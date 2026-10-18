#!/usr/bin/env python3
"""Шаблон B «Коментатор» для звичайних постів (Reels + TikTok): Вадим на фоні екранів-макетів,
маркерні позначки, великі субтитри, голос Ostap, без музики.

Вхід — «проста специфікація» від Claude (колонка C рядка reel), напр.:
  {"len":"short","hook":"Поки ви спите, *клієнти пишуть*","tag":"ДИРЕКТ ВНОЧІ",
   "lines":[{"t":"текст озвучки","bg":"dm|kanban|sheet|notifs|stat","items":["..",".."],"big":"КУПИЛИ"}, ...],
   "cta":"Хочете так само? Напишіть мені в приват слово «РОЗБІР»."}
expand() перетворює її на повну специфікацію рушія talk_scenes.html (фон, позначки, пози),
make() віддає готовий mp4 у d/tt_video.mp4 (кеш на Pages за версією шаблону).
"""
import hashlib, json, math, os, re, shutil, subprocess, sys, tempfile, urllib.request, wave
from pathlib import Path

import numpy as np

import explainer as E

HERE = E.HERE
W, H, FPS = E.W, E.H, E.FPS
LEAD = 1.0        # обкладинка (хук) до початку голосу
TAIL = 2.3        # кінцева картка
SR = 44100
HTML = "talk_scenes.html"
KEY_DEFAULT = "РОЗБІР"

NAMES = ["Олена", "Андрій", "Марина", "Ірина", "Олег", "Віктор"]
TIMES = ["23:12", "23:40", "00:05", "00:31", "07:50", "09:10"]
APPS = [("Директ", "linear-gradient(135deg,#F58529,#DD2A7B,#8134AF)"),
        ("CRM", "linear-gradient(135deg,#F5B301,#F58529)"),
        ("Сайт", "linear-gradient(135deg,#3B82F6,#1D4ED8)")]
POSES = ["ch_s3_talk", "ch_s2_present", "ch_s4_lean", "ch_s3_hips", "ch_s1_think", "ch_s4_pockets", "ch_s2_side", "ch_s3_tablet",
         "ch_s4_cross", "ch_s1_clasp", "ch_s3_cross"]


# ---------------------------------------------------------------- версія й розбір специфікації

def version():
    h = hashlib.sha1()
    for n in ("kinetic.py", HTML):
        p = HERE / n
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:8]


def parse_simple(text):
    """Текст із колонки C -> dict або None. Приймає JSON, у т.ч. в огорожі ```json."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    if not t.startswith("{"):
        return None
    try:
        d = json.loads(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.S)
        if not m:
            return None
        try:
            d = json.loads(m.group(0))
        except Exception:
            return None
    return d if isinstance(d, dict) and isinstance(d.get("lines"), list) else None


def clean(s, n=200):
    s = str(s or "")
    s = re.sub(r"[\U00010000-\U0010FFFF☀-➿️]", "", s)   # емодзі
    s = re.sub(r"\s+", " ", s).strip()
    if s.count("*") % 2:
        s = s.replace("*", "")
    return s[:n]


def price(seed, i):
    v = (int(seed[:6], 16) >> (i * 2)) % 40
    return f"{(8 + v) * 50:,}".replace(",", " ") + " грн"


def expand(simple, key="00000000"):
    """Проста специфікація -> повна специфікація рушія talk_scenes.html."""
    lines_in = [l for l in simple.get("lines", []) if isinstance(l, dict) and clean(l.get("t"))][:9]
    if len(lines_in) < 2:
        return None
    ckey = clean(simple.get("key"), 14).upper() or KEY_DEFAULT
    cta = clean(simple.get("cta"), 110) or f"Хочете так само? Напишіть мені в приват слово «{ckey}»."
    out_lines = []
    for i, l in enumerate(lines_in):
        t = clean(l.get("t"), 200)
        bg = str(l.get("bg") or "dm").lower()
        items = [clean(x, 40) for x in (l.get("items") or []) if clean(x, 40)][:5]
        marks, D = [], None
        if bg == "kanban" and items:
            cards = [{"col": 0, "t": NAMES[k], "s": items[k][:16]} for k in range(min(len(items), 4))]
            moves = [{"i": 0, "to": 1, "t": 1.6}]
            if len(cards) > 1:
                moves.append({"i": 1, "to": 2, "t": 2.8})
            if len(cards) > 2:
                cards[2]["col"] = 1
            D = {"type": "kanban", "cols": ["Нова заявка", "В роботі", "Оплачено"], "cards": cards, "moves": moves}
            marks = [{"t": 3.4, "type": "circle", "at": "col2"}]
        elif bg == "sheet" and items:
            rows = [{"n": items[k][:22], "p": price(key, k), "s": f"{(int(key[k:k + 2], 16) % 30) + 3} шт"} for k in range(len(items))]
            fix = [{"i": 0, "old": "", "new": price(key, 7), "t": 1.2}]
            if len(rows) > 1:
                fix.append({"i": 1, "old": "", "new": price(key, 9), "t": 2.2})
            D = {"type": "sheet", "rows": rows, "fix": fix}
            marks = [{"t": 0.9, "type": "circle", "at": "price0"}, {"t": 3.0, "type": "check", "at": "price1" if len(rows) > 1 else "price0"}]
        elif bg == "notifs" and items:
            its = [{"n": APPS[k % 3][0], "t": items[k], "ic": APPS[k % 3][1]} for k in range(len(items))]
            D = {"type": "notifs", "time": clean(l.get("time"), 6) or "23:12", "date": "сьогодні", "items": its}
            marks = [{"t": 1.8, "type": "arrow", "at": "n1" if len(its) > 1 else "n0", "dir": "l"}]
        elif bg == "stat" and l.get("num") is not None:
            try:
                num = int(float(str(l.get("num")).replace(" ", "").replace(",", ".")))
            except Exception:
                num = None
            if num is not None:
                D = {"type": "stat", "label": clean(l.get("label"), 40).upper(), "to": num, "unit": clean(l.get("unit"), 24),
                     "note": clean(l.get("note"), 40).upper() or "ПРИКЛАД", "color": "g" if l.get("good") else "r"}
                marks = [{"t": 2.2, "type": "underline", "at": "num"}]
        if D is None:   # dm — запасний варіант: пошук повідомлень у директі
            its = items or [t[:40]]
            rows = [{"n": NAMES[k % 6], "t": its[k], "time": TIMES[k % 6], "u": True} for k in range(len(its))]
            D = {"type": "dm", "rows": rows}
            if len(rows) >= 3:
                D["badge"] = len(rows)
                marks = [{"t": 1.4, "type": "circle", "at": "badge"}]
            else:
                marks = [{"t": 1.4, "type": "underline", "at": "row0"}]
        line = {"text": t, "bg": D, "marks": marks, "pose": POSES[(i * 3 + int(key[0], 16)) % len(POSES)] if i else "ch_s1_point"}
        big = clean(l.get("big"), 16)
        if big:
            fs = 130 if len(big) <= 8 else 100 if len(big) <= 12 else 80
            line["big"] = {"l": "", "v": big.upper(), "red": bool(l.get("bad", True)), "t": 1.5, "fs": fs, "w": 440}
        out_lines.append(line)
    # заклик: діалог із кодовим словом
    out_lines.append({"text": cta, "bg": {"type": "dm", "rows": [
        {"n": "Ви", "t": ckey, "time": "щойно", "u": True},
        {"n": "vPixselle", "t": "Привіт! Розкажу, що можна автоматизувати", "time": "щойно", "u": True}]},
        "pose": "ch_s4_welcome"})
    hook = clean(simple.get("hook"), 80) or out_lines[0]["text"]
    return {"engine": "talk", "html": HTML, "nomusic": True, "sfx_scale": 0.55, "hook": hook,
            "cover": {"tag": clean(simple.get("tag"), 28).upper()}, "end": {"key": ckey}, "lines": out_lines}


# ---------------------------------------------------------------- таймлайн та звук

def plan(spec, workdir, ff, use_voice=True):
    lines = [l["text"] for l in spec["lines"]]
    files, durs = [], []
    if use_voice:
        provider = None
        for i, ln in enumerate(lines):
            f = Path(workdir) / f"v{i}.mp3"
            rt, pt = E.prosody(i, len(lines), ln)
            p = E.synth(E.speak(ln), f, rt, pt)
            if not p:
                files = []
                break
            provider = p
            files.append(f)
            durs.append((E.audio_len(f, ff) or E.heur_len(ln)) + 0.2)
        if files:
            print(f"  voice: {provider}, {len(files)} lines")
    if not files:
        files = None
        durs = [max(1.8, len(E.plain(ln)) / 10.3 + 0.45) for ln in lines]
    tl, t = [], LEAD
    for i, d in enumerate(durs):
        tl.append({"t0": round(t, 3), "d": round(d, 3)})
        t += d + E.gap_after(lines[i], i == len(lines) - 2)
    total = tl[-1]["t0"] + tl[-1]["d"] + TAIL
    return lines, {"lines": tl}, files, total


def _env(n, a, d):
    x = np.arange(n) / SR
    return np.minimum(x / max(a, 1e-4), 1) * np.exp(-x / d)


def snd(kind):
    r = np.random.RandomState(7)
    if kind in ("whoosh", "whoosh2"):
        n = int(SR * (0.42 if kind == "whoosh" else 0.6))
        x = r.randn(n)
        c = np.linspace(0.02, 0.35, n) if kind == "whoosh" else np.linspace(0.03, 0.5, n)
        y = np.zeros(n)
        s = 0.0
        for i in range(n):
            s += c[i] * (x[i] - s)
            y[i] = s
        e = np.sin(np.linspace(0, math.pi, n)) ** 1.5
        return y * e * (0.9 if kind == "whoosh" else 1.2)
    if kind == "pop":
        n = int(SR * 0.14)
        f = np.linspace(760, 300, n)
        return np.sin(2 * math.pi * np.cumsum(f) / SR) * _env(n, .002, .035)
    if kind == "thud":
        n = int(SR * 0.5)
        f = np.linspace(110, 42, n)
        y = np.sin(2 * math.pi * np.cumsum(f) / SR) * _env(n, .002, .12)
        return y + r.randn(n) * _env(n, .001, .012) * .25
    if kind == "tick":
        n = int(SR * 0.06)
        return np.sin(2 * math.pi * 1900 * np.arange(n) / SR) * _env(n, .001, .012)
    if kind == "ding":
        n = int(SR * 0.7)
        t = np.arange(n) / SR
        return (np.sin(2 * math.pi * 1318 * t) + .5 * np.sin(2 * math.pi * 1976 * t)) * _env(n, .002, .16) * .7
    if kind == "rise":
        n = int(SR * 0.9)
        f = np.linspace(260, 980, n)
        return np.sin(2 * math.pi * np.cumsum(f) / SR) * np.sin(np.linspace(0, math.pi, n)) * .5
    return np.zeros(10)


GAIN = {"whoosh": .30, "whoosh2": .34, "pop": .30, "thud": .55, "tick": .16, "ding": .22, "rise": .18}


def build_sfx(events, total, path, scale=1.0):
    buf = np.zeros(int((total + 1) * SR) + SR)
    cache = {}
    for ev in events:
        k = ev["k"]
        if k not in GAIN or ev["t"] < 0:
            continue
        cache.setdefault(k, snd(k))
        s = cache[k] * GAIN[k] * scale
        i = int(ev["t"] * SR)
        buf[i:i + len(s)] += s[:len(buf) - i]
    buf = np.tanh(buf * 1.2) * 0.9
    pcm = (buf[:int(total * SR)] * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# ---------------------------------------------------------------- запис кадрів

def get_events(spec_cfg, tl):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        br = E.launch(p)
        pg = br.new_page(viewport={"width": W, "height": H})
        pg.goto((HERE / HTML).as_uri())
        pg.evaluate("Promise.all([document.fonts.load('800 40px InterX'),document.fonts.load('600 40px InterX')])")
        pg.evaluate("([c,t])=>START(c,t)", [spec_cfg, tl])
        pg.evaluate("window.READY")
        ev = pg.evaluate("window.EVENTS")
        br.close()
    return ev


def capture(spec_cfg, tl, total, audio, out_mp4, ff, frames_dir=None, frame_times=None):
    from playwright.sync_api import sync_playwright
    n = int(total * FPS)
    cmd = [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-r", str(FPS)]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)]   # так вимагає Instagram для Reels
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with sync_playwright() as p:
        br = E.launch(p)
        pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto((HERE / HTML).as_uri())
        pg.evaluate("Promise.all([document.fonts.load('800 40px InterX'),document.fonts.load('600 40px InterX')])")
        pg.evaluate("([c,t])=>START(c,t)", [spec_cfg, tl])
        pg.evaluate("window.READY")
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


def render_spec(spec, out_mp4, use_voice=True, frames_dir=None, frame_times=None):
    ff = E.find_ffmpeg()
    if not ff:
        print("kinetic: ffmpeg not found")
        return None
    with tempfile.TemporaryDirectory() as td:
        lines, tl, files, total = plan(spec, td, ff, use_voice)
        cfg = dict(spec)
        cfg["total"] = total
        cfg["cov_t"] = LEAD
        silent = Path(td) / "silent.wav"      # без музики: голос лежить на тиші, зверху тихі ефекти
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "5", str(silent)])
        a0 = Path(td) / "audio0.wav"
        audio = None
        if E.build_audio(files, tl, total, silent, a0, ff):
            audio = a0
            try:
                ev = get_events(cfg, tl)
                sfx = Path(td) / "sfx.wav"
                build_sfx(ev, total, sfx, spec.get("sfx_scale", 0.55))
                a1 = Path(td) / "audio.wav"
                r = subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(a0), "-i", str(sfx), "-filter_complex",
                                    "[0:a]aformat=channel_layouts=stereo[a];[1:a]aformat=channel_layouts=stereo[b];[a][b]amix=inputs=2:normalize=0:duration=first[o]",
                                    "-map", "[o]", "-t", f"{total:.2f}", str(a1)], capture_output=True, text=True)
                if r.returncode == 0:
                    audio = a1
                else:
                    print("  sfx mix failed:", r.stderr[-200:])
            except Exception as e:
                print("  sfx skipped:", str(e)[:150])
        ok = capture(cfg, tl, total, audio, out_mp4, ff, frames_dir, frame_times)
    return {"ok": ok, "voiced": bool(files), "seconds": round(total, 1)} if ok else None


# ---------------------------------------------------------------- інтерфейс для render.py

def make(text, key, d, make_music=None, voice_state=None, budget=None):
    """Рядок reel із JSON-сценарієм: кеш з Pages -> або новий рендер. True, якщо d/tt_video.mp4 готовий."""
    simple = parse_simple(text)
    if not simple:
        return False
    spec = expand(simple, key)
    if not spec:
        print("  kinetic: сценарій не пройшов перевірку")
        return False
    ver = version()
    d = Path(d)
    voice_ok = voice_state.get("ok") if voice_state else False
    names = [f"kx_{ver}_v.mp4"] + ([] if voice_ok else [f"kx_{ver}_s.mp4"])
    for nm in names:
        try:
            req = urllib.request.Request(f"{E.PAGES_BASE}c/{key}/{nm}", headers={"User-Agent": "vpixselle"})
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) > 50000:
                (d / nm).write_bytes(data)
                shutil.copyfile(d / nm, d / "tt_video.mp4")
                print(f"  kinetic cached: {nm}")
                return True
        except Exception:
            pass
    if budget is not None:
        if budget["left"] <= 0:
            print("  kinetic: ліміт рендерів на цей запуск")
            return False
        budget["left"] -= 1
    tmp = d / "_kx.mp4"
    res = render_spec(spec, tmp, use_voice=voice_ok)
    if not res:
        tmp.unlink(missing_ok=True)
        return False
    nm = f"kx_{ver}_{'v' if res['voiced'] else 's'}.mp4"
    shutil.move(str(tmp), d / nm)
    shutil.copyfile(d / nm, d / "tt_video.mp4")
    print(f"  kinetic rendered: {nm} ({res['seconds']} s)")
    return True


if __name__ == "__main__":
    # python kinetic.py spec.json out.mp4 [--novoice] [--frames dir t1,t2,...]
    # spec.json — повна специфікація (engine talk) або проста (з ключем "lines" без "html")
    sp = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if "html" not in sp:
        sp = expand(sp, hashlib.sha1(Path(sys.argv[1]).read_bytes()).hexdigest())
    out = sys.argv[2]
    nov = "--novoice" in sys.argv
    fd = ft = None
    if "--frames" in sys.argv:
        i = sys.argv.index("--frames")
        fd = sys.argv[i + 1]
        ft = [float(x) for x in sys.argv[i + 2].split(",")]
        Path(fd).mkdir(parents=True, exist_ok=True)
    print(render_spec(sp, out, use_voice=not nov, frames_dir=fd, frame_times=ft))
