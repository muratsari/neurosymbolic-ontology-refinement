"""Figures 3-5 of the paper, drawn from statistics/figure_data.json (SVG + PDF next to this script).
Usage: python statistics/make_all_figs.py ; python statistics/svg2png.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib.pyplot as plt
import numpy as np
from figtheme import C, INK, MUTED, GRID, SERIES
OUT = os.path.dirname(os.path.abspath(__file__))


def save(fig, name):
    # SVG is the single source (theme applied here); PNGs are derived by svg2png.py.
    import os
    fig.savefig(f'{OUT}/{name}.svg', bbox_inches='tight')   # editable vector source
    fig.savefig(f'{OUT}/{name}.pdf', bbox_inches='tight')   # vector for submission
    plt.close(fig)


# --------------------------------------------------------------------------- #
# The numerical inputs are computed from results/ by statistics/figure_data.py.
# This script only draws; no measured value is hard-coded here.
# --------------------------------------------------------------------------- #
import json as _json, os as _os
_DATA_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                           "figure_data.json")
if not _os.path.exists(_DATA_PATH):
    raise SystemExit("statistics/figure_data.json is missing; run "
                     "python statistics/figure_data.py first")
FIGDATA = _json.load(open(_DATA_PATH, encoding="utf-8"))

# ===================== FIG 3: Performance bar =====================
fig, ax = plt.subplots(figsize=(6.6, 3.7))
metrics = ['Coherence', 'CQ accuracy', 'F1']
methods = ['LLM-only', 'LLM + single-pass repair', 'Proposed (Hybrid)']
vals = FIGDATA['fig3']['values']
x = np.arange(3); w = 0.26
for j, m in enumerate(methods):
    bb = ax.bar(x + (j - 1) * w, vals[m], w, label=m, color=SERIES[m], edgecolor='white', linewidth=0.7, zorder=3)
    for b, v in zip(bb, vals[m]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.015, f'{v:.2f}', ha='center', va='bottom', fontsize=7.5, color='#333')
ax.set_ylim(0, 1.08); ax.set_xticks(x); ax.set_xticklabels(metrics); ax.set_ylabel('Score (0–1)')
ax.yaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, fontsize=8.5, loc='upper center', bbox_to_anchor=(0.5, 1.14), ncol=3, columnspacing=1.1)
fig.tight_layout(); save(fig, 'fig3_performance')
print('Fig 3 OK')

# ===================== FIG 4: Error distribution =====================
fig, ax = plt.subplots(figsize=(6.2, 3.5))
_f4 = FIGDATA['fig4']
_LBL = {'unsatisfiable_class': 'Unsatisfiable\nclasses', 'inconsistency': 'Reasoner failure\n(treated as\ninconsistency)',
        'missing_domain': 'Missing\ndomain', 'missing_range': 'Missing\nrange'}
cats = [_LBL.get(c, c) for c in _f4['categories']]
tot = [_f4['totals'][c] for c in _f4['categories']]
runs = [_f4['runs_with'][c] for c in _f4['categories']]
_N4 = _f4['n_ontologies']
bb = ax.barh(range(len(cats)), tot, color=SERIES['LLM + single-pass repair'], edgecolor='white', linewidth=0.7, height=0.6, zorder=3)
for b, t, r in zip(bb, tot, runs):
    ax.text(t + 3, b.get_y() + b.get_height() / 2, f'{t}  ({r}/{_N4} runs)', va='center', fontsize=8.5, color='#333')
ax.set_yticks(range(len(cats))); ax.set_yticklabels(cats); ax.invert_yaxis()
ax.set_xlabel(f'Total occurrences across {_N4} LLM-only ontologies')
ax.set_xlim(0, max(tot) * 1.22)
ax.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
fig.tight_layout(); save(fig, 'fig4_errors')
print('Fig 4 OK')

# ===================== FIG 5: Refinement iteration distribution (finance) =====================
fig, ax = plt.subplots(figsize=(5.4, 3.2))
_f5 = FIGDATA['fig5']['primary']
iters = _f5['iterations']; counts = _f5['counts']; _CAP = _f5['cap']
bb = ax.bar(iters, counts, width=0.62, color=C['refine'][1], edgecolor='white', linewidth=0.8, zorder=3)
for b, c in zip(bb, counts):
    ax.text(b.get_x() + b.get_width() / 2, c + 0.25, str(c), ha='center', va='bottom', fontsize=9, color='#333')
ax.set_xticks(iters); ax.set_xticklabels([str(i) for i in iters])
ax.set_xlabel('Committed refinement iterations per run'); ax.set_ylabel('Number of runs')
ax.set_ylim(0, max(counts) * 1.18); ax.set_xlim(-0.6, _CAP + 0.45)
ax.axvline(_CAP, color=MUTED, linestyle='--', linewidth=1.1, zorder=1)
ax.text(_CAP, max(counts) * 1.08, f'cap = {_CAP}', ha='center', va='top', fontsize=8, color=MUTED, style='italic')
ax.text(_CAP - 0.25, max(counts) * 0.79, f"median {_f5['median']:g}\n(n = {_f5['n']}, finance)", ha='right', va='top', fontsize=8.5, color=MUTED)
ax.yaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); ax.set_axisbelow(True)
for s in ['top', 'right']:
    ax.spines[s].set_visible(False)
fig.tight_layout(); save(fig, 'fig5_iterations')
print('Fig 5 OK')
