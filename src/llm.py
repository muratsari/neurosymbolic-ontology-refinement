"""
LLM clients for the pipeline.

Every generation call goes through a provider's official HTTP API. The extractors
of the study share one configuration (paper §4.4):

    MAX_OUTPUT_TOKENS  per-call output ceiling, reasoning tokens included
    REASONING          each provider's stated reasoning level (paper §4.4)
    no sampling parameters (temperature, top-p, top-k): provider defaults apply

- AnthropicClient : Claude (claude-sonnet-5; adaptive thinking + effort).
- GeminiClient    : Google Gemini through the google-genai SDK
                    (gemini-3.8-flash; thinking_level).
- OpenAICompatClient : any OpenAI-compatible chat-completions endpoint
                    (OpenAI gpt-6-sol with reasoning_effort; DeepSeek, OpenRouter).
- MockClient      : offline, deterministic stub used to verify the pipeline
                    plumbing without network/API access. It is NOT a real
                    extractor -- it builds a tiny, deliberately-flawed ontology
                    from frequent corpus terms so that the reason -> refine ->
                    evaluate path can be exercised end to end.

Every client exposes the same surface:
    .complete(system, prompt, max_tokens=None, cache=False) -> str
    .name        -> "<provider>:<model>"
    .reasoning   -> the reasoning level sent with every call
    .stats       -> calls, tokens (cache reads/writes separately), seconds,
                    truncations, served model ids
    .call_log    -> set to a list to record every reply (raw output archive)

`cache=True` marks the prompt as a prompt-cache prefix. The pipeline sets it only on
the extraction call, whose prompt (frozen prompt + whole corpus) is identical across
the runs of a domain. Caching changes billing and latency, never the reply: each
reply is generated afresh.

Selection (in precedence order):
    get_client(provider=..., model=...)        explicit (CLI --provider/--model)
    PIPELINE_PROVIDER=anthropic|gemini|openai|deepseek|openrouter|mock
    PIPELINE_LLM=anthropic|mock                (legacy alias, still honoured)
    auto: anthropic if ANTHROPIC_API_KEY is set, else mock
"""
import os, re, json, time, hashlib, collections

# Shared generation settings (paper §4.4). 64,000 fits under every model's output
# cap (Gemini 3.8 Flash: 65,536); reasoning tokens count against this limit.
MAX_OUTPUT_TOKENS = 64000
# Reasoning level per provider, as stated in the paper (§4.4): Claude at its default
# effort ("high"); Gemini at "medium", which keeps a whole-ontology rewrite clear of
# the 65,536-token cap (at "high" its reasoning alone reached 54k tokens).
REASONING = {"anthropic": "high", "gemini": "medium", "openai": "high"}
CACHE_TTL = "1h"         # consecutive runs of a domain start more than 5 minutes apart
API_RETRIES = 6          # transient errors (429, 5xx, connection) are retried by the SDKs
API_TIMEOUT_S = 1800     # one extraction call over the whole corpus can take minutes

# OpenAI-compatible providers. `token_param` differs because the newer OpenAI
# models reject `max_tokens` in favour of `max_completion_tokens`.
PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-v4-pro",
        "token_param": "max_tokens",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model": "qwen/qwen3-235b-a22b",
        "token_param": "max_tokens",
    },
    "openai": {
        "base_url": None,                      # SDK default
        "key_env": "OPENAI_API_KEY",
        "model": "gpt-6-sol",
        "token_param": "max_completion_tokens",
        "reasoning_effort": True,
    },
}


def _truncated(name):
    """A reply cut off at MAX_OUTPUT_TOKENS is never used: a truncated ontology can
    still parse, look less faulty and pass the gate while silently losing content.
    Returning nothing makes the caller treat it as unusable and retry."""
    import sys
    sys.stderr.write(f"  ! {name}: reply truncated at the output limit, discarded\n")
    return ""


class QuotaExhausted(RuntimeError):
    """Provider quota or prepaid credit exhausted: retrying is pointless, the run set
    should stop (and resume later with --run-offset)."""


_QUOTA_MARKERS = ("credit balance", "prepayment credits", "insufficient_quota",
                  "billing", "quota")


def _raise_if_quota(err):
    """Turn a provider's out-of-credit / out-of-quota error into QuotaExhausted."""
    text = str(err).lower()
    code = getattr(err, "status_code", None) or getattr(err, "code", None)
    if code == 402 or (code in (400, 403, 429) and any(m in text for m in _QUOTA_MARKERS)):
        raise QuotaExhausted(str(err)[:300]) from err


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _record(client, system, prompt, reply, finish, usage, seconds, model_id):
    """Append one call to client.call_log when the caller asked for an archive.
    Prompts are stored as hashes and sizes only: they contain the corpus, part of
    which may not be redistributed. Replies are stored verbatim."""
    log = getattr(client, "call_log", None)
    if log is None:
        return
    log.append({"model_id": model_id, "finish": str(finish), "seconds": round(seconds, 1),
                "usage": usage, "system_sha": _sha(system), "prompt_sha": _sha(prompt),
                "prompt_chars": len(prompt), "reply": reply})


class _Stats:
    """Per-client call/token/wall-clock accounting (feeds the cost table that
    closes the paper's 'computational cost was not instrumented' limitation).

    in_tokens is the full prompt size; cache_read_tokens and cache_write_tokens are
    the parts of it billed at cache prices."""

    def __init__(self):
        self.calls = 0
        self.in_tokens = 0
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0
        self.out_tokens = 0
        self.thinking_tokens = 0
        self.seconds = 0.0
        self.truncated = 0           # replies cut off at MAX_OUTPUT_TOKENS
        self.model_ids = set()       # model versions the provider reports serving

    def add(self, dt, n_in, n_out, n_think=0, truncated=False, model_id=None,
            cache_read=0, cache_write=0):
        self.calls += 1
        self.seconds += dt
        self.in_tokens += n_in or 0
        self.cache_read_tokens += cache_read or 0
        self.cache_write_tokens += cache_write or 0
        self.out_tokens += n_out or 0
        self.thinking_tokens += n_think or 0
        self.truncated += int(bool(truncated))
        if model_id:
            self.model_ids.add(str(model_id))

    def asdict(self):
        return {"calls": self.calls, "in_tokens": self.in_tokens,
                "cache_read_tokens": self.cache_read_tokens,
                "cache_write_tokens": self.cache_write_tokens,
                "out_tokens": self.out_tokens,
                "thinking_tokens": self.thinking_tokens,
                "seconds": round(self.seconds, 2),
                "truncated": self.truncated,
                "model_ids": sorted(self.model_ids)}


class AnthropicClient:
    def __init__(self, model=None):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=API_RETRIES, timeout=API_TIMEOUT_S)
        self.model = model or os.environ.get("PIPELINE_MODEL", "claude-sonnet-5")
        self.reasoning = REASONING["anthropic"]
        self.stats = _Stats()
        self.call_log = None

    def complete(self, system, prompt, max_tokens=None, cache=False):
        # Streaming keeps a 64k-token reply clear of HTTP timeouts. The Messages API
        # does not report thinking tokens separately: output_tokens includes them.
        block = {"type": "text", "text": prompt}
        if cache:
            block["cache_control"] = {"type": "ephemeral", "ttl": CACHE_TTL}
        t0 = time.time()
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens or MAX_OUTPUT_TOKENS,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": self.reasoning},
                messages=[{"role": "user", "content": [block]}],
            ) as stream:
                msg = stream.get_final_message()
        except self.anthropic.APIStatusError as e:
            _raise_if_quota(e)
            raise
        dt = time.time() - t0
        u = getattr(msg, "usage", None)
        c_read = getattr(u, "cache_read_input_tokens", 0) or 0
        c_write = getattr(u, "cache_creation_input_tokens", 0) or 0
        n_in = (getattr(u, "input_tokens", 0) or 0) + c_read + c_write
        n_out = getattr(u, "output_tokens", 0) or 0
        model_id = getattr(msg, "model", None)
        self.stats.add(dt, n_in, n_out, truncated=(msg.stop_reason == "max_tokens"),
                       model_id=model_id, cache_read=c_read, cache_write=c_write)
        reply = "".join(b.text for b in msg.content if b.type == "text")
        _record(self, system, prompt, reply, msg.stop_reason,
                {"in": n_in, "cache_read": c_read, "cache_write": c_write, "out": n_out},
                dt, model_id)
        if msg.stop_reason == "refusal":
            raise RuntimeError(f"{self.name}: request refused ({msg.stop_details})")
        if msg.stop_reason == "max_tokens":
            return _truncated(self.name)
        return reply

    @property
    def name(self):
        return f"anthropic:{self.model}"


class OpenAICompatClient:
    """OpenAI-compatible chat-completions client (DeepSeek / OpenRouter / OpenAI).

    Reasoning-model note: providers that expose chain-of-thought return it in a
    separate `reasoning_content` field; only `message.content` is read here, so
    the Turtle payload is never polluted by reasoning text. Prompt caching is
    automatic on these endpoints; `cache` is accepted for interface parity.
    """

    def __init__(self, provider, model=None, base_url=None, api_key=None):
        from openai import OpenAI
        cfg = PROVIDERS.get(provider)
        if cfg is None:
            raise ValueError(f"unknown provider {provider!r}; "
                             f"known: {sorted(PROVIDERS)}")
        self.provider = provider
        self.token_param = cfg["token_param"]
        self.reasoning = REASONING["openai"] if cfg.get("reasoning_effort") else None
        self.model = model or os.environ.get("PIPELINE_MODEL") or cfg["model"]
        key = api_key or os.environ.get(cfg["key_env"])
        if not key:
            raise RuntimeError(
                f"{cfg['key_env']} is not set (required for provider {provider!r})")
        kwargs = {"api_key": key, "max_retries": API_RETRIES, "timeout": API_TIMEOUT_S}
        url = base_url or cfg["base_url"]
        if url:
            kwargs["base_url"] = url
        self.client = OpenAI(**kwargs)
        self.stats = _Stats()
        self.call_log = None

    def complete(self, system, prompt, max_tokens=None, cache=False):
        t0 = time.time()
        extra = {"reasoning_effort": self.reasoning} if self.reasoning else {}
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                **{self.token_param: max_tokens or MAX_OUTPUT_TOKENS},
                **extra,
            )
        except Exception as e:
            _raise_if_quota(e)
            raise
        dt = time.time() - t0
        u = getattr(resp, "usage", None)
        details = getattr(u, "completion_tokens_details", None)
        p_details = getattr(u, "prompt_tokens_details", None)
        c_read = getattr(p_details, "cached_tokens", 0) or 0
        choice = resp.choices[0]
        n_in = getattr(u, "prompt_tokens", 0) or 0
        n_out = getattr(u, "completion_tokens", 0) or 0       # includes reasoning
        n_think = getattr(details, "reasoning_tokens", 0) or 0
        model_id = getattr(resp, "model", None)
        self.stats.add(dt, n_in, n_out, n_think,
                       truncated=(choice.finish_reason == "length"),
                       model_id=model_id, cache_read=c_read)
        reply = choice.message.content or ""
        _record(self, system, prompt, reply, choice.finish_reason,
                {"in": n_in, "cache_read": c_read, "out": n_out, "thinking": n_think},
                dt, model_id)
        if choice.finish_reason == "length":
            return _truncated(self.name)
        return reply

    @property
    def name(self):
        return f"{self.provider}:{self.model}"


class GeminiClient:
    """Google Gemini through the official google-genai SDK.

    Used instead of Gemini's OpenAI-compatibility layer because only the native
    API sets thinking_level directly and reports thinking tokens and the served
    model version for every call. Prompt caching of repeated prefixes is implicit
    on the Gemini API; `cache` is accepted for interface parity.
    """

    DEFAULT_MODEL = "gemini-3.8-flash"

    def __init__(self, model=None):
        from google import genai
        from google.genai import types
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set (required for provider 'gemini')")
        self.types = types
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(
            timeout=API_TIMEOUT_S * 1000,
            retry_options=types.HttpRetryOptions(attempts=API_RETRIES)))
        self.model = model or os.environ.get("PIPELINE_MODEL") or self.DEFAULT_MODEL
        self.reasoning = REASONING["gemini"]
        self.stats = _Stats()
        self.call_log = None

    def complete(self, system, prompt, max_tokens=None, cache=False):
        t = self.types
        t0 = time.time()
        try:
            resp = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=t.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens or MAX_OUTPUT_TOKENS,
                    thinking_config=t.ThinkingConfig(thinking_level=self.reasoning.upper()),
                ),
            )
        except Exception as e:
            _raise_if_quota(e)
            raise
        dt = time.time() - t0
        u = resp.usage_metadata
        finish = resp.candidates[0].finish_reason if resp.candidates else None
        n_in = getattr(u, "prompt_token_count", 0) or 0         # includes cached tokens
        c_read = getattr(u, "cached_content_token_count", 0) or 0
        n_out = getattr(u, "candidates_token_count", 0) or 0
        n_think = getattr(u, "thoughts_token_count", 0) or 0
        self.stats.add(dt, n_in, n_out, n_think,
                       truncated=(finish == t.FinishReason.MAX_TOKENS),
                       model_id=resp.model_version, cache_read=c_read)
        reply = resp.text or ""
        _record(self, system, prompt, reply, finish,
                {"in": n_in, "cache_read": c_read, "out": n_out, "thinking": n_think},
                dt, resp.model_version)
        if finish == t.FinishReason.MAX_TOKENS:
            return _truncated(self.name)
        if finish != t.FinishReason.STOP:
            raise RuntimeError(f"{self.name}: generation ended with {finish}")
        return reply

    @property
    def name(self):
        return f"gemini:{self.model}"


# Stop-words so the mock doesn't turn boilerplate into "concepts".
_STOP = set("""The This That These Those With From Into Over Under When While Where
What Which Their There Here Both Each Some Most More Less Such About After Before
Diabetes Type Wikipedia English Glossary Education Reform Financial European Central
Bank National Institute American""".split())


class MockClient:
    """Deterministic offline stub. Injects exactly one unsatisfiable class and one
    domain/range-less property at extraction, then repairs them on correction."""

    name = "mock:offline-stub"
    reasoning = None

    def __init__(self):
        self.stats = _Stats()
        self.call_log = None

    def complete(self, system, prompt, max_tokens=None, cache=False):
        self.stats.add(0.0, len(prompt) // 4, 0, model_id=self.name)
        if "TASK: CORRECT" in prompt:
            # patch mode asks for a JSON edit list, rewrite mode for Turtle
            return self._patch() if "JSON" in system else self._correct(prompt)
        # the frozen extraction prompts do not carry a task marker
        return self._extract(prompt)

    @staticmethod
    def _patch():
        return json.dumps({"drop_subclass": [["MockHybrid", "MockB"]],
                           "add_domain": [["mockRelates", "MockA"]],
                           "add_range": [["mockRelates", "MockB"]]})

    def _extract(self, prompt):
        corpus = prompt.split("CORPUS:", 1)[-1]
        freq = collections.Counter(
            w for w in re.findall(r"\b([A-Z][a-z]{4,})\b", corpus) if w not in _STOP
        )
        concepts = [w for w, _ in freq.most_common(10)] or ["Alpha", "Beta", "Gamma"]
        ns = "http://example.org/gen#"
        lines = [f"@prefix : <{ns}> .",
                 "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
                 "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
                 "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
                 "<http://example.org/gen> a owl:Ontology .",
                 ":Concept a owl:Class ; rdfs:label \"Concept\" ."]
        for c in concepts:
            lines.append(f":{c} a owl:Class ; rdfs:label \"{c}\" ; rdfs:subClassOf :Concept .")
        # a real-ish relation (subClassOf chain) for relation P/R/F1
        if len(concepts) >= 2:
            lines.append(f":{concepts[1]} rdfs:subClassOf :{concepts[0]} .")
        # --- injected flaws (so refinement has something to fix) ---
        lines += [
            ":MockA a owl:Class ; rdfs:label \"Mock A\" .",
            ":MockB a owl:Class ; rdfs:label \"Mock B\" .",
            "[] a owl:AllDisjointClasses ; owl:members ( :MockA :MockB ) .",
            ":MockHybrid a owl:Class ; rdfs:label \"Mock Hybrid\" ; rdfs:subClassOf :MockA , :MockB .",
            ":mockRelates a owl:ObjectProperty ; rdfs:label \"mock relates\" .",
        ]
        return "```turtle\n" + "\n".join(lines) + "\n```"

    def _correct(self, prompt):
        # operate on the current ontology embedded in the prompt (format-tolerant)
        m = re.search(r"```(?:turtle)?\s*(.*?)```", prompt, flags=re.S | re.I)
        ttl = m.group(1) if m else ""
        # fix the unsatisfiable class: drop one of the two disjoint parents
        # (regex tolerant to rdflib's whitespace/newline serialisation)
        ttl = re.sub(r":MockA\s*,\s*:MockB", ":MockA", ttl)
        ttl = re.sub(r":MockB\s*,\s*:MockA", ":MockA", ttl)
        # fix missing domain/range by appending a statement (rdflib merges by subject)
        ttl += "\n:mockRelates rdfs:domain :MockA ; rdfs:range :MockB .\n"
        return "```turtle\n" + ttl + "\n```"


def get_client(provider=None, model=None):
    """Resolve a client. Explicit args win, then PIPELINE_PROVIDER, then the
    legacy PIPELINE_LLM alias, then auto-detection from available keys."""
    choice = (provider
              or os.environ.get("PIPELINE_PROVIDER")
              or os.environ.get("PIPELINE_LLM"))
    if not choice:
        choice = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "mock"
    choice = choice.strip().lower()
    if choice == "mock":
        return MockClient()
    if choice == "anthropic":
        return AnthropicClient(model=model)
    if choice == "gemini":
        return GeminiClient(model=model)
    if choice in PROVIDERS:
        return OpenAICompatClient(choice, model=model)
    raise ValueError(f"unknown provider {choice!r}; known: "
                     f"{['anthropic', 'gemini', 'mock'] + sorted(PROVIDERS)}")
