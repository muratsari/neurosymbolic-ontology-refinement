"""SVG (source) -> PNG (single-layer raster for embedding in a manuscript), high resolution via cairosvg.
Usage: python statistics/svg2png.py   (fig*.svg -> fig*.png, next to this script)
Flow: make_all_figs.py draws the SVG (theme in one place) -> this script converts it to PNG."""
import cairosvg, glob, os

BASE = os.path.dirname(os.path.abspath(__file__))
SVG = BASE                      # fig*.svg next to this script
PNG = BASE
SCALE = 4.0  # matplotlib SVG at ~96 dpi, x4 = about 384 dpi (print quality)

n = 0
for s in sorted(glob.glob(os.path.join(SVG, '*.svg'))):
    name = os.path.basename(s)[:-4] + '.png'
    out = os.path.join(PNG, name)
    cairosvg.svg2png(url=s, write_to=out, scale=SCALE, background_color='white')
    from PIL import Image
    w, h = Image.open(out).size
    print(f'  {name}  {w}×{h}px')
    n += 1
print(f'{n} SVG files converted to PNG (scale={SCALE}, white background).')
