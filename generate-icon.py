#!/usr/bin/env python3
"""Generate a proper TrustTunnel app icon as .icns file using Pillow + iconutil."""
import os
import sys
import subprocess
import tempfile
import shutil

def create_icon(size, output_path):
    """Create a shield+VPN icon PNG at the given size."""
    from PIL import Image, ImageDraw

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = max(1, size // 16)
    bg_color = (45, 45, 45, 255)

    # Background rounded rect
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=max(size // 8, 2),
        fill=bg_color
    )

    # Shield shape
    cx, cy = size // 2, size // 2
    shield_w = int(size * 0.55)
    shield_h = int(size * 0.65)
    shield_x1 = cx - shield_w // 2
    shield_y1 = cy - shield_h // 2
    shield_x2 = cx + shield_w // 2
    shield_y2 = cy + shield_h // 2
    shield_color = (37, 99, 235, 255)
    draw.rounded_rectangle(
        [shield_x1, shield_y1, shield_x2, shield_y2],
        radius=max(size // 10, 2),
        fill=shield_color
    )

    # Tunnel line — white horizontal
    line_width = max(1, size // 32)
    line_y = cy - shield_h // 6
    line_x1 = cx - shield_w // 3
    line_x2 = cx + shield_w // 3
    draw.line([(line_x1, line_y), (line_x2, line_y)], fill=(255, 255, 255, 255), width=line_width)

    # Connection dot — green
    dot_r = max(2, size // 20)
    dot_y = cy + shield_h // 5
    draw.ellipse(
        [cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
        fill=(78, 201, 176, 255)
    )

    img.save(output_path)

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'icon.icns'

    tmpdir = tempfile.mkdtemp()
    try:
        # Generate all required sizes
        # iconutil needs: 16x16, 32x32, 128x128, 256x256, 512x512
        # Plus @2x versions: icon_16x16@2x = 32x32, etc.
        sizes = [16, 32, 64, 128, 256, 512]
        for s in sizes:
            create_icon(s, os.path.join(tmpdir, f'{s}x{s}.png'))

        # Build iconset directory
        iconset = os.path.join(tmpdir, 'trusttunnel.iconset')
        os.makedirs(iconset)

        # Standard sizes
        for s in sizes:
            src = os.path.join(tmpdir, f'{s}x{s}.png')
            shutil.copy2(src, os.path.join(iconset, f'icon_{s}x{s}.png'))

        # @2x sizes (16@2x=32, 32@2x=64, 128@2x=256, 256@2x=512)
        retinas = [(16, 32), (32, 64), (128, 256), (256, 512)]
        for small, large in retinas:
            src = os.path.join(tmpdir, f'{large}x{large}.png')
            shutil.copy2(src, os.path.join(iconset, f'icon_{small}x{small}@2x.png'))

        # Convert to .icns
        subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', out], check=True)
        print(f"Created {out}")

    finally:
        shutil.rmtree(tmpdir)

if __name__ == '__main__':
    main()
