"""
thumbnail_generator.py
Creates eye-catching YouTube thumbnails using Pillow. No external API needed.
"""

import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
import config

THUMB_W, THUMB_H = 1280, 720

_THEMES = {
    "personal finance": {
        "bg_top":    (8,  12, 35),
        "bg_bottom": (15, 65, 50),
        "accent":    (0,  230, 120),
        "text":      (255, 255, 255),
        "sub":       (160, 255, 190),
        "bar":       (0,  200, 100),
    },
    "AI tools and technology": {
        "bg_top":    (5,   5,  20),
        "bg_bottom": (25,  8,  70),
        "accent":    (120, 80, 255),
        "text":      (255, 255, 255),
        "sub":       (200, 185, 255),
        "bar":       (100, 60, 240),
    },
}

_DEFAULT_THEME = {
    "bg_top":    (10, 10, 30),
    "bg_bottom": (30, 30, 80),
    "accent":    (80, 160, 255),
    "text":      (255, 255, 255),
    "sub":       (200, 220, 255),
    "bar":       (60,  130, 220),
}

_FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]
_FONT_CANDIDATES_REG = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]


def _get_font(size: int, bold: bool = False):
    candidates = _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REG
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _gradient(img: Image.Image, top: tuple, bottom: tuple) -> None:
    draw = ImageDraw.Draw(img)
    for y in range(THUMB_H):
        t = y / THUMB_H
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (THUMB_W, y)], fill=color)


def _draw_text_centered(draw, text, font, y, color, shadow_color=(0, 0, 0)):
    # Measure width using textbbox
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (THUMB_W - w) // 2
    # Drop shadow
    draw.text((x + 3, y + 3), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=color)


def create_thumbnail(title: str, output_path: str) -> str:
    theme = _THEMES.get(config.NICHE, _DEFAULT_THEME)

    img = Image.new("RGB", (THUMB_W, THUMB_H))
    _gradient(img, theme["bg_top"], theme["bg_bottom"])
    draw = ImageDraw.Draw(img)

    # Left accent bar
    draw.rectangle([(0, 0), (14, THUMB_H)], fill=theme["bar"])
    # Bottom accent bar
    draw.rectangle([(0, THUMB_H - 10), (THUMB_W, THUMB_H)], fill=theme["bar"])

    # Decorative accent dots (top-right)
    for i, (cx, cy, r) in enumerate([(THUMB_W - 80, 70, 10), (THUMB_W - 48, 95, 7), (THUMB_W - 105, 100, 5)]):
        alpha = 200 - i * 40
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=theme["accent"])

    # Title — word-wrap to 3 lines max, font size adapts to line count
    words = title.split()
    lines = textwrap.wrap(title, width=20)[:3]
    font_size = 100 if len(lines) == 1 else (86 if len(lines) == 2 else 72)
    font_title = _get_font(font_size, bold=True)
    font_channel = _get_font(36)

    line_h = font_size + 16
    total_h = len(lines) * line_h
    y = (THUMB_H - total_h) // 2 - 20

    for line in lines:
        _draw_text_centered(draw, line, font_title, y, theme["text"])
        y += line_h

    # Channel name — bottom right
    ch_bbox = draw.textbbox((0, 0), config.CHANNEL_NAME, font=font_channel)
    ch_w = ch_bbox[2] - ch_bbox[0]
    draw.text(
        (THUMB_W - ch_w - 30, THUMB_H - 52),
        config.CHANNEL_NAME,
        font=font_channel,
        fill=theme["sub"],
    )

    abs_path = os.path.abspath(output_path)
    img.save(abs_path, "JPEG", quality=95)
    print(f"[thumbnail] Created → {abs_path}")
    return abs_path
