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


API_PAUSES = (10, 30, 60)   # паузи між повторами запитів до Apps Script, с


def _api_get_once(action):
    sep = "&" if "?" in WEBAPP else "?"
    with urllib.request.urlopen(f"{WEBAPP}{sep}action={action}", timeout=90) as r:
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
    for k in range(len(API_PAUSES) + 1):
        data = json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(WEBAPP, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            print(f"api_post: {type(e).__name__}: {e} (спроба {k + 1}/{len(API_PAUSES) + 1})")
            if k == len(API_PAUSES):
                raise
            time.sleep(API_PAUSES[k])
            rows = payload.get("rows") or []
            if rows:
                # таймаут міг настати вже після запису: не дублюємо рядки, що вже є в таблиці
                try:
                    ids = set(str(x) for x in api_get("known", pauses=()).get("ids", []))
                    left = [r for r in rows if str(r["company_id"]) not in ids]
                    if len(left) != len(rows):
                        print(f"api_post: {len(rows) - len(left)} рядків уже записано, повторюю решту ({len(left)})")
                    payload = {**payload, "rows": left}
                except Exception as e2:
                    print(f"api_post: перевірка known не вдалась: {e2}")


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
    st, _, htm = get(f"https://prom.ua/ua/c{cid}-{slug or 'company'}.html")
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
    known = set(str(x) for x in api_get("known").get("ids", []))
    print(f"categories todo: {len(cats)}, known companies: {len(known)}")
    done_companies, pages_used = 0, 0
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
                    break
                comps = companies_from_category(htm)
                print(f"  page {n}: html {len(htm)} bytes, company blocks {htm.count('\"company\":{\"id\":')}, parsed {len(comps)}")
                if not comps and len(htm) < 60000:
                    # не справжня сторінка категорії (антибот/заглушка) - не позначаємо "готово"
                    snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", htm))[:300]
                    print(f"  page {n}: suspicious short page, stop. title/text: {snippet}")
                    pages_used = MAX_PAGES
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
                    known.add(co["id"])
                    total, site0 = company_info(co["id"], co["slug"])
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
                print(f"[{c['category']} / {c['subcategory']}] page {n}: {len(comps)} companies, new {len(rows)}, "
                      f"with email {sum(1 for r in rows if r['email'])}")
                if not full:
                    break
                n = nxt
            if pages_used >= MAX_PAGES or done_companies >= MAX_COMPANIES:
                break
    except Blocked as e:
        print("STOP: Prom blocks requests:", e)
    print(f"done: companies {done_companies}, pages {pages_used}")


if __name__ == "__main__":
    main()
