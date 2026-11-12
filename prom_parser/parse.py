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
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "uk-UA,uk;q=0.9"})
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


def api_get(action):
    sep = "&" if "?" in WEBAPP else "?"
    with urllib.request.urlopen(f"{WEBAPP}{sep}action={action}", timeout=60) as r:
        return json.loads(r.read().decode())


def api_post(payload):
    if DRY:
        print("DRY POST", json.dumps(payload, ensure_ascii=False)[:1500])
        return {"ok": True}
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(WEBAPP, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def page_url(url, n):
    url = url.split("?")[0].rstrip("/")
    url = re.sub(r";\d+$", "", url)
    return url if n <= 1 else f"{url};{n}"


def companies_from_category(htm):
    out, seen = [], set()
    for m in re.finditer(r'"company":\{"id":(\d+),"__typename":"Company","name":"((?:[^"\\]|\\.)*)","slug":"([^"]*)","regionName":(null|"(?:[^"\\]|\\.)*")', htm):
        cid = m.group(1)
        if cid in seen:
            continue
        seen.add(cid)
        name = json.loads('"' + m.group(2) + '"')
        region = json.loads(m.group(4)) if m.group(4) != "null" else ""
        out.append({"id": cid, "name": name, "slug": m.group(3), "region": region or ""})
    return out


def product_total(cid, slug):
    st, _, htm = get(f"https://prom.ua/ua/c{cid}-{slug or 'company'}.html")
    m = re.search(r'"total":(\d+)', htm)
    return int(m.group(1)) if m else ""


def contacts(cid):
    st, final, htm = get(f"https://cs{cid}.prom.ua/ua/contacts")
    if st != 200 or not htm:
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
                st, _, htm = get(page_url(c["url"], n))
                pages_used += 1
                comps = companies_from_category(htm) if st == 200 else []
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
                    ct = contacts(co["id"]) or {}
                    total = product_total(co["id"], co["slug"])
                    rows.append({
                        "category": c["category"], "subcategory": c["subcategory"],
                        "company_id": co["id"], "shop": co["name"],
                        "site": ct.get("site") or f"https://cs{co['id']}.prom.ua/",
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
