"""Shared figure theme for Fig. 3-5: palette, series colours and matplotlib defaults."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# --- palette (stage colours: light fill, dark edge/title) ---
C = {
    'neural':   ('#E8F0FB', '#2E5EAA'),   # blue
    'semantic': ('#E6F4EC', '#2E8B57'),   # green
    'symbolic': ('#FDEEDD', '#E8820C'),   # orange
    'refine':   ('#EFE9F6', '#7B5EA7'),   # purple
    'io':       ('#F4F5F7', '#3A3F4B'),   # neutral grey (input/output)
    'plain':    ('#FFFFFF', '#3A3F4B'),   # white box
    'warn':     ('#FDECEA', '#C0392B'),   # red (detected issues)
}
INK = '#2A2E37'
MUTED = '#5A6270'
GRID = '#DDDDDD'
# chart series (Fig. 3/4), taken from the stage colours, colour-blind safe
SERIES = {'LLM-only': '#E8820C', 'LLM + single-pass repair': '#2E5EAA', 'Proposed (Hybrid)': '#2E8B57'}

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
    'font.size': 10, 'text.color': INK, 'axes.edgecolor': '#8A909C',
    'axes.linewidth': 0.9,
    # 'path': text is embedded as glyph outlines, so the matplotlib rendering is preserved
    # exactly in Word/PDF (no font-fallback shifts). Edit the source in make_all_figs.py.
    'svg.fonttype': 'path', 'pdf.fonttype': 42,
})
