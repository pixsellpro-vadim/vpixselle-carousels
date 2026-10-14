#!/usr/bin/env python3
"""Ролики-пояснення для рекламних постів.

Як це працює (простими словами):
  1. Для рекламного тексту береться готовий сценарій з ad_scripts.json (яка сцена, які числа, що казати).
  2. Кожну фразу озвучує голос (Azure -> edge-tts -> якщо нічого немає, ролик без голосу).
     Довжина озвученої фрази задає темп анімації.
  3. Браузер (Playwright) відкриває explainer_scenes.html, кадр за кадром «перемотує» анімацію
     і робить знімок; ffmpeg збирає знімки + голос + музику в mp4 1080x1920.
  4. Результат: c/<ключ>/tt_video.mp4 (його вже бере Make) і ex_<версія>_<v|s>.mp4 (кеш на Pages).
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 25
CTA_LINE = "Хочете так само у своєму магазині? Пишіть у приватні повідомлення."
VOICE = os.environ.get("EX_VOICE", "uk-UA-PolinaNeural")
RATE = os.environ.get("EX_RATE", "+4%")
PAGES_BASE = os.environ.get("PAGES_BASE", "https://pixsellpro-vadim.github.io/vpixselle-carousels/")
GAP = 0.28          # пауза між фразами, с
LEAD = 0.35         # тиша перед першою фразою, с
TAIL = 1.0          # хвіст після останньої фрази, с


def norm(text):
    return re.sub(r"\s+", " ", text.replace("\r", " ")).strip().lower()


def script_key(text):
    return norm(text)[:48]


def version():
    h = hashlib.sha1()
    for n in ("explainer.py", "explainer_scenes.html", "ad_scripts.json"):
        p = HERE / n
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:8]


def load_scripts():
    p = HERE / "ad_scripts.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {script_key(a["match"]): a for a in data["ads"]}


def find_ffmpeg():
    for c in (shutil.which("ffmpeg"),):
        if c:
            return c
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def plain(s):
    return s.replace("*", "")


# Як озвучувати латинські назви (голос читає їх по-українськи, тож підказуємо вимову)
SPEAK = [("Google Shopping", "Гугл Шопінг"), ("Google", "Гугл"), ("Prom", "Пром"), ("Rozetka", "Розетка"),
         ("Horoshop", "Хорошоп"), ("Allegro", "Алегро"), ("Instagram", "Інстаграм"), ("Telegram", "Телеграм"),
         ("Viber", "Вайбер"), ("Make", "Мейк"), ("CRM", "сі-ар-ем"), ("SEO", "сео"), ("AI", "ШІ"),
         ("API", "ей-пі-ай"), ("→", " у "), ("грн", "гривень")]


def speak(s):
    s = plain(s)
    for a, b in SPEAK:
        s = re.sub(r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])", b, s)
    return s


# ---------------------------------------------------------------- голос

def synth_azure(text, path):
    key, reg = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION")
    if not key or not reg:
        return False
    ssml = (f"<speak version='1.0' xml:lang='uk-UA'><voice name='{VOICE}'>"
            f"<prosody rate='{RATE}'>{html.escape(text)}</prosody></voice></speak>")
    req = urllib.request.Request(
        f"https://{reg}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"),
        headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "vpixselle"})
    with urllib.request.urlopen(req, timeout=60) as r:
        Path(path).write_bytes(r.read())
    return Path(path).stat().st_size > 1000


def synth_edge(text, path):
    import asyncio
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))
    asyncio.run(go())
    return Path(path).exists() and Path(path).stat().st_size > 1000


def synth(text, path):
    """Повертає назву провайдера або None."""
    for name, fn in (("azure", synth_azure), ("edge", synth_edge)):
        try:
            if fn(text, path):
                return name
        except Exception as e:  # немає ключа / бібліотеки / мережі
            print(f"  voice {name}: {type(e).__name__}: {str(e)[:120]}")
    return None


def probe_voice():
    with tempfile.TemporaryDirectory() as td:
        return synth("Перевірка голосу.", Path(td) / "p.mp3")


def audio_len(path, ff):
    r = subprocess.run([ff, "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"time=(\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        return None
    h, mi, s = m[-1]
    return int(h) * 3600 + int(mi) * 60 + float(s)


def heur_len(text):
    return max(1.8, len(plain(text)) / 14.0 + 0.45)


# ---------------------------------------------------------------- таймінг

def clamp_refs(obj, last_body):
    """at/flipAt/atBefore/atAfter не можуть вказувати на заклик (останній рядок) або поза межі."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in ("at", "flipAt", "atBefore", "atAfter") and isinstance(v, int):
                obj[k] = max(0, min(v, last_body))
            else:
                clamp_refs(v, last_body)
    elif isinstance(obj, list):
        for v in obj:
            clamp_refs(v, last_body)


def plan(spec, workdir, ff, use_voice=True):
    """Повертає (lines, timeline, voice_files|None, total_seconds)."""
    lines = list(spec["lines"]) + [CTA_LINE]
    clamp_refs(spec["cfg"], len(lines) - 2)
    files, durs = [], []
    if use_voice:
        provider = None
        for i, ln in enumerate(lines):
            f = Path(workdir) / f"v{i}.mp3"
            p = synth(speak(ln), f)
            if not p:
                files = []
                break
            provider = p
            files.append(f)
            durs.append((audio_len(f, ff) or heur_len(ln)) + 0.2)
        if files:
            print(f"  voice: {provider}, {len(files)} lines")
    if not files:
        files = None
        durs = [heur_len(ln) for ln in lines]
    tl, t = [], LEAD
    for d in durs:
        tl.append({"t0": round(t, 3), "d": round(d, 3)})
        t += d + GAP
    total = tl[-1]["t0"] + tl[-1]["d"] + TAIL
    return lines, {"lines": tl}, files, total


def build_audio(files, tl, total, music, out, ff):
    """Голос по таймлайну + тиха музика -> wav."""
    cmd = [ff, "-y", "-loglevel", "error"]
    for f in files or []:
        cmd += ["-i", str(f)]
    nv = len(files or [])
    cmd += ["-stream_loop", "-1", "-i", str(music)]
    parts = []
    for i in range(nv):
        ms = int(tl["lines"][i]["t0"] * 1000)
        parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=mono,adelay={ms}|{ms}[a{i}]")
    if nv:
        parts.append("".join(f"[a{i}]" for i in range(nv)) +
                     f"amix=inputs={nv}:normalize=0:dropout_transition=0,loudnorm=I=-15:TP=-1.5:LRA=9,apad[voice]")
        parts.append(f"[{nv}:a]volume=0.34,aformat=channel_layouts=mono,afade=t=in:d=0.5,afade=t=out:st={max(total-1.5,0):.2f}:d=1.5[mus]")
        parts.append("[voice][mus]amix=inputs=2:normalize=0:duration=longest,aformat=channel_layouts=stereo[out]")
    else:
        parts.append(f"[{nv}:a]volume=1.6,afade=t=in:d=0.5,afade=t=out:st={max(total-1.8,0):.2f}:d=1.8,aformat=channel_layouts=stereo[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-t", f"{total:.2f}", "-ar", "44100", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("  audio failed:", r.stderr[-300:])
    return r.returncode == 0


# ---------------------------------------------------------------- запис кадрів

def launch(p):
    errs = []
    for kw in ({}, {"channel": "chrome"}, {"executable_path": shutil.which("google-chrome") or shutil.which("chromium") or ""}):
        if "executable_path" in kw and not kw["executable_path"]:
            continue
        try:
            return p.chromium.launch(args=["--no-sandbox", "--disable-gpu", "--font-render-hinting=none"], **kw)
        except Exception as e:
            errs.append(str(e)[:100])
    raise RuntimeError("browser not available: " + " | ".join(errs))


def capture(cfg, lines, tl, total, audio, out_mp4, ff, frames_dir=None, frame_times=None):
    from playwright.sync_api import sync_playwright
    spec_cfg = {"scene": cfg["scene"], "cfg": cfg["cfg"], "title": cfg.get("title"), "lines": lines}
    n = int(total * FPS)
    cmd = [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", str(FPS)]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    # без «edit list» і з moov на початку: так вимагає Instagram для Reels
    cmd += ["-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with sync_playwright() as p:
        br = launch(p)
        pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto((HERE / "explainer_scenes.html").as_uri())
        pg.evaluate("Promise.all([document.fonts.load('800 40px InterX'),document.fonts.load('600 40px InterX')])")
        pg.evaluate("([c,t])=>START(c,t)", [spec_cfg, tl])
        buf, shots = None, 0
        for i in range(n):
            t = i / FPS
            dirty = pg.evaluate("t=>seek(t)", t)
            if dirty or buf is None:
                buf = pg.screenshot(type="jpeg", quality=90)
                shots += 1
            proc.stdin.write(buf)
            if frames_dir and frame_times is not None and any(abs(t - ft) < 0.5 / FPS for ft in frame_times):
                (Path(frames_dir) / f"f_{t:05.2f}.jpg").write_bytes(buf)
        br.close()
    proc.stdin.close()
    proc.wait()
    print(f"  frames {n}, screenshots {shots}")
    return proc.returncode == 0


# ---------------------------------------------------------------- публічний інтерфейс

def render_spec(spec, out_mp4, make_music=None, seed=1, use_voice=True, frames_dir=None, frame_times=None):
    ff = find_ffmpeg()
    if not ff:
        print("explainer: ffmpeg not found")
        return None
    with tempfile.TemporaryDirectory() as td:
        lines, tl, files, total = plan(spec, td, ff, use_voice)
        music = Path(td) / "music.wav"
        if make_music:
            make_music(music, total + 1, seed)
        else:
            subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "5", str(music)])
        audio = Path(td) / "audio.wav"
        if not build_audio(files, tl, total, music, audio, ff):
            audio = None
        ok = capture(spec, lines, tl, total, audio, out_mp4, ff, frames_dir, frame_times)
    return {"ok": ok, "voiced": bool(files), "seconds": round(total, 1)} if ok else None


def make(text, key, d, make_music=None, voice_state=None, budget=None):
    """Для одного рекламного посту: кеш з Pages -> або новий рендер. Повертає True, якщо d/tt_video.mp4 замінено роликом."""
    scripts = load_scripts()
    spec = scripts.get(script_key(text))
    if not spec:
        return False
    ver = version()
    d = Path(d)
    # 1) кеш: голосова версія, а якщо голосу немає — беззвучна
    voice_ok = voice_state.get("ok") if voice_state else False
    names = [f"ex_{ver}_v.mp4"] + ([] if voice_ok else [f"ex_{ver}_s.mp4"])
    for nm in names:
        try:
            req = urllib.request.Request(f"{PAGES_BASE}c/{key}/{nm}", headers={"User-Agent": "vpixselle"})
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) > 50000:
                (d / nm).write_bytes(data)
                shutil.copyfile(d / nm, d / "tt_video.mp4")
                print(f"  explainer cached: {nm}")
                return True
        except Exception:
            pass
    # 2) ліміт нових рендерів за один запуск
    if budget is not None:
        if budget["left"] <= 0:
            print("  explainer: ліміт рендерів на цей запуск, лишаю відео зі слайдів")
            return False
        budget["left"] -= 1
    seed = int(key[:8], 16)
    tmp = d / "_ex.mp4"
    res = render_spec(spec, tmp, make_music, seed, use_voice=voice_ok)
    if not res:
        tmp.unlink(missing_ok=True)
        return False
    nm = f"ex_{ver}_{'v' if res['voiced'] else 's'}.mp4"
    shutil.move(str(tmp), d / nm)
    shutil.copyfile(d / nm, d / "tt_video.mp4")
    print(f"  explainer rendered: {nm} ({res['seconds']} s)")
    return True


if __name__ == "__main__":
    # тест: python explainer.py spec.json out.mp4 [--novoice] [--frames dir t1,t2,...]
    sp = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = sys.argv[2]
    nov = "--novoice" in sys.argv
    fd, ft = None, None
    if "--frames" in sys.argv:
        i = sys.argv.index("--frames")
        fd = sys.argv[i + 1]
        ft = [float(x) for x in sys.argv[i + 2].split(",")]
        Path(fd).mkdir(parents=True, exist_ok=True)
    mm = None
    try:
        sys.path.insert(0, os.environ.get("RENDER_DIR", "."))
        from render import make_music as mm  # noqa
    except Exception as e:
        print("no music:", e)
    print(render_spec(sp, out, mm, 5, use_voice=not nov, frames_dir=fd, frame_times=ft))
