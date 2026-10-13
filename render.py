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
    (d / "caption.txt").write_text(make_caption(text), encoding="utf-8")
    make_video(d, slides, key)
    return n



# ---------- музика (власний синтез, без авторських прав) ----------

def make_music(path, seconds, seed):
    """Лоу-фай трек: акорди Am-F-C-G, бас, мелодія пентатонікою, ритм. Тональність і темп трохи залежать від ключа посту."""
    import wave
    sr = 44100
    rng = np.random.default_rng(seed)
    bpm = 84 + seed % 9
    shift = (seed // 9) % 5  # півтони вгору
    beat = 60.0 / bpm
    n = int(sr * seconds)
    t = np.arange(n) / sr
    out = np.zeros(n)

    def hz(midi):
        return 440.0 * 2 ** ((midi + shift - 69) / 12)

    def tone(freq, start, dur, amp, attack=0.02, decay=3.0, harm=(1.0, 0.35, 0.12)):
        i0 = int(start * sr)
        m = min(int(dur * sr), n - i0)
        if m <= 0:
            return
        tt = np.arange(m) / sr
        w = sum(a * np.sin(2 * np.pi * freq * (k + 1) * tt) for k, a in enumerate(harm))
        env = np.minimum(tt / attack, 1.0) * np.exp(-decay * tt)
        out[i0:i0 + m] += amp * w * env

    chords = [(45, [57, 60, 64]), (41, [53, 57, 60]), (48, [60, 64, 67]), (43, [55, 59, 62])]  # бас + акорд (MIDI)
    penta = [69, 72, 74, 76, 79, 81]
    bar = 4 * beat
    nbars = int(seconds / bar) + 1
    for b in range(nbars):
        bass, notes = chords[b % 4]
        t0 = b * bar
        for nt in notes:  # м'яка підкладка
            tone(hz(nt), t0, bar * 1.05, 0.09, attack=0.25, decay=0.6, harm=(1.0, 0.2))
        tone(hz(bass), t0, beat * 2.0, 0.22, attack=0.01, decay=2.2, harm=(1.0, 0.4))
        tone(hz(bass), t0 + beat * 2.5, beat * 1.4, 0.16, attack=0.01, decay=2.5, harm=(1.0, 0.4))
        for e in range(8):  # мелодія вісімками, не кожну
            if rng.random() < 0.55:
                tone(hz(int(rng.choice(penta))), t0 + e * beat / 2, beat * 1.5, 0.07, attack=0.005, decay=5.0)
        for q in range(4):  # ритм
            tq = t0 + q * beat
            i0 = int(tq * sr)
            m = min(int(0.25 * sr), n - i0)
            if m <= 0:
                continue
            tt = np.arange(m) / sr
            if q in (0, 2):  # бочка
                f = 50 + 70 * np.exp(-tt * 28)
                out[i0:i0 + m] += 0.35 * np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt * 14)
            else:  # снейр-шум
                out[i0:i0 + m] += 0.10 * rng.standard_normal(m) * np.exp(-tt * 22)
            for hh in (0, 0.5):  # хет
                j0 = int((tq + hh * beat) * sr)
                mm = min(int(0.05 * sr), n - j0)
                if mm > 0:
                    noise = rng.standard_normal(mm)
                    noise = np.diff(noise, prepend=0.0)  # прибрати низи
                    out[j0:j0 + mm] += 0.04 * noise * np.exp(-np.arange(mm) / sr * 70)
    # легке згладжування високих і нормалізація
    k = np.ones(3) / 3
    out = np.convolve(out, k, mode="same")
    out = out / (np.max(np.abs(out)) + 1e-9) * 0.6
    pcm = (np.clip(out, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


# ---------- підпис для TikTok ----------

HASHTAGS = "#vPixselle #маркетинг #інтернетмагазин #ecommerce #автоматизація"


def make_caption(text):
    """Підпис: опис (хук + суть) + заклик написати повідомлення з кодовим словом із фінального слайда + хештеги."""
    t = text.replace("\r\n", "\n").strip()
    paras = [p.strip() for p in re.split(r"\n\s*\n", t) if p.strip()] or [t]
    cta_idx = next((i for i in range(len(paras) - 1, -1, -1) if re.search("«[^»]+»", paras[i])), None)
    if cta_idx is not None:
        key = re.search("«([^»]+)»", paras[cta_idx]).group(1)
        rest = paras[cta_idx][re.search("«[^»]+»", paras[cta_idx]).end():].lstrip(" —-:").strip()
        body = "\n\n".join(paras[:cta_idx])
        cta = f"👉 Напиши мені в повідомлення слово «{key}»" + (f" — {rest}" if rest else "")
    else:
        body = "\n\n".join(paras[:-1]) if len(paras) > 1 else ""
        cta = "👉 " + paras[-1] if len(paras) > 1 else "👉 " + paras[0]
        if not body:
            cta = paras[0]
    cap = (body + "\n\n" if body else "") + cta + "\n\n" + HASHTAGS
    return cap[:2000]


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


def make_video(d, slides, key="0" * 8):
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
    own = ROOT / "music.mp3"  # власний трек: поклади music.mp3 у корінь репозиторію, і він замінить згенерований
    music = own if own.exists() else d / "_music.wav"
    if not own.exists():
        make_music(music, sum(durs) + xf + 1, int(key[:8], 16))
    cmd += ["-stream_loop", "-1", "-i", str(music)]
    parts = [f"[{i}:v]setsar=1,format=yuv420p[v{i}]" for i in range(len(durs))]
    last, acc = "v0", durs[0]
    for i in range(1, len(durs)):
        parts.append(f"[{last}][v{i}]xfade=transition=fade:duration={xf}:offset={acc:.2f}[x{i}]")
        last, acc = f"x{i}", acc + durs[i]
    total = acc + xf
    parts.append(f"[{len(durs)}:a]afade=t=in:d=0.6,afade=t=out:st={max(total - 1.8, 0):.2f}:d=1.8,volume=1.9,aformat=channel_layouts=stereo[a]")
    cmd += ["-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", "[a]",
            "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(d / "tt_video.mp4")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not own.exists():
        music.unlink(missing_ok=True)
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
