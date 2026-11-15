"""Парсер контактів продавців Prom за категоріями.

Категорії читаються з аркуша `categories` Google-таблиці, результат дописується в аркуш `contacts`
через веб-застосунок Apps Script (URL у секреті SHEET_WEBAPP_URL, з ?token=...).

Звідки дані:
  сторінка категорії  prom.ua/ua/<Категорія>[;N]    -> "company":{"id":...,"name":...,"slug":...,"regionName":...}
  сторінка компанії   prom.ua/ua/c<ID>-<slug>.html  -> "total":<кількість товарів>
  сайт продавця       cs<ID>.prom.ua/ua/contacts    -> email, телефони, місто (або свій домен після редиректу)
Лише стандартна бібліотека Python.
"""
import json, os, re, sys, time, random, urllib.request, urllib.parse, urllib.error, html
from datetime import datetime, timezone, timedelta

WEBAPP = os.environ.get("SHEET_WEBAPP_URL", "").strip()
MAX_COMPANIES = int(os.environ.get("MAX_COMPANIES") or 100)   # нових компаній за запуск
MAX_PAGES = int(os.environ.get("MAX_PAGES") or 15)             # сторінок категорій за запуск
DELAY = float(os.environ.get("DELAY") or 2.5)                  # пауза між запитами, с
DRY = os.environ.get("DRY_RUN", "") == "1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
KYIV = timezone(timedelta(hours=2))
BAD_MAIL = re.compile(r"(prom\.ua|evo\.company|sentry|example\.|\.png|\.jpg|\.webp|\.svg|bigl\.ua|wixpress|@2x)", re.I)


class Blocked(Exception):
    pass


def is_prom(url):
    """Лише сам prom.ua: 403/429 там - справжнє блокування. Власні сайти продавців і cs*.prom.ua - ні."""
    return urllib.parse.urlparse(url).netloc.lower() in ("prom.ua", "www.prom.ua")


def get(url, tries=3):
    for k in range(tries):
        time.sleep(DELAY + random.random() * DELAY * 0.6)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "uk-UA,uk;q=0.9",
                                                   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                if not is_prom(url):
                    return e.code, url, ""     # сайт продавця закрив доступ - не блокування Prom, пропускаємо
                if k == tries - 1:
                    raise Blocked(f"{e.code} on {url}")
                time.sleep(30 * (k + 1))
                continue
            return e.code, url, ""
        except Exception as e:  # мережа
            if k == tries - 1:
                print("ERR", url, e)
                return 0, url, ""
    return 0, url, ""


def get_retry(url, need=None, pauses=(8, 20)):
    """get() із повтором, якщо відповідь збійна: мережа/5xx або сторінка без очікуваного вмісту (заглушка антибота)."""
    for k in range(len(pauses) + 1):
        st, final, htm = get(url)
        good = st == 200 and bool(htm) and (need is None or re.search(need, htm))
        if good or st in (404, 410) or k == len(pauses):
            return st, final, htm
        print(f"  retry {k + 1}: {url} -> {st}, {len(htm)} bytes")
        time.sleep(pauses[k])


API_PAUSES = (5, 10, 20, 30, 60)   # паузи між повторами запитів до Apps Script, с (6 спроб)
GET_TIMEOUT, POST_TIMEOUT = 30, 60  # Apps Script відповідає за 1-3 с; довге очікування = завислого з'єднання, краще нова спроба
KNOWN_CACHE = "/tmp/prom_known.json"   # кеш відомих ID у межах одного job, щоб не смикати повільний знімок `known`


def load_known():
    try:
        with open(KNOWN_CACHE, encoding="utf-8") as f:
            ids = json.load(f)
        if ids:
            return set(str(x) for x in ids)
    except Exception:
        pass
    return set(str(x) for x in api_get("known").get("ids", []))


def save_known(known):
    try:
        with open(KNOWN_CACHE, "w", encoding="utf-8") as f:
            json.dump(sorted(known), f)
    except Exception as e:
        print("known cache:", e)


def _api_get_once(action):
    sep = "&" if "?" in WEBAPP else "?"
    with urllib.request.urlopen(f"{WEBAPP}{sep}action={action}", timeout=GET_TIMEOUT) as r:
        return json.loads(r.read().decode())


def api_get(action, pauses=API_PAUSES):
    """GET до веб-застосунку з повторами: Apps Script іноді відповідає довше за таймаут."""
    for k in range(len(pauses) + 1):
        try:
            return _api_get_once(action)
        except Exception as e:
            print(f"api_get {action}: {type(e).__name__}: {e} (спроба {k + 1}/{len(pauses) + 1})")
            if k == len(pauses):
                raise
            time.sleep(pauses[k])


def api_post(payload):
    if DRY:
        print("DRY POST", json.dumps(payload, ensure_ascii=False)[:1500])
        return {"ok": True}
    unsure = False                      # після збою POST не знаємо, що вже записано в таблицю
    for k in range(len(API_PAUSES) + 1):
        if unsure:
            rows = payload.get("rows") or []
            try:
                ids = set(str(x) for x in api_get("known", pauses=()).get("ids", []))
                left = [r for r in rows if str(r["company_id"]) not in ids]
                if len(left) != len(rows):
                    print(f"api_post: {len(rows) - len(left)} рядків уже записано, повторюю решту ({len(left)})")
                payload = {**payload, "rows": left}
                unsure = False
            except Exception as e2:
                # без перевірки повторний POST дав би дублі - спершу повторюємо перевірку
                print(f"api_post: перевірка known не вдалась: {e2} (спроба {k + 1}/{len(API_PAUSES) + 1})")
                if k == len(API_PAUSES):
                    raise
                time.sleep(API_PAUSES[k])
                continue
        data = json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(WEBAPP, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=POST_TIMEOUT) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f"api_post: {type(e).__name__}: {e} (спроба {k + 1}/{len(API_PAUSES) + 1})")
            if k == len(API_PAUSES):
                raise
            time.sleep(API_PAUSES[k])
            unsure = bool(payload.get("rows"))


def page_url(url, n):
    url = url.split("?")[0].rstrip("/")
    url = re.sub(r";\d+$", "", url)
    return url if n <= 1 else f"{url};{n}"


def _jstr(seg, key):
    m = re.search(r'"' + key + r'":("(?:[^"\\]|\\.)*"|null)', seg)
    if not m or m.group(1) == "null":
        return ""
    return json.loads(m.group(1))


def companies_from_category(htm):
    out, seen = [], set()
    for m in re.finditer(r'"company":\{"id":(\d+)', htm):
        cid = m.group(1)
        if cid in seen:
            continue
        seg = htm[m.end():m.end() + 1500]
        if '"__typename":"Company"' not in seg[:60]:
            continue
        seen.add(cid)
        out.append({"id": cid, "name": _jstr(seg, "name"), "slug": _jstr(seg, "slug"),
                    "region": _jstr(seg, "regionName")})
    return out


def company_info(cid, slug):
    """Сторінка компанії на Prom: кількість товарів і справжня адреса сайту продавця (webSiteUrl)."""
    st, _, htm = get_retry(f"https://prom.ua/ua/c{cid}-{slug or 'company'}.html", need=r'"total":\d+|"webSiteUrl":')
    if st != 200 or not re.search(r'"total":\d+|"webSiteUrl":', htm):
        return None               # сторінку компанії не вдалося отримати - рядок не пишемо
    m = re.search(r'"total":(\d+)', htm)
    total = int(m.group(1)) if m else ""
    if total == 10000:
        total = "10000+"          # Prom показує не більше 10 000
    w = re.search(r'"webSiteUrl":"([^"]+)"', htm)
    site = json.loads('"' + w.group(1) + '"') if w else f"https://cs{cid}.prom.ua/ua/"
    return total, site


def contacts(cid, site):
    base = site.split("#")[0].rstrip("/")
    base = re.sub(r"/(ua|ru)$", "", base)
    st, final, htm = get(f"{base}/ua/contacts")
    if 500 <= st < 600:
        time.sleep(8)
        st, final, htm = get(f"{base}/ua/contacts")
    if (st != 200 or not htm or urllib.parse.urlparse(final).netloc == "prom.ua") and "cs" not in base:
        st, final, htm = get(f"https://cs{cid}.prom.ua/ua/contacts")
    if st != 200 or not htm or urllib.parse.urlparse(final).netloc == "prom.ua":
        return None
    host = urllib.parse.urlparse(final).netloc
    site = f"https://{host}/"
    mails = re.findall(r'mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})', htm)
    if not mails:
        mails = re.findall(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', htm)
    mails = [m.lower() for m in mails if not BAD_MAIL.search(m)]
    mails = list(dict.fromkeys(mails))
    phones = []
    for p in re.findall(r'(?:tel:)?(\+?380[\s()\-\d]{9,16})', htm):
        d = re.sub(r"\D", "", p)
        if len(d) == 12 and d.startswith("380"):
            phones.append("+" + d)
    phones = list(dict.fromkeys(phones))
    m = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', htm)
    city = html.unescape(json.loads('"' + m.group(1) + '"')) if m else ""
    return {"site": site, "email": ", ".join(mails[:2]), "phone": ", ".join(phones[:3]), "city": city}


def main():
    if not WEBAPP:
        sys.exit("SHEET_WEBAPP_URL is empty")
    cats = api_get("categories").get("categories", [])
    known = load_known()
    print(f"categories todo: {len(cats)}, known companies: {len(known)}")
    if not cats:
        print("nothing to do: all categories done")
        sys.exit(3)
    done_companies, pages_used = 0, 0
    stopped = False                  # зупинка через блокування/заглушку - зовнішній цикл має завершитися
    try:
        for c in cats:
            n = int(c.get("next_page") or 1)
            last = int(c.get("pages_max") or 50)
            while n <= last and pages_used < MAX_PAGES and done_companies < MAX_COMPANIES:
                st, final, htm = get(page_url(c["url"], n))
                pages_used += 1
                host = urllib.parse.urlparse(final).netloc
                if st == 404 or (st == 200 and host not in ("prom.ua", "www.prom.ua")):
                    # мертва категорія (404) або інший домен (напр. love.prom.ua): n=1 -> пропуск (next_page=0), n>1 -> кінець
                    skip = n == 1
                    api_post({"cats": [{"row": c["row"], "next_page": 0 if skip else n, "status": "готово"}], "rows": []})
                    print(f"[{c['category']} / {c['subcategory']}] page {n}: HTTP {st}, host {host} -> "
                          f"{'skip category (next_page=0)' if skip else 'end of category'}")
                    n = last + 1
                    break
                if st != 200:
                    print(f"[{c['category']} / {c['subcategory']}] page {n}: HTTP {st}, stop this run")
                    pages_used = MAX_PAGES
                    stopped = True
                    break
                comps = companies_from_category(htm)
                print(f"  page {n}: html {len(htm)} bytes, company blocks {htm.count('\"company\":{\"id\":')}, parsed {len(comps)}")
                if not comps and len(htm) < 60000:
                    # не справжня сторінка категорії (антибот/заглушка) - не позначаємо "готово"
                    snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", htm))[:300]
                    print(f"  page {n}: suspicious short page, stop. title/text: {snippet}")
                    pages_used = MAX_PAGES
                    stopped = True
                    break
                if not comps:
                    api_post({"cats": [{"row": c["row"], "next_page": n, "status": "готово"}], "rows": []})
                    print(f"[{c['category']} / {c['subcategory']}] page {n}: empty -> done")
                    n = last + 1
                    break
                rows = []
                for co in comps:
                    if co["id"] in known:
                        continue
                    if done_companies >= MAX_COMPANIES:
                        break
                    info = company_info(co["id"], co["slug"])
                    if info is None:
                        print(f"  skip {co['id']}: company page failed (will be retried if met again)")
                        continue
                    known.add(co["id"])
                    total, site0 = info
                    ct = contacts(co["id"], site0) or {}
                    rows.append({
                        "category": c["category"], "subcategory": c["subcategory"],
                        "company_id": co["id"], "shop": co["name"],
                        "site": ct.get("site") or ("" if urllib.parse.urlparse(site0).netloc in ("prom.ua", "www.prom.ua") else site0),
                        "products": total, "phone": ct.get("phone", ""), "email": ct.get("email", ""),
                        "city": ct.get("city") or re.sub(r"^м\.\s*", "", co["region"]),
                        "added": datetime.now(KYIV).strftime("%Y-%m-%d %H:%M"),
                        "prom_url": f"https://prom.ua/ua/c{co['id']}-{co['slug']}.html",
                    })
                    done_companies += 1
                full = done_companies < MAX_COMPANIES   # сторінку пройдено повністю
                nxt = n + 1 if full else n
                status = "готово" if nxt > last else "в роботі"
                api_post({"cats": [{"row": c["row"], "next_page": nxt, "status": status}], "rows": rows})
                if rows:
                    save_known(known)
                print(f"[{c['category']} / {c['subcategory']}] page {n}: {len(comps)} companies, new {len(rows)}, "
                      f"with email {sum(1 for r in rows if r['email'])}")
                if not full:
                    break
                n = nxt
            if pages_used >= MAX_PAGES or done_companies >= MAX_COMPANIES:
                break
    except Blocked as e:
        print("STOP: Prom blocks requests:", e)
        stopped = True
    print(f"done: companies {done_companies}, pages {pages_used}")
    if stopped:
        sys.exit(4)


if __name__ == "__main__":
    main()
