"""Рендер слайдів каруселей для постів із черги Threads (Google Sheets, опублікований як CSV).

Для кожного рядка зі статусом queued / ad:
  ключ = sha1(text.strip()) (це ж рахує Make: sha1(trim(text); "hex")),
  текст ділиться рівно на 4 слайди, кожному слайду своя поза персонажа,
  слайди зберігаються як site/c/<ключ>/ig_1..4.jpg (1080x1350) і tt_1..4.jpg (1080x1920).

Скрипт без стану: щоразу рендерить усі активні рядки заново (результат детермінований),
GitHub Pages публікує папку site/. Використання:
    python render.py <URL-або-шлях-CSV> [вихідна_папка]
"""
import csv
import hashlib
import io
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

import carousel_core as mc

ROOT = Path(__file__).resolve().parent
ACTIVE = {"queued", "ad"}
SLIDES = 4
SCALE = {"tiktok": 1.30, "instagram": 0.90}  # масштаб персонажа

# ролі поз: хук / середні слайди / фінальний слайд
POSES_HOOK = [("s2_p07_idea", 0), ("s2_p01_nav", 0), ("s2_p02_thumb", 0)]
POSES_MID = [("s2_p12_talk", 0), ("s2_p03_explain", 0), ("s2_p08_strategy", 0),
             ("s2_p06_hips", 0), ("s2_p15_growth", 0)]
POSES_END = [("s2_p04_point", -20), ("s2_p10_greet", 0)]  # p16_leader вимкнено: на вирізці лишився підпис «Лідерство»


def text_key(text: str) -> str:
    return hashlib.sha1(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()


# ---------- поділ тексту рівно на SLIDES слайдів ----------

def _sentences(t):
    return [x.strip() for x in re.split(r"(?<=[.!?…])\s+", t) if x.strip()]


def _split_once(t):
    """Ділить текст на дві частини: за реченнями, потім за розділовими знаками, потім за пробілом."""
    parts = _sentences(t)
    if len(parts) >= 2:
        best, best_d = 1, 10 ** 9
        for i in range(1, len(parts)):
            d = abs(len(" ".join(parts[:i])) - len(" ".join(parts[i:])))
            if d < best_d:
                best, best_d = i, d
        return " ".join(parts[:best]), " ".join(parts[best:])
    mid = len(t) // 2
    cands = [m.end() for m in re.finditer(r"(,|;|:| —| - )\s+", t)]
    cut = min(cands, key=lambda c: abs(c - mid)) if cands else None
    if cut is None or cut < 15 or len(t) - cut < 15:
        cut = t.rfind(" ", 0, mid) if t.rfind(" ", 0, mid) > 0 else mid
    a, b = t[:cut].strip(), t[cut:].strip()
    if re.search(r"[,;:—-]$", a):  # розрив посеред речення: ставимо «…» замість висячого знака
        a = a.rstrip(" ,;:—-") + "…"
        b = "…" + b
    return a, b


def _balance_middle(units, groups):
    """Ділить послідовність рядків на groups послідовних груп з близькою довжиною."""
    total = sum(len(u) for u in units)
    out, cur, acc = [], [], 0
    for i, u in enumerate(units):
        cur.append(u)
        acc += len(u)
        left_groups = groups - len(out) - 1
        left_units = len(units) - i - 1
        if left_groups > 0 and (acc >= total * (len(out) + 1) / groups or left_units <= left_groups):
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return out


def split_slides(text, n=SLIDES):
    text = text.replace("\r\n", "\n").strip()
    blocks = [b.strip().replace("\n", " ") for b in re.split(r"\n\s*\n", text) if b.strip()]
    if 3 <= len(blocks) <= n + 2 and len(blocks) >= 3:
        units = blocks
    else:  # без абзаців: одиниця = рядок (або речення)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        units = lines if len(lines) >= 3 else _sentences(text.replace("\n", " ")) or [text]
    if len(units) > n:  # перший і останній лишаються, середні зливаємо
        head, tail, mid = units[0], units[-1], units[1:-1]
        units = [head] + _balance_middle(mid, n - 2) + [tail]
    while len(units) < n:  # ділимо найдовший
        i = max(range(len(units)), key=lambda k: len(units[k]))
        if len(units[i]) < 40:
            break
        a, b = _split_once(units[i])
        units[i:i + 1] = [a, b]
    return units


# ---------- сцена: фон + персонаж ----------

_BG_CACHE = {}


def plain_bg(w, h):
    if (w, h) not in _BG_CACHE:
        tpl = np.array(Image.open(mc.TEMPLATE).convert("RGB")).astype(float)
        left = np.array(Image.fromarray(tpl[:, :3].mean(axis=1).astype("uint8").reshape(-1, 1, 3)).resize((1, h), Image.BILINEAR))[:, 0].astype(float)
        right = np.array(Image.fromarray(tpl[:, -3:].mean(axis=1).astype("uint8").reshape(-1, 1, 3)).resize((1, h), Image.BILINEAR))[:, 0].astype(float)
        t = np.linspace(0, 1, w)[None, :, None]
        _BG_CACHE[(w, h)] = Image.fromarray((left[:, None, :] * (1 - t) + right[:, None, :] * t).astype("uint8"))
    return _BG_CACHE[(w, h)].copy()


_POSE_CACHE = {}


def scene(fmt, w, h, pose, dx=0):
    bg = plain_bg(w, h)
    if (pose, fmt) not in _POSE_CACHE:
        p = Image.open(ROOT / f"sr_{pose}.png").convert("RGBA")
        k = SCALE[fmt]
        _POSE_CACHE[(pose, fmt)] = p.resize((round(p.width * k), round(p.height * k)), Image.LANCZOS)
    p = _POSE_CACHE[(pose, fmt)]
    bg.paste(p, (round((w - p.width) / 2 + dx), h - p.height), p)
    return bg


def pick_poses(key, n):
    """Пози для слайдів: хук, середні (різні між собою), фінал; зсув залежить від ключа, тож пости не повторюють один одного."""
    seed = int(key[:8], 16)
    hook = POSES_HOOK[seed % len(POSES_HOOK)]
    end = POSES_END[(seed // 7) % len(POSES_END)]
    mids = [POSES_MID[(seed // 3 + i) % len(POSES_MID)] for i in range(n - 2)]
    return [hook] + mids + [end]


def render_post(text, key, out_dir):
    slides = split_slides(text)
    n = len(slides)
    poses = pick_poses(key, n)
    d = out_dir / "c" / key
    d.mkdir(parents=True, exist_ok=True)
    for fmt, (w, h) in mc.FORMATS.items():
        prefix = "ig" if fmt == "instagram" else "tt"
        for i, (pose, dx) in enumerate(poses, 1):
            sc = scene(fmt, w, h, pose, dx)
            img = mc.render(slides, fmt, w, h, i, n, scene=sc)
            img.save(d / f"{prefix}_{i}.jpg", "JPEG", quality=88, subsampling=0, optimize=True)
    make_video(d, slides)
    return n


_FF = []


def find_ffmpeg():
    """ffmpeg з системи або (якщо нема) з pip-пакета imageio-ffmpeg — ставиться один раз за запуск."""
    if _FF:
        return _FF[0]
    path = shutil.which("ffmpeg")
    if not path:
        try:
            import imageio_ffmpeg
        except ImportError:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "imageio-ffmpeg"], check=False)
            try:
                import imageio_ffmpeg
            except ImportError:
                imageio_ffmpeg = None
        if imageio_ffmpeg:
            path = imageio_ffmpeg.get_ffmpeg_exe()
    _FF.append(path)
    return path


def make_video(d, slides):
    """Ролик 1080x1920 зі слайдів tt_N.jpg: плавні переходи, тривалість слайда залежить від довжини тексту, тиха аудіодоріжка."""
    ff = find_ffmpeg()
    if not ff:
        print("video skipped: ffmpeg not found")
        return False
    xf = 0.4
    durs = [max(3.5, min(7.0, 1.2 + 0.3 * len(s.split()))) for s in slides]
    cmd = [ff, "-y", "-loglevel", "error"]
    for i, dur in enumerate(durs, 1):
        cmd += ["-loop", "1", "-t", f"{dur + xf:.2f}", "-framerate", "25", "-i", str(d / f"tt_{i}.jpg")]
    cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    parts = [f"[{i}:v]setsar=1,format=yuv420p[v{i}]" for i in range(len(durs))]
    last, acc = "v0", durs[0]
    for i in range(1, len(durs)):
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={xf}:offset={acc:.2f}[x{i}]")
        last, acc = f"x{i}", acc + durs[i]
    total = acc + xf
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", f"{len(durs)}:a",
            "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k", "-shortest", "-movflags", "+faststart", str(d / "tt_video.mp4")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("video failed:", r.stderr[-300:])
    return r.returncode == 0


def load_rows(src):
    if re.match(r"^https?://", src):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig")
    else:
        raw = Path(src).read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def main():
    src = sys.argv[1]
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "site")
    out.mkdir(parents=True, exist_ok=True)
    (out / ".nojekyll").write_text("")
    (out / "index.html").write_text("<!doctype html><meta charset=utf-8><title>vPixselle carousels</title>")
    rows = load_rows(src)
    done, seen = 0, set()
    for r in rows:
        status = (r.get("status") or "").strip().lower()
        text = (r.get("text") or "").replace("\r\n", "\n").strip()
        if status not in ACTIVE or not text:
            continue
        key = text_key(text)
        if key in seen:
            continue
        seen.add(key)
        render_post(text, key, out)
        done += 1
    print(f"rendered posts: {done}")


if __name__ == "__main__":
    main()
