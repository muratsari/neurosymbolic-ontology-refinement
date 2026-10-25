#!/usr/bin/env python3
"""Deterministic statistical primitives shared by the analysis scripts.

One-sided paired sign-flip permutation test (exact up to EXACT_MAX non-zero
differences, deterministic Monte Carlo beyond), Cohen's dz, LCG bootstrap 95% CI
and the Wilson score interval. No external randomness: every number is
reproducible bit for bit.
"""
import itertools, math, statistics as st

EXACT_MAX = 20          # exact enumeration up to 2^20 sign patterns
MC_DRAWS = 200000       # Monte Carlo draws beyond that (paper §4.7)

def signflip(diffs):  # one-sided, H1: mean > 0; zero differences are dropped
    nz = [d for d in diffs if abs(d) > 1e-12]
    if not nz: return 1.0
    obs = sum(nz)
    if len(nz) <= EXACT_MAX:
        c = sum(1 for s in itertools.product([1, -1], repeat=len(nz)) if sum(a*b for a, b in zip(s, nz)) >= obs - 1e-9)
        return c / 2 ** len(nz)
    # 2^n patterns are infeasible for n = 30 paired runs: deterministic Monte Carlo
    # (fixed-seed LCG, no external randomness) with the (1 + hits) / (1 + draws) estimator
    s, hits = 12345, 0
    for _ in range(MC_DRAWS):
        tot = 0.0
        for d in nz:
            s = (1103515245 * s + 12345) & 0x7fffffff
            tot += d if s & 0x40000000 else -d
        if tot >= obs - 1e-9:
            hits += 1
    return (1 + hits) / (1 + MC_DRAWS)

def cohen_dz(diffs):
    nz = [d for d in diffs if abs(d) > 1e-12] or diffs
    if len(diffs) < 2 or st.pstdev(diffs) == 0: return 0.0
    return st.mean(diffs) / st.stdev(diffs)

def boot_ci(diffs, iters=20000, seed=12345):
    # deterministic bootstrap (LCG, no external randomness)
    if not diffs: return (0.0, 0.0)
    n = len(diffs); s = seed; means = []
    for _ in range(iters):
        acc = 0
        for _ in range(n):
            s = (1103515245 * s + 12345) & 0x7fffffff
            acc += diffs[s % n]
        means.append(acc / n)
    means.sort()
    return (means[int(0.025*iters)], means[int(0.975*iters)])

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k/n; d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d
    return (c-h, c+h)
