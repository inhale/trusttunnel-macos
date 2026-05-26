#!/usr/bin/env python3
"""Generate a black-hole themed TrustTunnel app icon as .icns file using Pillow + iconutil."""
import os
import sys
import subprocess
import tempfile
import shutil
import math


def create_icon(size, output_path):
    """Create a black hole icon PNG at the given size."""
    from PIL import Image, ImageDraw

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2

    # ── Outer glow (accretion disk halo) ──
    for r in range(int(size * 0.48), int(size * 0.35), -1):
        t = (r - size * 0.35) / (size * 0.48 - size * 0.35)
        alpha = int(40 + 60 * (1 - t))
        color = (
            int(80 + 120 * t),
            int(40 + 60 * t),
            int(180 + 75 * t),
            alpha,
        )
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=color,
        )

    # ── Accretion disk ring (bright, tilted ellipse to suggest rotation) ──
    ring_r = int(size * 0.38)
    ring_w = max(2, size // 12)
    for offset in range(ring_w):
        t = offset / ring_w
        alpha = int(180 + 75 * math.sin(t * math.pi))
        # Tilted: slightly elliptical
        rx = ring_r + offset
        ry = int(ring_r * 0.6) + offset
        r = int(ring_r * 0.3 + offset)
        color = (
            int(120 + 135 * t),
            int(80 + 100 * t),
            int(200 + 55 * (1 - t)),
            alpha,
        )
        draw.ellipse(
            [cx - rx, cy - ry, cx + rx, cy + ry],
            outline=color,
            width=1,
        )

    # ── Event horizon (solid black center) ──
    hole_r = int(size * 0.22)
    draw.ellipse(
        [cx - hole_r, cy - hole_r, cx + hole_r, cy + hole_r],
        fill=(0, 0, 0, 255),
    )

    # ── Inner glow ring (just outside event horizon) ──
    for r in range(hole_r + 3, hole_r - 1, -1):
        if r <= hole_r:
            break
        t = (r - hole_r) / 3
        alpha = int(120 * (1 - t))
        color = (60, 30, 140, alpha)
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=color,
            width=1,
        )

    # ── Gravitational lensing arcs (light bending around the hole) ──
    arc_r = int(size * 0.28)
    for angle_offset in [30, -30, 60, -60]:
        start_a = angle_offset - 20
        end_a = angle_offset + 20
        alpha = 50 + abs(angle_offset) // 3
        color = (100, 60, 200, alpha)
        bbox = [cx - arc_r, cy - arc_r, cx + arc_r, cy + arc_r]
        draw.arc(bbox, start_a, end_a, fill=color, width=max(1, size // 40))

    img.save(output_path)


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else 'icon.icns'

    tmpdir = tempfile.mkdtemp()
    try:
        # Generate all required sizes
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

        # @2x sizes
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
