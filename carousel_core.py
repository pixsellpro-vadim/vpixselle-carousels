"""Генерує слайди каруселі з тексту посту (абзаци -> слайди) у стилі шаблону Вадима:
світлий фон + ілюстрований персонаж внизу на КОЖНОМУ слайді + біла картка з текстом зверху.

Використання: python make_carousel.py "<текст з порожніми рядками між абзацами>" <папка_виводу> <префікс>
Робить два набори JPEG: instagram (1080x1350, 4:5) і tiktok (1080x1920, 9:16).
Потрібен файл cta_template.jpg поруч зі скриптом (шаблон 768x1376).
Параметри верстки (LAYOUT, SIZES) налаштовуються нижче.
"""
import re
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = str(Path(__file__).resolve().parent) + "/"
BOLD = FONT_DIR + "Inter-ExtraBold.otf"
SEMI = FONT_DIR + "Inter-SemiBold.otf"

TEMPLATE = Path(__file__).resolve().parent / "cta_template.jpg"
TPL_CARD = (50, 198, 718, 640)       # стара картка шаблону разом з тінню (пікселі шаблону 768x1376)
TPL_ROCKET = (556, 516, 634, 596)    # ракета з оригінального тексту шаблону

BLUE = (10, 75, 143)
ORANGE = (222, 75, 32)
MUTED = (118, 136, 172)

FORMATS = {"instagram": (1080, 1350), "tiktok": (1080, 1920)}

# card = (x, y, ширина, висота) картки з текстом; shift = на скільки опустити персонажа (Instagram)
LAYOUT = {
    "tiktok": {"shift": None, "card": (60, 225, 960, 640)},      # знизу ~460 px і справа ~170 px перекриває інтерфейс TikTok
    "instagram": {"shift": 100, "card": (60, 70, 960, 620)},
}
# початковий / мінімальний розмір шрифту: хук, звичайний слайд, фінальний слайд
SIZES = {"hook": (92, 40), "body": (72, 36), "cta": (88, 40)}


def split_cta(text):
    """'Напиши «КЛЮЧ» — продовження' -> ('КЛЮЧ', 'продовження')."""
    m = re.search(r"«([^»]+)»", text)
    if not m:
        return None, text
    return m.group(1), text[m.end():].lstrip(" —-")


def build_scene(fmt, w, h):
    """Фон із персонажем: шаблон масштабується під формат, поля добудовуються краями фону,
    стара картка шаблону замальовується градієнтом фону."""
    tpl = Image.open(TEMPLATE).convert("RGB")
    tw, th = tpl.size
    canvas = Image.new("RGB", (w, h))
    if fmt == "tiktok":
        s = w / tw
        base = tpl.resize((w, round(th * s)), Image.LANCZOS)
        ox, oy = 0, -((base.height - h) // 2) if base.height > h else 0
    else:
        s = h / th
        base = tpl.resize((round(tw * s), h), Image.LANCZOS)
        ox, oy = (w - base.width) // 2, LAYOUT["instagram"]["shift"]
    canvas.paste(base, (ox, oy))
    if ox > 0:  # поля по боках
        canvas.paste(base.crop((0, 0, 1, base.height)).resize((ox, base.height)), (0, oy))
        canvas.paste(base.crop((base.width - 1, 0, base.width, base.height)).resize((w - ox - base.width, base.height)),
                     (ox + base.width, oy))
    if oy > 0:  # зверху після зсуву вниз
        canvas.paste(canvas.crop((0, oy, w, oy + 1)).resize((w, oy)), (0, 0))

    x0, y0, x1, y1 = TPL_CARD
    cy0, cy1 = round(oy + y0 * s), round(oy + y1 * s)
    top = np.array(canvas.crop((0, cy0 - 6, w, cy0 - 5)).convert("RGB"))[0].astype(float)
    bot = np.array(canvas.crop((0, cy1 + 6, w, cy1 + 7)).convert("RGB"))[0].astype(float)
    band_h = cy1 - cy0 + 12
    band = Image.new("RGB", (w, band_h))
    for yy in range(band_h):
        t = yy / max(1, band_h - 1)
        band.paste(Image.fromarray((top * (1 - t) + bot * t).astype("uint8").reshape(1, w, 3)), (0, yy))
    canvas.paste(band, (0, cy0 - 6))
    return canvas


@lru_cache(maxsize=8)
def rounded_card(size, radius):
    w, h = size
    pad = 30
    layer = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    sh = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([pad, pad + 8, pad + w, pad + h + 8], radius, fill=(40, 70, 130, 70))
    layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(10)))
    ImageDraw.Draw(layer).rounded_rectangle([pad, pad, pad + w, pad + h], radius, fill=(255, 255, 255, 255),
                                            outline=(205, 214, 232, 255), width=2)
    return layer, pad


def layout_tokens(draw, toks, font, max_w):
    space = draw.textlength(" ", font=font)
    lines, cur, cur_w = [], [], 0
    for word, col in toks:
        if word == "\n":
            lines.append(cur)
            cur, cur_w = [], 0
            continue
        ww = draw.textlength(word, font=font)
        add = ww if not cur else space + ww
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [], 0
            add = ww
        cur.append((word, col, ww))
        cur_w += add
    lines.append(cur)
    return lines, space


def tokens_plain(text):
    toks = []
    for i, part in enumerate(text.split("\n")):
        if i:
            toks.append(("\n", None))
        toks += [(w, BLUE) for w in part.split()]
    return toks


def tokens_cta(key, rest):
    rest = rest.strip()
    if rest.endswith("."):
        rest = rest[:-1] + "!"
    toks = [("Пиши", BLUE), (f"«{key}»", ORANGE), ("\n", None), ("у", BLUE), ("дірект", BLUE), ("—", BLUE)]
    return toks + [(w, BLUE) for w in rest.split()]


def slide_word_count(paragraphs, idx, total):
    """Скільки слів на слайді (для анімації друку у відео)."""
    text = paragraphs[idx - 1]
    if idx == total:
        key, rest = split_cta(text)
        if key:
            return sum(1 for t in tokens_cta(key, rest) if t[0] != "\n")
    return sum(1 for t in tokens_plain(text) if t[0] != "\n")


def render(paragraphs, fmt, w, h, idx, total, reveal=None, scene=None, bob=0, progress=None):
    """Один слайд. Для відео: reveal = скільки слів уже видно (None = усі),
    scene = готовий фон із персонажем (кеш), bob = зсув персонажа в пікселях, progress = 0..1 заповнення смужки."""
    canvas = scene.copy() if scene is not None else build_scene(fmt, w, h)
    cx, cy, cw, ch = LAYOUT[fmt]["card"]
    if bob:  # персонаж злегка «дихає»: зсуваємо нижню частину сцени нижче картки
        ys = cy + ch + 15
        canvas.paste(canvas.crop((0, ys, w, h)), (0, ys + bob))
    layer, pad = rounded_card((cw, ch), 34)
    rgba = canvas.convert("RGBA")
    rgba.alpha_composite(layer, (cx - pad, cy - pad))
    canvas = rgba.convert("RGB")
    d = ImageDraw.Draw(canvas)
    if progress is not None:  # смужки прогресу як у сторіс
        seg_gap, seg_w = 10, (cw - 100 - 10 * (total - 1)) / total
        for i in range(total):
            sx = cx + 50 + i * (seg_w + seg_gap)
            d.rounded_rectangle([sx, cy + 22, sx + seg_w, cy + 30], 4, fill=(215, 223, 238))
            frac = 1 if i < idx - 1 else (progress if i == idx - 1 else 0)
            if frac > 0:
                d.rounded_rectangle([sx, cy + 22, sx + seg_w * frac, cy + 30], 4, fill=BLUE)

    text = paragraphs[idx - 1]
    is_first, is_last = idx == 1, idx == total
    rocket = None
    if is_last:
        key, rest = split_cta(text)
        if key:
            toks, kind = tokens_cta(key, rest), "cta"
            rocket = Image.open(TEMPLATE).convert("RGB").crop(TPL_ROCKET)
        else:
            toks, kind = tokens_plain(text), "body"
    elif is_first:
        toks, kind = tokens_plain(text), "hook"
    else:
        toks, kind = tokens_plain(text), "body"

    font_path = SEMI if kind == "body" else BOLD
    start, minimum = SIZES[kind]
    inner_w, top_pad, foot_h = cw - 100, 40, 90
    inner_h = ch - top_pad - foot_h
    size = start
    while size >= minimum:
        font = ImageFont.truetype(font_path, size)
        lines, space = layout_tokens(d, toks, font, inner_w)
        if len(lines) * size * 1.22 <= inner_h:
            break
        size -= 2
    font = ImageFont.truetype(font_path, size)
    lines, space = layout_tokens(d, toks, font, inner_w)
    lh = size * 1.22
    y = cy + top_pad + (inner_h - len(lines) * lh) / 2
    shown = 0
    n_words = sum(len(line) for line in lines)
    for li, line in enumerate(lines):
        line_w = sum(t[2] for t in line) + space * (len(line) - 1)
        rk_w = rk_h = 0
        if rocket is not None and li == len(lines) - 1:
            rk_h = round(size)
            rk_w = round(rocket.width * rk_h / rocket.height)
            line_w += space + rk_w
        x = cx + (cw - line_w) / 2
        for word, col, ww in line:
            if reveal is None or shown < reveal:
                d.text((x, y), word, font=font, fill=col)
            shown += 1
            x += ww + space
        if rk_w and (reveal is None or reveal >= n_words):
            canvas.paste(rocket.resize((rk_w, rk_h), Image.LANCZOS), (round(x), round(y + size * 0.05)))
        y += lh

    # підпис і лічильник усередині картки (поза зонами інтерфейсу TikTok)
    foot = ImageFont.truetype(SEMI, 32)
    fy = cy + ch - 58
    d.text((cx + 50, fy), "vPixselle", font=foot, fill=BLUE)
    counter = f"{idx}/{total}" + ("  →" if not is_last else "")
    d.text((cx + cw - 50 - d.textlength(counter, font=foot), fy), counter, font=foot, fill=MUTED)
    return canvas


def main():
    text, out_dir, prefix = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out_dir.mkdir(parents=True, exist_ok=True)
    for fmt, (w, h) in FORMATS.items():
        for i in range(1, len(paragraphs) + 1):
            img = render(paragraphs, fmt, w, h, i, len(paragraphs))
            img.save(out_dir / f"{prefix}_{fmt}_{i}.jpg", "JPEG", quality=90, subsampling=0)
    print(f"slides: {len(paragraphs)} per format -> {out_dir}")


if __name__ == "__main__":
    main()
