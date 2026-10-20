"""Слайди каруселі у стилі «неонове письмо на склі»: темний фон із помаранчевим сяйвом,
реалістичний Вадим (вирізки ch_*.webp), рукописний текст із неоновим світінням,
кутові дужки, підкреслення від руки, підпис vPixselle і нік акаунта.

Інтерфейс як у carousel_core.render: render(slides, fmt, w, h, idx, total, pose) -> PIL.Image (RGB).
Усе детерміноване: один і той самий пост завжди дає ті самі слайди.
"""
import hashlib
import math
import random
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
HAND = str(ROOT / "Caveat-Bold.ttf")          # рукописний шрифт із кирилицею
BOLD = str(ROOT / "Inter-ExtraBold.otf")
SEMI = str(ROOT / "Inter-SemiBold.otf")

HANDLE = "@vadim.pixsell_service"
WHITE = (255, 246, 232)       # серцевина неону
ACCENT = (255, 150, 60)       # акцентні слова
GLOW = (255, 105, 20)         # колір світіння

# компонування: fig_scale/fig_top — персонаж; text — рамка тексту (x0, y0, x1, y1); bottom — рядок із ніком
LAYOUT = {
    "instagram": {"fig_scale": 1.5, "fig_top": 215, "fig_cx": 235, "fade_from": 0.60,
                  "text": (560, 300, 1036, 1150), "brand_y": 58, "bottom_y": 1296, "note_y": 118,
                  "size": {"hook": (104, 56), "body": (92, 50), "cta": (98, 52)}},
    "tiktok": {"fig_scale": 1.8, "fig_top": 330, "fig_cx": 235, "fade_from": 0.58,
               "text": (530, 430, 920, 1330), "brand_y": 130, "bottom_y": 1420, "note_y": 195,
               "size": {"hook": (112, 56), "body": (96, 50), "cta": (100, 52)}},
}
FORMATS = {"instagram": (1080, 1350), "tiktok": (1080, 1920)}

# пози: хук / середні / фінал; mirror=True: рука на вихідному фото тягнеться вліво, тож дзеркалимо
POSES_HOOK = ["s1_point", "s3_talk", "s2_present", "s4_welcome"]
POSES_MID = ["s1_think", "s3_hips", "s4_lean", "s4_pockets", "s3_cross", "s1_clasp", "s4_walk", "s1_walk"]
POSES_END = ["s4_welcome", "s3_talk", "s2_present", "s1_point"]
MIRROR = {"s1_point", "s2_present", "s4_welcome"}


def pick_poses(key, n):
    seed = int(key[:8], 16)
    hook = POSES_HOOK[seed % len(POSES_HOOK)]
    end_pool = [p for p in POSES_END if p != hook]
    end = end_pool[(seed // 7) % len(end_pool)]
    mid_pool = [p for p in POSES_MID if p not in (hook, end)]
    mids = [mid_pool[(seed // 3 + i * 2) % len(mid_pool)] for i in range(n - 2)]
    return [hook] + mids + [end]


# ---------- фон і персонаж ----------

def _screen(base, layer):
    return 255.0 - (255.0 - base) * (255.0 - layer) / 255.0


@lru_cache(maxsize=4)
def background(fmt):
    w, h = FORMATS[fmt]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.float32)
    img[:] = (9, 6, 5)

    def blob(cx, cy, rx, ry, col, k):
        d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
        a = np.exp(-d * 1.6)[..., None] * k
        return a * np.array(col, np.float32)

    img += blob(w * 1.02, h * 0.10, w * 0.95, h * 0.55, (205, 78, 14), 0.85)    # основне сяйво праворуч зверху
    img += blob(w * 0.86, h * 0.78, w * 0.70, h * 0.40, (150, 56, 10), 0.40)    # м'яке сяйво під текстом
    img += blob(w * 0.05, h * 0.55, w * 0.50, h * 0.50, (60, 28, 10), 0.22)     # тепла підсвітка зліва
    # діагональна смуга відблиску, як на склі
    diag = np.exp(-(((xx + yy * 0.55) - w * 0.95) / 90.0) ** 2)[..., None] * np.array((255, 140, 60), np.float32) * 0.045
    img += diag
    vx = ((xx - w / 2) / (w / 2)) ** 2
    vy = ((yy - h / 2) / (h / 2)) ** 2
    img *= (1 - 0.42 * (vx * 0.6 + vy * 0.8))[..., None]
    rng = np.random.default_rng(7)
    img += rng.normal(0, 2.2, (h, w, 1)).astype(np.float32)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


@lru_cache(maxsize=4)
def _logo(width):
    lg = Image.open(ROOT / "logo_pixsell.png").convert("RGBA")
    return lg.resize((width, round(lg.height * width / lg.width)), Image.LANCZOS)


@lru_cache(maxsize=64)
def figure_layer(fmt, pose):
    """Персонаж на прозорому тлі: збільшений, тонований під сцену, з помаранчевою контражурною підсвіткою
    праворуч і з розчиненням у темряві знизу. Повертає (RGBA-шар на весь кадр)."""
    w, h = FORMATS[fmt]
    L = LAYOUT[fmt]
    p = Image.open(ROOT / f"ch_{pose}.webp").convert("RGBA")
    if pose in MIRROR:
        p = p.transpose(Image.FLIP_LEFT_RIGHT)
    k = L["fig_scale"]
    p = p.resize((round(p.width * k), round(p.height * k)), Image.LANCZOS)
    p = p.filter(ImageFilter.UnsharpMask(radius=1.6, percent=70, threshold=2))
    al = p.getchannel("A").filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(1.1))
    p.putalpha(al)
    a = np.array(p).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3] / 255.0

    # тон: трохи темніше й тепліше, вертикальний градієнт світла
    hh, ww = alpha.shape
    gx = np.linspace(0.68, 0.98, ww)[None, :, None]
    rgb = rgb * gx * np.array((1.0, 0.93, 0.86), np.float32)
    # контражур праворуч: край, де праворуч від пікселя прозоро
    dx = max(6, round(8 * k / 1.65))
    shifted = np.roll(alpha, -dx, axis=1)
    shifted[:, -dx:] = 0
    rim = np.clip(alpha - shifted, 0, 1)
    rim = np.array(Image.fromarray((rim * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3.2))).astype(np.float32) / 255.0
    rgb = _screen(rgb, rim[..., None] * np.array((255, 125, 35), np.float32) * 0.95)
    layer = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alpha * 255]).astype(np.uint8), "RGBA")

    pad = 400  # запас, щоб поза за краєм кадру не ламала вставку
    big = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    x = round(L["fig_cx"] - ww * 0.42)
    x = max(-int(ww * 0.12), min(x, 560 - ww // 2))
    y = L["fig_top"]
    big.alpha_composite(layer, (x + pad, y + pad))
    out = big.crop((pad, pad, pad + w, pad + h))
    # розчинення в темряві знизу
    arr = np.array(out).astype(np.float32)
    ys_full = np.arange(h, dtype=np.float32)[:, None]
    start = h * L["fade_from"]
    arr[..., 3] *= np.clip(1 - (ys_full - start) / (h * 0.99 - start), 0, 1) ** 1.3
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


@lru_cache(maxsize=64)
def base_scene(fmt, pose):
    bg = background(fmt).convert("RGBA")
    bg.alpha_composite(figure_layer(fmt, pose))
    return bg.convert("RGB")


# ---------- текст ----------

def _tokens(text, last=False):
    """Слова з позначкою акценту: «ключ» і числа — помаранчеві. Для CTA додаємо перенос після ключа."""
    toks = []
    m = re.search(r"«([^»]+)»", text) if last else None
    if m:
        rest = text[m.end():].lstrip(" —-").strip()
        if rest.endswith("."):
            rest = rest[:-1] + "!"
        toks = [("Пиши", False), (f"«{m.group(1)}»", True), ("\n", False), ("у", False), ("дірект", False), ("—", False)]
        toks += [(w, False) for w in rest.split()]
        return toks
    for i, part in enumerate(text.split("\n")):
        if i:
            toks.append(("\n", False))
        for w in part.split():
            accent = bool(re.match(r"^[«\"]", w)) or bool(re.search(r"\d", w))
            toks.append((w, accent))
    return toks


def _layout(draw, toks, font, max_w):
    space = draw.textlength(" ", font=font) * 0.9
    lines, cur, cur_w = [], [], 0.0
    for word, acc in toks:
        if word == "\n":
            lines.append(cur)
            cur, cur_w = [], 0.0
            continue
        ww = draw.textlength(word, font=font)
        add = ww if not cur else space + ww
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w, add = [], 0.0, ww
        cur.append((word, acc, ww))
        cur_w += add
    if cur:
        lines.append(cur)
    return lines, space


def _bezier(p0, p1, p2, n=40):
    pts = []
    for i in range(n + 1):
        t = i / n
        pts.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t ** 2 * p2[0],
                    (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t ** 2 * p2[1]))
    return pts


def _stroke(draw, pts, width):
    draw.line(pts, fill=255, width=width, joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=255)


def _arrow(draw, x, y, length, col, width=4):
    """Рукописна стрілка вправо, що закінчується в (x + length, y)."""
    draw.line([(x, y), (x + length, y)], fill=col, width=width)
    draw.line([(x + length - 16, y - 12), (x + length, y), (x + length - 16, y + 12)], fill=col, width=width, joint="curve")


def _spaced(draw, xy, text, font, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing
    return x


def _blur(mask, r):
    return np.array(mask.filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255.0


def render(slides, fmt, w, h, idx, total, pose, key="0" * 8):
    L = LAYOUT[fmt]
    rnd = random.Random(int(hashlib.sha1((key + str(idx)).encode()).hexdigest()[:8], 16))
    canvas = base_scene(fmt, pose).copy()
    text = slides[idx - 1]
    is_first, is_last = idx == 1, idx == total
    kind = "hook" if is_first else ("cta" if (is_last and "«" in text) else "body")
    toks = _tokens(text, last=is_last)

    x0, y0, x1, y1 = L["text"]
    tw, th = x1 - x0, y1 - y0
    probe = ImageDraw.Draw(Image.new("L", (10, 10)))
    start, minimum = L["size"][kind]
    size = start
    while size >= minimum:
        font = ImageFont.truetype(HAND, size)
        lines, space = _layout(probe, toks, font, tw - 20)
        if len(lines) * size * 0.98 <= th - 30:
            break
        size -= 2
    font = ImageFont.truetype(HAND, size)
    lines, space = _layout(probe, toks, font, tw - 20)
    n_lines = len(lines)
    lo, hi = 120, tw - 20  # вирівнювання переносів: найвужча ширина, при якій рядків лишається стільки ж
    while hi - lo > 6:
        mid_w = (lo + hi) // 2
        if len(_layout(probe, toks, font, mid_w)[0]) <= n_lines:
            hi = mid_w
        else:
            lo = mid_w
    lines, space = _layout(probe, toks, font, hi)
    lh = size * 0.98
    block_h = len(lines) * lh
    top = y0 + (th - block_h) / 2

    # маски: звичайний текст, акценти, декор
    m_norm = Image.new("L", (w, h), 0)
    m_acc = Image.new("L", (w, h), 0)
    m_dec = Image.new("L", (w, h), 0)
    dn, da, dd = ImageDraw.Draw(m_norm), ImageDraw.Draw(m_acc), ImageDraw.Draw(m_dec)

    minx, maxx = w, 0
    last_line_box = None
    for li, line in enumerate(lines):
        line_w = sum(t[2] for t in line) + space * (len(line) - 1)
        lay_w, lay_h = int(line_w + 80), int(size * 1.6)
        ln, la = Image.new("L", (lay_w, lay_h), 0), Image.new("L", (lay_w, lay_h), 0)
        dln, dla = ImageDraw.Draw(ln), ImageDraw.Draw(la)
        xx = 40
        for word, acc, ww in line:
            (dla if acc else dln).text((xx, size * 0.15), word, font=font, fill=255)
            xx += ww + space
        ang = rnd.uniform(-1.6, 1.2)
        ln = ln.rotate(ang, resample=Image.BICUBIC, expand=False)
        la = la.rotate(ang, resample=Image.BICUBIC, expand=False)
        px = round(x0 + 10 - 40 + rnd.uniform(0, 10))
        py = round(top + li * lh - size * 0.15)
        m_norm.paste(ln, (px, py), ln)
        m_acc.paste(la, (px, py), la)
        minx, maxx = min(minx, px + 40), max(maxx, px + 40 + line_w)
        if li == len(lines) - 1:
            last_line_box = (px + 40, py + size * 0.15, line_w, size)

    # підкреслення двома штрихами під останнім рядком (як у референсі)
    bx, by, bw, bh = last_line_box
    base_y = by + bh * 0.98
    _stroke(dd, _bezier((bx - 6, base_y + 6), (bx + bw * 0.5, base_y - 14), (bx + bw + 8, base_y + 2)), 6)
    _stroke(dd, _bezier((bx + bw * 0.18, base_y + 30), (bx + bw * 0.55, base_y + 16), (bx + bw * 0.86, base_y + 26)), 5)

    # кутові дужки (правий верх і лівий низ), як рамка кадру на склі
    pad = 38
    bx0, by0 = minx - pad, top - pad + 6
    bx1, by1 = min(maxx + pad, w - 34), top + block_h + pad + 34
    arm = 92
    bw_ = 8
    dd.line([(bx1 - arm, by0), (bx1, by0), (bx1, by0 + arm)], fill=255, width=bw_, joint="curve")
    dd.line([(bx0, by1 - arm), (bx0, by1), (bx0 + arm, by1)], fill=255, width=bw_, joint="curve")

    # неонове складання: тінь -> світіння -> серцевина
    arr = np.array(canvas).astype(np.float32)
    all_mask = Image.new("L", (w, h), 0)
    all_mask = Image.fromarray(np.maximum(np.maximum(np.array(m_norm), np.array(m_acc)), np.array(m_dec)))
    shadow = _blur(all_mask.transform(all_mask.size, Image.AFFINE, (1, 0, 0, 0, 1, -8)), 16)
    arr *= (1 - 0.62 * shadow)[..., None]
    glow_col = np.array(GLOW, np.float32)
    for r, k in ((50, 0.55), (20, 0.8), (7, 0.9)):
        g = _blur(all_mask, r)[..., None] * glow_col * k
        arr = _screen(arr, g)
    # серцевина
    for mask, col in ((m_dec, ACCENT), (m_acc, ACCENT), (m_norm, WHITE)):
        a = (np.array(mask).astype(np.float32) / 255.0)[..., None]
        arr = arr * (1 - a) + np.array(col, np.float32) * a
    canvas = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # верхній підпис, примітка від руки, нижній рядок
    d = ImageDraw.Draw(canvas, "RGBA")
    by_ = L["brand_y"]
    logo = _logo(300)  # логотип pixsell marketing (PNG з прозорим тлом) замість тексту vPixselle
    canvas.paste(logo, (54, by_ - 12), logo)
    d = ImageDraw.Draw(canvas, "RGBA")

    note = "Свайп далі" if not is_last else "Ваш хід"
    f_note = ImageFont.truetype(HAND, 50)
    nw = d.textlength(note, font=f_note)
    nx, ny = w - 60 - nw, L["note_y"]
    arrow_w = 0 if is_last else 58
    nx -= arrow_w
    d.text((nx, ny), note, font=f_note, fill=(255, 255, 255, 235))
    if arrow_w:
        _arrow(d, nx + nw + 12, ny + 34, arrow_w - 12, (255, 255, 255, 235))
    ul = Image.new("L", (w, h), 0)
    _stroke(ImageDraw.Draw(ul), _bezier((nx - 4, ny + 62), (nx + nw * 0.5, ny + 50), (nx + nw + arrow_w, ny + 60)), 5)
    ul_a = np.array(ul).astype(np.float32)[..., None] / 255.0
    arr = np.array(canvas).astype(np.float32)
    arr = arr * (1 - ul_a) + np.array(ACCENT, np.float32) * ul_a
    canvas = Image.fromarray(arr.astype(np.uint8))

    d = ImageDraw.Draw(canvas, "RGBA")
    by2 = L["bottom_y"]
    f_h = ImageFont.truetype(SEMI, 30)
    d.text((60, by2), HANDLE, font=f_h, fill=(255, 255, 255, 235))
    hw = d.textlength(HANDLE, font=f_h)
    d.line([(60 + hw + 24, by2 + 20), (w - 60, by2 + 20)], fill=(255, 140, 50, 255), width=3)
    counter = f"{idx}/{total}"
    f_c = ImageFont.truetype(HAND, 46)
    cw_ = d.textlength(counter, font=f_c)
    shift = 0 if is_last else 54
    d.text((w - 60 - cw_ - shift, by2 - 50), counter, font=f_c, fill=(255, 190, 120, 255))
    if not is_last:
        _arrow(d, w - 60 - 46, by2 - 20, 40, (255, 190, 120, 255), 4)
    return canvas
