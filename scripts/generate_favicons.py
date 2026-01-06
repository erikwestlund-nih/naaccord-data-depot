#!/usr/bin/env python3
"""
Generate favicon variants from SVG source.
Requires: pip install cairosvg pillow
"""
import os
from pathlib import Path
from PIL import Image
import io

try:
    import cairosvg
except ImportError:
    print("ERROR: cairosvg not installed. Run: pip install cairosvg pillow")
    exit(1)

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
SVG_SOURCE = BASE_DIR / "static" / "favicon.svg"
OUTPUT_DIR = BASE_DIR / "static"

# Favicon sizes needed for modern browsers
FAVICON_SIZES = [
    (16, 16),    # Classic favicon.ico size
    (32, 32),    # Standard favicon
    (48, 48),    # Windows site icons
    (64, 64),    # Windows site icons
    (128, 128),  # Chrome Web Store
    (180, 180),  # Apple Touch Icon
    (192, 192),  # Android Chrome
    (512, 512),  # Android Chrome, PWA
]

def generate_png_from_svg(svg_path, output_path, width, height):
    """Convert SVG to PNG at specified size."""
    png_data = cairosvg.svg2png(
        url=str(svg_path),
        output_width=width,
        output_height=height
    )

    # Save PNG
    with open(output_path, 'wb') as f:
        f.write(png_data)

    print(f"✅ Generated {output_path.name} ({width}x{height})")

def create_ico_from_pngs():
    """Create multi-resolution .ico file."""
    ico_sizes = [(16, 16), (32, 32), (48, 48)]
    images = []

    for width, height in ico_sizes:
        png_path = OUTPUT_DIR / f"favicon-{width}x{height}.png"
        if png_path.exists():
            images.append(Image.open(png_path))

    if images:
        ico_path = OUTPUT_DIR / "favicon.ico"
        images[0].save(
            ico_path,
            format='ICO',
            sizes=[(img.width, img.height) for img in images]
        )
        print(f"✅ Generated favicon.ico (multi-resolution)")

def main():
    if not SVG_SOURCE.exists():
        print(f"ERROR: SVG source not found: {SVG_SOURCE}")
        return

    print(f"📦 Generating favicons from {SVG_SOURCE.name}...")
    print()

    # Generate all PNG sizes
    for width, height in FAVICON_SIZES:
        output_path = OUTPUT_DIR / f"favicon-{width}x{height}.png"
        generate_png_from_svg(SVG_SOURCE, output_path, width, height)

    # Create Apple Touch Icon (special name)
    apple_icon = OUTPUT_DIR / "apple-touch-icon.png"
    generate_png_from_svg(SVG_SOURCE, apple_icon, 180, 180)

    # Create multi-resolution .ico file
    create_ico_from_pngs()

    print()
    print("🎉 All favicons generated successfully!")
    print()
    print("Add these to your HTML <head>:")
    print('  <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">')
    print('  <link rel="icon" type="image/png" sizes="32x32" href="/static/favicon-32x32.png">')
    print('  <link rel="icon" type="image/png" sizes="16x16" href="/static/favicon-16x16.png">')
    print('  <link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">')
    print('  <link rel="manifest" href="/static/site.webmanifest">')

if __name__ == "__main__":
    main()
