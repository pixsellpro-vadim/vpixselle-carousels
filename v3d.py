#!/usr/bin/env python3
"""3D-ролики для звичайних (не рекламних) постів Instagram Reels / TikTok.

Текст посту -> розкадрування (сцени за ключовими словами) -> голос (edge-tts / Azure) -> 3D-рендер у headless-Chromium
(three.js, v3d_engine.html + human.js) -> mp4 1080x1920, який лягає в d/tt_video.mp4 (його беруть Make і Zernio).
Вмикається файлом v3d_on.txt у корені репозиторію. Без нього, без npm/Chromium або при будь-якій помилці лишається відео зі слайдів.
"""
import hashlib
import html
import http.server
import io
import json
import math
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 25
VOICES = [v for v in os.environ.get("V3D_VOICE", "uk-UA-OstapNeural,uk-UA-PolinaNeural").split(",") if v]
RATE = os.environ.get("V3D_RATE", "+0%")
PAGES_BASE = os.environ.get("PAGES_BASE", "https://pixsellpro-vadim.github.io/vpixselle-carousels/")
LABEL = "vPIXSELLE"
LEAD, TAIL, MIN_CH = 0.40, 0.55, 3.2
MAX_TOTAL = 85.0          # довші ролики не рендеримо
T_START = time.time()
MAX_MIN = float(os.environ.get("V3D_MAX_MIN", "75"))   # після цього нових рендерів у запуску не починаємо
NPM_DEPS = ["three@0.160.0", "@fontsource/oswald@5", "@fontsource/exo-2@5", "@fontsource/inter@5"]
STATE = {"broken": False}


# ------------------------------------------------------------------ утиліти
def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def version():
    h = hashlib.sha1()
    for n in ("v3d.py", "v3d_engine.html", "human.js"):
        p = HERE / n
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:8]


def ensure_deps():
    """three.js і шрифти ставляться з npm у корінь (один раз за запуск)."""
    if (HERE / "node_modules" / "three" / "build" / "three.module.js").exists() and \
            (HERE / "node_modules" / "@fontsource" / "oswald" / "cyrillic-700.css").exists():
        return True
    npm = shutil.which("npm")
    if not npm:
        print("  v3d: npm не знайдено")
        return False
    r = subprocess.run([npm, "install", "--no-audit", "--no-fund", "--silent", "--no-save", *NPM_DEPS], cwd=HERE,
                       capture_output=True, text=True, timeout=300)
    ok = (HERE / "node_modules" / "three" / "build" / "three.module.js").exists()
    if not ok:
        print("  v3d: npm install не вдалося:", (r.stderr or r.stdout)[-300:])
    return ok


# ------------------------------------------------------------------ текст -> розкадрування
CTA_RE = re.compile(r"(підпиш|лайк|коментар|приват|напишіть|пишіть)", re.I)
STOP = set("""це що як але для його вона вони воно вже ще так тому коли якщо тільки також цей ця ці той та то ти ви ми вас вам вами ваш ваші вашого
        наступне наступний наступна тоді такий такі такої цього цьому свій свої себе можна треба буде було були бути більше менше саме просто навіть через після перед який яка яке які чому тут там""".split())

RULES = [  # (назва, regex по тексту розділу в нижньому регістрі, сцена)
    ("signs", r"ознак", "signs"),
    ("card", r"картк|переписк|запис[аа-я]*ться|запишеться|записа", "card"),
    ("remind", r"нагадуван|нагадат|закінчу|закінчив|порожн|спорожніл|шукає заміну", "remind"),
    ("same", r"однаков|всім шлють|усім шлють|всім летить|усім летить|усім приходить|всім приходить|одна й та сама", "same"),
    ("auto", r"вручну|автоматичн|саме запишеться|саме зробить|без вашої участі|за вас", "s8"),
    ("night", r"вечор|увечері|вночі|\bніч|пізно|десят(ій|ої)", "s3"),
    ("morning", r"наступного (ранку|дня)|вранці|уранці|до ранку|наступного", "s4"),
    ("compet", r"деінде|конкурент|в іншому магазині|купила там|купив там", "s5"),
    ("price", r"не через ціну|не про ціну|не в ціні|не ціна|ціна|ціну", "s6"),
    ("exp", r"10\+|10 років|десять років|досвід|років в ?іт", "s7"),
    ("typical", r"типов|будь-якої (години|пори)|миттєв|швидк", "s8"),
    ("complex", r"складн|разом з (усією )?історі", "s9"),
    ("silent", r"мовч|тиш[іау]|не пише|не питає|не відкриває|не читає|не відповів|не відповіда|ніхто не", "silent"),
    ("leave", r"не повертаються|не повернул|не повернут|йдуть|\bіде\b|втрат|втрача|забул|пішл|покинул|зникла|зникає", "s1"),
    ("community", r"спільнот|підписник", "community"),
    ("stays", r"не доводиться|повторювати|пояснювати|відчуває|пам'ятають|пам’ятають|повертається|залишається", "s10"),
]

HEADS = {  # сцена -> варіанти (kicker, заголовок з [акцентом])
    "s1": [("КЛІЄНТИ", "КЛІЄНТ [ЙДЕ] ТИХО"), ("ПРОБЛЕМА", "ТОВАР Є, А [КЛІЄНТА] НЕМАЄ")],
    "s2": [("ОЧІКУВАННЯ", "КЛІЄНТ [ЧЕКАЄ]")],
    "s3": [("ВЕЧІР", "ПИТАННЯ [ВНОЧІ]"), ("НІЧ", "ВИ [СПИТЕ], А КЛІЄНТ ПИТАЄ")],
    "s4": [("ЧАС", "ПОКИ ВИ [ЧЕКАЄТЕ РАНКУ]"), ("ПАУЗА", "ВІДПОВІДЬ [ЗАПІЗНИЛАСЯ]")],
    "s5": [("КОНКУРЕНТ", "КУПИЛИ [ДЕІНДЕ]"), ("РИЗИК", "КЛІЄНТ ВЖЕ [У КОНКУРЕНТА]")],
    "s6": [("ВИСНОВОК", "НЕ ПРО ЦІНУ. ПРО [ЧАС]")],
    "s7": [("ДОСВІД", "[10+] РОКІВ В ІТ")],
    "s8": [("АВТОМАТИЗАЦІЯ", "[РОБОТ] ПРАЦЮЄ ЗА ВАС"), ("РІШЕННЯ", "ВІДПОВІДЬ [ЗА СЕКУНДИ]")],
    "s9": [("ВАЖЛИВЕ", "[СКЛАДНЕ] — ДО ВАС"), ("ЛЮДИНА", "СКЛАДНЕ ПИТАННЯ — [ДО ВАС]")],
    "s10": [("РЕЗУЛЬТАТ", "КЛІЄНТ [ЛИШАЄТЬСЯ]"), ("РЕЗУЛЬТАТ", "ЛЮДИНУ [ПАМ'ЯТАЮТЬ]")],
    "card": [("КАРТКА КЛІЄНТА", "УСЕ В ОДНІЙ [КАРТЦІ]")],
    "remind": [("НАГАДУВАННЯ", "ВЧАСНЕ [НАГАДУВАННЯ]"), ("МОМЕНТ", "КОЛИ ТОВАР [ЗАКІНЧУЄТЬСЯ]")],
    "signs": [("ОЗНАКИ", "[ОЗНАКИ] ВТРАТИ КЛІЄНТА")],
    "same": [("РОЗСИЛКА", "ОДНАКОВА ДЛЯ [ВСІХ]"), ("ПРОБЛЕМА", "ШАБЛОН ДЛЯ [ВСІХ]")],
    "silent": [("ТИША", "КЛІЄНТ [МОВЧИТЬ]"), ("ТИША", "[НІХТО] НЕ ПИШЕ")],
    "community": [("СПІЛЬНОТА", "СВОЇ [КЛІЄНТИ]")],
}
CTA_HEADS = {"♥": ("ДАЛІ", "СТАВТЕ [ЛАЙК]"), "+": ("ДАЛІ", "[ПІДПИШІТЬСЯ]"), "?": ("ДАЛІ", "ПИШІТЬ У [КОМЕНТАРЯХ]"), "✉": ("ДАЛІ", "ПИШІТЬ У [ПРИВАТ]")}


def clean(text):
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"\([^)]*\)", "", t)  # дужки (джерела, уточнення)

    def quote(m):
        s = m.group(1)
        lat = len(re.findall(r"[A-Za-z]", s))
        return "" if lat > max(3, len(s) * 0.4) else m.group(0)
    t = re.sub(r"«([^»]*)»", quote, t)
    t = re.sub(r"[\U0001F000-\U0001FFFF☀-➿️]", "", t)  # емодзі
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+([,.!?:;])", r"\1", t)
    return t.strip()


def split_sentences(text):
    out = []
    for line in clean(text).split("\n"):
        line = line.strip()
        if not line:
            continue
        for s in re.split(r"(?<=[.!?…])\s+(?=[«\"“A-ZА-ЯІЇЄҐ0-9])", line):
            s = s.strip(" ,;")
            if len(re.findall(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", s)) >= 3:
                out.append(s)
    return out


def group(sents, max_ch=8):
    chs = []
    for s in sents:
        if chs and len(chs[-1]) < 46 and len(chs[-1]) + 1 + len(s) <= 150:
            chs[-1] += " " + s
        else:
            chs.append(s)
    while len(chs) > max_ch:  # зливаємо найкоротшу пару сусідів
        i = min(range(len(chs) - 1), key=lambda k: len(chs[k]) + len(chs[k + 1]))
        chs[i] += " " + chs.pop(i + 1)
    return chs


VERB_END = ("тиме", "атиме", "ятиме", "ться", "ть", "ете", "ите", "ємо", "имо", "ють", "уть", "ять", "ати", "яти", "ити", "ала", "ила", "али", "или", "ався", "лася", "лися")


def keyword(text):
    """Одне слово-акцент для сцени 'think': не дієслово, 4-10 літер, без обрізання."""
    words = [w for w in re.findall(r"[А-Яа-яІіЇїЄєҐґ'’]+", text) if 4 <= len(w) <= 10]
    ok = [w for w in words if w.lower() not in STOP and not w.lower().endswith(VERB_END)]
    if not ok:
        ok = [w for w in words if w.lower() not in STOP]
    if not ok:
        return "ГОЛОВНЕ"
    return max(ok, key=lambda x: (-abs(len(x) - 7), -ok.index(x))).upper()


def cta_glyph(s):
    low = s.lower()
    if "лайк" in low:
        return "♥"
    if "підпиш" in low:
        return "+"
    if "коментар" in low:
        return "?"
    return "✉"


def storyboard(text, seed=0):
    """-> {"label","chapters":[{scene,args,kicker,head,text}]} або None, якщо тексту замало."""
    sents = split_sentences(text)
    if len(sents) < 3:
        return None
    cta = None
    if CTA_RE.search(sents[-1]) and len(sents[-1]) < 140:
        cta = sents.pop()
    body = group(sents, 7 if cta else 8)
    chapters, prev, used, think_n = [], None, {}, 0
    for i, ct in enumerate(body):
        low = ct.lower()
        cands = [sc for _, rx, sc in RULES if re.search(rx, low)]
        pick = next((c for c in cands if c != prev and used.get(c, 0) < 2), None)
        args = {}
        if pick is None:
            pick = "think"
            think_n += 1
            args = {"word": keyword(ct), "flip": think_n % 2 == 0}
            if prev == "think":
                args["flip"] = not (chapters[-1]["args"].get("flip", False))
            kick, head = "ГОЛОВНЕ", f"[{args['word']}]"
        else:
            hv = HEADS[pick]
            kick, head = hv[(seed + i) % len(hv)]
        used[pick] = used.get(pick, 0) + 1
        prev = pick
        chapters.append({"scene": pick, "args": args, "kicker": kick, "head": head, "text": ct})
    if cta:
        g = cta_glyph(cta)
        kick, head = CTA_HEADS[g]
        chapters.append({"scene": "s11", "args": {"glyph": g}, "kicker": kick, "head": head, "text": cta})
    return {"label": LABEL, "chapters": chapters}


def sub_chunks(text, max_chars=30, max_words=4):
    """Субтитри: 2-4 слова, розрив бажано на розділовому знаку."""
    words = text.replace("«", "").replace("»", "").split()
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        s = " ".join(cur)
        end = w[-1] in ",.:;!?…—"
        if len(cur) >= max_words or len(s) >= max_chars or (end and len(cur) >= 2):
            chunks.append(s)
            cur = []
    if cur:
        if chunks and len(cur) == 1 and len(chunks[-1]) + 1 + len(cur[0]) <= max_chars + 6:
            chunks[-1] += " " + cur[0]
        else:
            chunks.append(" ".join(cur))
    return chunks


# ------------------------------------------------------------------ голос
SPEAK = [("Google Shopping", "Гугл Шопінг"), ("Google", "Гугл"), ("Prom", "Пром"), ("Rozetka", "Розетка"), ("Horoshop", "Хорошоп"),
         ("Instagram", "Інстаграм"), ("Telegram", "Телеграм"), ("Viber", "Вайбер"), ("Email", "імейл"), ("email", "імейл"),
         ("CRM", "сі-ар-ем"), ("SEO", "сео"), ("AI", "ШІ"), ("API", "ей-пі-ай"), ("10+", "понад десять"), ("%", " відсотків"),
         ("→", " у "), ("грн", "гривень"), ("—", ", ")]


def speak(s):
    for a, b in SPEAK:
        if a in ("10+", "%", "→", "—"):
            s = s.replace(a, b)
        else:
            s = re.sub(r"(?<![A-Za-z])" + re.escape(a) + r"(?![A-Za-z])", b, s)
    return re.sub(r"\s+", " ", s).strip()


def synth_azure(text, path, voice):
    key, reg = os.environ.get("AZURE_SPEECH_KEY"), os.environ.get("AZURE_SPEECH_REGION")
    if not key or not reg:
        return False
    ssml = (f"<speak version='1.0' xml:lang='uk-UA'><voice name='{voice}'>"
            f"<prosody rate='{RATE}'>{html.escape(text)}</prosody></voice></speak>")
    req = urllib.request.Request(f"https://{reg}.tts.speech.microsoft.com/cognitiveservices/v1", data=ssml.encode("utf-8"),
                                 headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                                          "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "vpixselle"})
    with urllib.request.urlopen(req, timeout=60) as r:
        Path(path).write_bytes(r.read())
    return Path(path).stat().st_size > 1000


def synth_edge(text, path, voice):
    import asyncio
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, voice, rate=RATE).save(str(path))
    asyncio.run(go())
    return Path(path).exists() and Path(path).stat().st_size > 1000


def synth(text, path):
    """Повертає (провайдер, голос) або None. Перший робочий голос запам'ятовується на запуск."""
    for voice in ([STATE["voice"]] if STATE.get("voice") else VOICES):
        for name, fn in (("azure", synth_azure), ("edge", synth_edge)):
            for attempt in (1, 2, 3):
                try:
                    if fn(text, path, voice):
                        STATE["voice"] = voice
                        return name, voice
                    break  # провайдер не налаштований (немає ключа): без повторів
                except Exception as e:
                    print(f"  voice {name}/{voice} (спроба {attempt}): {type(e).__name__}: {str(e)[:100]}")
                    if "No module" in str(e):
                        break
                    time.sleep(1.5 * attempt)
    return None


def probe_voice():
    with tempfile.TemporaryDirectory() as td:
        r = synth("Перевірка голосу.", Path(td) / "p.mp3")
    return bool(r)


def audio_len(path, ff):
    r = subprocess.run([ff, "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"time=(\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        return None
    h, mi, s = m[-1]
    return int(h) * 3600 + int(mi) * 60 + float(s)


def envelope(path, ff, fps=FPS):
    """Гучність голосу по кадрах 0..1 для руху губ."""
    import numpy as np
    r = subprocess.run([ff, "-loglevel", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype="<i2").astype("float32") / 32768.0
    n = max(1, int(len(a) / 16000 * fps))
    step = 16000 / fps
    rms = np.array([float(np.sqrt(np.mean(a[int(i * step):int((i + 1) * step) + 1] ** 2) + 1e-12)) for i in range(n)])
    return rms


def ambient(path, seconds, seed=7):
    """Темний ембієнт без авторських прав: дрон + повільний пад + тихий пульс."""
    import numpy as np
    SR = 44100
    n = int(SR * (seconds + 1.0))
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    sine = lambda f, ph=0: np.sin(2 * np.pi * f * t + ph)
    drone = (0.5 * sine(55.0) + 0.25 * sine(82.41) + 0.12 * sine(110.0)) * (0.75 + 0.25 * np.sin(2 * np.pi * t / 9.0))
    pad = np.zeros(n)
    for f in (220.0, 261.63, 329.63, 493.88):
        for det in (-0.6, 0.0, 0.7):
            pad += np.sin(2 * np.pi * (f + det) * t + rng.uniform(0, 6.28)) / 12
    pad *= 0.35 + 0.65 * (0.5 - 0.5 * np.cos(2 * np.pi * t / 13.0)) ** 1.5
    pulse = np.zeros(n)
    beat = 60 / 66
    for k in range(int((seconds + 1) / beat) + 1):
        s = int(k * beat * SR)
        m = min(n - s, int(0.35 * SR))
        if m <= 0:
            break
        tt = np.arange(m) / SR
        pulse[s:s + m] += np.sin(2 * np.pi * (48 + 40 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 14) * 0.9
    noise = np.convolve(rng.standard_normal(n), np.ones(40) / 40, mode="same") * 0.25
    mix = 0.55 * drone + 0.38 * pad + 0.32 * pulse + 0.12 * noise
    f_in, f_out, end = int(0.8 * SR), int(2.0 * SR), int(seconds * SR)
    env = np.ones(n)
    env[:f_in] = np.linspace(0, 1, f_in)
    env[end - f_out:end] = np.linspace(1, 0, f_out)
    env[end:] = 0
    mix *= env
    st = np.stack([mix + 0.06 * np.roll(pad, 90), mix + 0.06 * np.roll(pad, -90)], 1)
    st = st / np.max(np.abs(st)) * 0.9
    pcm = (st[:int(seconds * SR)] * 32767).astype("<i2")
    w = wave.open(str(path), "wb")
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
    w.close()


# ------------------------------------------------------------------ таймлайн і звук
def build_timeline(sb, workdir, ff, use_voice=True):
    """Озвучує розділи, рахує тривалості, субтитри й рух губ. Повертає (timeline, voice_files|None, total)."""
    chs = sb["chapters"]
    files = []
    durs = []
    if use_voice:
        for i, ch in enumerate(chs):
            f = Path(workdir) / f"v{i}.mp3"
            r = synth(speak(ch["text"]), f)
            if not r:
                files = []
                break
            files.append(f)
            durs.append(audio_len(f, ff) or max(1.8, len(ch["text"]) / 14.0))
        if files:
            print(f"  v3d voice: {STATE.get('voice')}, {len(files)} розділів")
    if not files:
        durs = [max(1.8, len(ch["text"]) / 14.0 + 0.3) for ch in chs]
    out, t = [], 0.0
    starts = []
    for ch, vd in zip(chs, durs):
        dur = max(MIN_CH, LEAD + vd + TAIL)
        chunks = sub_chunks(ch["text"])
        tot = sum(len(c) for c in chunks) or 1
        acc, cs = 0, []
        for c in chunks:
            cs.append([c.upper(), round(LEAD + vd * (acc / tot) * 0.97, 3)])
            acc += len(c)
        out.append({"scene": ch["scene"], "args": ch["args"], "kicker": ch["kicker"], "head": ch["head"], "dur": round(dur, 3), "chunks": cs})
        starts.append(t)
        t += dur
    total = round(t + 0.2, 3)
    tl = {"label": sb["label"], "cta": "", "chapters": out, "total": total, "mouthFps": FPS}
    if files:
        n = int(total * FPS) + 2
        mouth = [0.0] * n
        import numpy as np
        allrms = []
        for st, f in zip(starts, files):
            rms = envelope(f, ff)
            allrms.append(rms)
        ref = np.percentile(np.concatenate(allrms), 92) if allrms else 1.0
        for st, rms in zip(starts, allrms):
            off = int(round((st + LEAD) * FPS))
            for i, v in enumerate(rms):
                j = off + i
                if 0 <= j < n:
                    mouth[j] = float(min(1.0, (v / (ref + 1e-9)) ** 0.8)) if v > ref * 0.12 else 0.0
        # згладжування
        sm = [0.0] * n
        for i in range(n):
            a = mouth[max(0, i - 1)]
            b = mouth[i]
            c = mouth[min(n - 1, i + 1)]
            sm[i] = round(0.25 * a + 0.5 * b + 0.25 * c, 3)
        tl["mouth"] = sm
    lines = {"lines": [{"t0": round(s + LEAD, 3)} for s in starts]}
    return tl, (files or None), lines, total


def build_audio(files, lines, total, music, out, ff):
    cmd = [ff, "-y", "-loglevel", "error"]
    for f in files or []:
        cmd += ["-i", str(f)]
    nv = len(files or [])
    cmd += ["-i", str(music)]
    parts = []
    for i in range(nv):
        ms = int(lines["lines"][i]["t0"] * 1000)
        parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=mono,adelay={ms}|{ms}[a{i}]")
    if nv:
        parts.append("".join(f"[a{i}]" for i in range(nv)) +
                     f"amix=inputs={nv}:normalize=0:dropout_transition=0,loudnorm=I=-15:TP=-1.5:LRA=9,apad[voice]")
        parts.append(f"[{nv}:a]volume=0.30,aformat=channel_layouts=mono,afade=t=in:d=0.5,afade=t=out:st={max(total - 1.5, 0):.2f}:d=1.5[mus]")
        parts.append("[voice][mus]amix=inputs=2:normalize=0:duration=longest,aformat=channel_layouts=stereo[out]")
    else:
        parts.append(f"[{nv}:a]volume=1.3,afade=t=in:d=0.5,afade=t=out:st={max(total - 1.8, 0):.2f}:d=1.8,aformat=channel_layouts=stereo[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-t", f"{total:.2f}", "-ar", "44100", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("  v3d audio failed:", r.stderr[-300:])
    return r.returncode == 0


# ------------------------------------------------------------------ рендер кадрів
class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve():
    handler = lambda *a, **k: _Quiet(*a, directory=str(HERE), **k)  # noqa: E731
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def capture(tl, audio, out_mp4, ff, frames_dir=None, frame_times=None, scale=1.0, camk=None):
    from playwright.sync_api import sync_playwright
    n = int(tl["total"] * FPS)
    cmd = [ff, "-y", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS)]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-movflags", "+faststart", "-use_editlist", "0", str(out_mp4)]
    srv = serve()
    port = srv.server_address[1]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    dark = 0
    t0 = time.time()
    try:
        with sync_playwright() as p:
            br = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist",
                                         "--enable-webgl", "--disable-gpu-vsync", "--no-sandbox"])
            pg = br.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
            init = f"window.__RS={scale};" + (f"window.__CAMK={camk};" if camk else "")
            pg.add_init_script(init)
            pg.goto(f"http://127.0.0.1:{port}/v3d_engine.html")
            pg.wait_for_function("window.__ready===true", timeout=60000)
            pg.evaluate("tl => window.loadTimeline(tl)", tl)
            for i in range(n):
                t = i / FPS
                pg.evaluate("t => window.renderAt(t)", t)
                buf = pg.screenshot(type="jpeg", quality=88)
                if i in (int(FPS * 1.5), int(FPS * 6), n // 2):  # перевірка, що кадр не чорний (WebGL міг не завестися)
                    try:
                        from PIL import Image
                        im = Image.open(io.BytesIO(buf)).convert("L").resize((108, 192))
                        if sum(im.tobytes()) / (108 * 192) < 4.0:
                            dark += 1
                    except Exception:
                        pass
                    if dark >= 2:
                        print("  v3d: кадри чорні, WebGL не працює; зупиняю")
                        STATE["broken"] = True
                        br.close()
                        proc.stdin.close()
                        proc.wait()
                        return False
                proc.stdin.write(buf)
                if frames_dir and frame_times is not None and any(abs(t - ft) < 0.5 / FPS for ft in frame_times):
                    (Path(frames_dir) / f"f_{t:05.2f}.jpg").write_bytes(buf)
                if i % 250 == 0:
                    print(f"  v3d frame {i}/{n} {time.time() - t0:.0f}s", flush=True)
            if errs:
                print("  v3d page errors:", errs[:3])
            br.close()
    finally:
        srv.shutdown()
    proc.stdin.close()
    proc.wait()
    print(f"  v3d frames {n}, {time.time() - t0:.0f}s")
    return proc.returncode == 0


# ------------------------------------------------------------------ публічний інтерфейс
def render_text(text, out_mp4, seed=1, use_voice=True, frames_dir=None, frame_times=None, scale=1.0, camk=None):
    ff = find_ffmpeg()
    if not ff:
        print("v3d: ffmpeg не знайдено")
        return None
    sb = storyboard(text, seed)
    if not sb:
        print("v3d: замало тексту для ролика")
        return None
    with tempfile.TemporaryDirectory() as td:
        tl, files, lines, total = build_timeline(sb, td, ff, use_voice)
        if total > MAX_TOTAL:
            print(f"v3d: ролик {total:.0f} с задовгий")
            return None
        if os.environ.get("V3D_DUMP"):
            Path(os.environ["V3D_DUMP"]).write_text(json.dumps(tl, ensure_ascii=False), encoding="utf-8")
        music = Path(td) / "music.wav"
        ambient(music, total + 1, seed)
        audio = Path(td) / "audio.wav"
        if not build_audio(files, lines, total, music, audio, ff):
            audio = None
        ok = capture(tl, audio, out_mp4, ff, frames_dir, frame_times, scale, camk)
    return {"ok": ok, "voiced": bool(files), "seconds": round(total, 1), "chapters": [c["scene"] for c in sb["chapters"]]} if ok else None


def make(text, key, d, make_music=None, voice_state=None, budget=None):
    """Для одного звичайного посту: кеш з Pages або новий 3D-рендер. True, якщо d/tt_video.mp4 замінено 3D-роликом."""
    if STATE["broken"]:
        return False
    ver = version()
    d = Path(d)
    voice_ok = bool(voice_state.get("ok")) if voice_state else False
    names = [f"v3_{ver}_v.mp4"] + ([] if voice_ok else [f"v3_{ver}_s.mp4"])
    for nm in names:
        try:
            req = urllib.request.Request(f"{PAGES_BASE}c/{key}/{nm}", headers={"User-Agent": "vpixselle"})
            data = urllib.request.urlopen(req, timeout=30).read()
            if len(data) > 200000:
                (d / nm).write_bytes(data)
                shutil.copyfile(d / nm, d / "tt_video.mp4")
                print(f"  v3d cached: {nm}")
                return True
        except Exception:
            pass
    if budget is not None and budget["left"] <= 0:
        print("  v3d: ліміт рендерів на цей запуск, лишаю відео зі слайдів")
        return False
    if time.time() - T_START > MAX_MIN * 60:
        print("  v3d: вичерпано час на 3D-рендери в цьому запуску")
        return False
    if not ensure_deps():
        STATE["broken"] = True
        return False
    if budget is not None:
        budget["left"] -= 1
    tmp = d / "_v3.mp4"
    res = render_text(text, tmp, int(key[:8], 16), use_voice=voice_ok)
    if not res or not tmp.exists() or tmp.stat().st_size < 200000:
        tmp.unlink(missing_ok=True)
        return False
    nm = f"v3_{ver}_{'v' if res['voiced'] else 's'}.mp4"
    shutil.move(str(tmp), d / nm)
    shutil.copyfile(d / nm, d / "tt_video.mp4")
    print(f"  v3d rendered: {nm} ({res['seconds']} s) сцени: {','.join(res['chapters'])}")
    return True


if __name__ == "__main__":
    # тест: python v3d.py "текст посту" out.mp4 [--novoice] [--print] [--frames dir t1,t2] [--rs 1.0]
    args = sys.argv[1:]
    txt = args[0]
    if txt.endswith(".txt") and Path(txt).exists():
        txt = Path(txt).read_text(encoding="utf-8")
    if "--print" in args:
        sb = storyboard(txt, 1)
        for c in sb["chapters"]:
            print(f"{c['scene']:9s} | {c['kicker']} | {c['head']} | {c['args']} | {c['text']}")
        sys.exit(0)
    out = args[1]
    nov = "--novoice" in args
    fd = ft = None
    if "--frames" in args:
        i = args.index("--frames")
        fd = args[i + 1]
        ft = [float(x) for x in args[i + 2].split(",")]
        Path(fd).mkdir(parents=True, exist_ok=True)
    rs = float(args[args.index("--rs") + 1]) if "--rs" in args else 1.0
    ck = float(args[args.index("--camk") + 1]) if "--camk" in args else None
    if not ensure_deps():
        sys.exit("deps")
    print(render_text(txt, out, 5, use_voice=not nov, frames_dir=fd, frame_times=ft, scale=rs, camk=ck))
