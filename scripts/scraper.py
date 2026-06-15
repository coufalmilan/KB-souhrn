"""
scraper.py — Stahuje kybernetické novinky z RSS feedů a scrapuje NÚKIB portál.
Vrátí seznam článků: title, url, source, published, summary
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import os
import re
import time
import sys

# Fallback: kolik hodin zpět hledáme, pokud neexistuje last_run.txt
HOURS_BACK_FALLBACK = 32

RSS_FEEDS = [
    ("CERT.CZ",              "https://www.cert.cz/feed/"),
    ("Krebs on Security",    "https://krebsonsecurity.com/feed/"),
    ("The Hacker News",      "https://feeds.feedburner.com/TheHackersNews"),
    ("BleepingComputer",     "https://www.bleepingcomputer.com/feed/"),
    ("Schneier on Security", "https://schneier.com/feed/"),
]

# ENISA - samostatně kvůli bozo feed fallbacku
ENISA_RSS = "https://www.enisa.europa.eu/media/news-items/news-wires/RSS"

# NÚKIB klasická stránka (nukib.gov.cz) — RSS nefunguje, scrapeujeme HTML přímo
NUKIB_CLASSIC_PAGES = [
    ("NUKIB Aktuality", "https://nukib.gov.cz/cs/infoservis/aktuality/"),
    ("NUKIB Hrozby",    "https://nukib.gov.cz/cs/infoservis/hrozby/"),
]

# NÚKIB portál (React SPA / Next.js) - zkouší API i HTML scraping
NUKIB_PORTAL_AKTUALNE_URL  = "https://portal.nukib.gov.cz/informacni-servis/aktualne"
NUKIB_PORTAL_MATERIALY_URL = "https://portal.nukib.gov.cz/informacni-servis/podpurne-materialy"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def cutoff_time() -> datetime:
    """
    Vrátí čas od kdy hledat články.
    Pokud existuje env LAST_RUN_TS (ISO 8601 z docs/last_run.txt), použijeme ho.
    Jinak jdeme HOURS_BACK_FALLBACK hodin zpět.
    """
    last_run_ts = os.environ.get("LAST_RUN_TS", "").strip()
    if last_run_ts:
        try:
            dt = datetime.fromisoformat(last_run_ts.replace("Z", "+00:00"))
            print(f"[INFO] Cutoff: od posledního runu {dt.strftime('%Y-%m-%d %H:%M UTC')}", file=sys.stderr)
            return dt
        except ValueError:
            print(f"[WARN] Nepodařilo se parsovat LAST_RUN_TS='{last_run_ts}', používám fallback.", file=sys.stderr)
    fallback = datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK_FALLBACK)
    print(f"[INFO] Cutoff: fallback {HOURS_BACK_FALLBACK}h zpět ({fallback.strftime('%Y-%m-%d %H:%M UTC')})", file=sys.stderr)
    return fallback


def parse_entry_date(entry) -> datetime | None:
    """Vrátí datetime z feedparser entry, nebo None."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_rss(name: str, url: str, since: datetime) -> list[dict]:
    """Stáhne RSS feed a vrátí články novější než `since`."""
    articles = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        if feed.bozo and not feed.entries:
            print(f"[WARN] {name}: bozo feed bez položek, přeskakuji.", file=sys.stderr)
            return []
        for entry in feed.entries:
            pub = parse_entry_date(entry)
            if pub and pub < since:
                continue
            title   = getattr(entry, "title", "").strip()
            url_e   = getattr(entry, "link",  "").strip()
            raw_sum = getattr(entry, "summary", "") or getattr(entry, "description", "")
            summary = ""
            if raw_sum and len(raw_sum) > 10 and not raw_sum.startswith("/"):
                try:
                    summary = BeautifulSoup(raw_sum, "lxml").get_text(separator=" ").strip()[:500]
                except Exception:
                    summary = raw_sum[:500]
            if title and url_e:
                articles.append({
                    "title":     title,
                    "url":       url_e,
                    "source":    name,
                    "published": pub.isoformat() if pub else "",
                    "summary":   summary,
                })
    except Exception as exc:
        print(f"[ERROR] {name}: {exc}", file=sys.stderr)
    return articles


def fetch_nukib_classic(name: str, url: str, since: datetime) -> list[dict]:
    """
    Scrapuje klasické stránky nukib.gov.cz (Aktuality, Hrozby).
    RSS feed přestal fungovat (vrací HTML místo XML) — parsujeme HTML přímo.
    Struktura stránky: <h3>DD.MM.YYYY <a href="/cs/...">Titulek</a></h3>
    """
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Hledáme <h3> elementy — každý obsahuje datum a odkaz
        for h3 in soup.find_all("h3"):
            a_tag = h3.find("a", href=True)
            if not a_tag:
                continue

            full_text = h3.get_text(separator=" ", strip=True)

            # Datum ve formátu DD.MM.YYYY (přesný tvar na nukib.gov.cz)
            date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", full_text)
            pub = None
            if date_match:
                try:
                    pub = datetime(int(date_match.group(3)), int(date_match.group(2)),
                                   int(date_match.group(1)), tzinfo=timezone.utc)
                except ValueError:
                    pass

            if pub is None:
                continue
            if pub < since:
                continue

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            href = a_tag["href"]
            if not href.startswith("http"):
                href = "https://nukib.gov.cz" + href

            articles.append({
                "title":     title,
                "url":       href,
                "source":    name,
                "published": pub.isoformat(),
                "summary":   "",
            })

    except Exception as exc:
        print(f"[ERROR] {name}: {exc}", file=sys.stderr)

    print(f"[INFO] {name}: {len(articles)} článků", file=sys.stderr)
    return articles


def fetch_nukib_portal_playwright(url: str, source_name: str, path_segment: str, since: datetime) -> list[dict]:
    """
    Záloha pomocí Playwright pro JS-only SPA (portal.nukib.gov.cz).
    Spustí headless Chromium, počká na načtení stránky a extrahuje linky.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(f"[WARN] Playwright není nainstalován, přeskakuji {source_name}.", file=sys.stderr)
        return []

    articles = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=HEADERS["User-Agent"])
            page.goto(url, wait_until="networkidle", timeout=30000)

            # Datum je v jiném elementu než odkaz.
            # Strategie: zkusíme closest(), pak procházíme rodiče až 8 úrovní nahoru,
            # hledáme první kontejner jehož text obsahuje datum (DD. M. YYYY).
            # Pokud ani to nepomůže, vrátíme text rodiče 3. úrovně jako zálohu.
            links = page.eval_on_selector_all(
                f'a[href*="{path_segment}"]',
                """els => {
                    const dateRe = /\\d{1,2}[.\\s]\\s*\\d{1,2}[.\\s]\\s*\\d{4}/;
                    return els.map(el => {
                        // 1) Zkusíme closest() se širším výběrem selektorů
                        const container = el.closest(
                            'li, article, tr, ' +
                            '[class*="item"], [class*="card"], [class*="row"], ' +
                            '[class*="article"], [class*="entry"], [class*="post"], ' +
                            '[class*="list"], [class*="result"]'
                        );
                        if (container) {
                            return { href: el.href, title: el.innerText.trim(),
                                     text: container.innerText.trim() };
                        }

                        // 2) Procházíme rodiče nahoru, hledáme datum
                        let node = el.parentElement;
                        let fallback3 = null;
                        for (let i = 0; i < 8; i++) {
                            if (!node) break;
                            if (i === 2) fallback3 = node;
                            const txt = node.innerText || '';
                            if (dateRe.test(txt)) {
                                return { href: el.href, title: el.innerText.trim(),
                                         text: txt.trim() };
                            }
                            node = node.parentElement;
                        }

                        // 3) Záloha: rodič 3. úrovně nebo přímý rodič
                        const fb = fallback3 || el.parentElement;
                        return { href: el.href, title: el.innerText.trim(),
                                 text: fb ? fb.innerText.trim() : el.innerText.trim() };
                    });
                }"""
            )
            print(f"[INFO] {source_name} (Playwright): {len(links)} odkazů", file=sys.stderr)

            # Debug: vypiš první 2 záznamy pro diagnostiku
            for dbg in links[:2]:
                snip = dbg.get("text", "")[:150].replace("\n", " | ")
                print(f"[DEBUG] {source_name}: text kontejneru: {snip!r}", file=sys.stderr)

            browser.close()

        seen_urls = set()
        for link in links:
            href       = link.get("href", "").strip()
            title_text = link.get("title", "").strip()   # text samotného odkazu
            full_text  = link.get("text", "").strip()    # text celého kontejneru (obsahuje datum)
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            # Datum hledáme v celém kontejneru (formát "25. 5. 2026" nebo "25.5.2026")
            date_match = re.search(r"(\d{1,2})\.,?\s*(\d{1,2})\.,?\s*(\d{4})", full_text)
            pub = None
            if date_match:
                try:
                    pub = datetime(int(date_match.group(3)), int(date_match.group(2)),
                                   int(date_match.group(1)), tzinfo=timezone.utc)
                except ValueError:
                    pass

            # Pokud datum nebylo nalezeno v kontejneru, článek přeskočíme
            # (brání zobrazování starých článků bez data)
            if pub is None:
                print(f"[WARN] {source_name}: nenalezeno datum pro '{title_text[:60]}'", file=sys.stderr)
                print(f"[WARN]   container text: {full_text[:120]!r}", file=sys.stderr)
                continue
            if pub < since:
                continue

            # Název: preferuj text odkazu, jinak očisti kontejner
            title = title_text or re.sub(r"^\d{1,2}\.,?\s*\d{1,2}\.,?\s*\d{4}\s*", "", full_text).strip()
            title = re.sub(r"^TLP\s*:\s*\w+\s*[·•\-–]?\s*", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"^[·•\-–]\s*", "", title).strip()
            if not title or len(title) < 5:
                continue

            articles.append({
                "title":     title,
                "url":       href,
                "source":    source_name,
                "published": pub.isoformat() if pub else "",
                "summary":   "",
            })
    except Exception as exc:
        print(f"[ERROR] {source_name} Playwright selhal: {exc}", file=sys.stderr)

    return articles


def fetch_nukib_portal(url: str, source_name: str, path_segment: str, since: datetime) -> list[dict]:
    """
    Scrapuje portal.nukib.gov.cz.
    Portál je React/Next.js SPA — zkouší:
    1) JSON API s Accept: application/json
    2) HTML scraping odkazů s path_segment v href
    3) Playwright jako záloha pro JS-only stránky
    """
    articles = []

    # --- Pokus 1: JSON API (content negotiation) ---
    try:
        api_headers = {**HEADERS, "Accept": "application/json, text/plain, */*"}
        resp = requests.get(url, headers=api_headers, timeout=20)
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct:
            data = resp.json()
            print(f"[INFO] {source_name}: JSON API odpověď, typ: {type(data)}", file=sys.stderr)
            items = data if isinstance(data, list) else data.get("items", data.get("articles", data.get("data", [])))
            for item in items:
                pub_str = item.get("publishedAt") or item.get("createdAt") or item.get("date", "")
                pub = None
                if pub_str:
                    try:
                        pub = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                if pub and pub < since:
                    continue
                title = item.get("title") or item.get("name") or item.get("heading", "")
                slug  = item.get("slug") or item.get("id") or item.get("_id") or ""
                link  = f"https://portal.nukib.gov.cz/informacni-servis/{path_segment}/{slug}" if slug else url
                if title:
                    articles.append({
                        "title":     title,
                        "url":       link,
                        "source":    source_name,
                        "published": pub.isoformat() if pub else "",
                        "summary":   item.get("perex") or item.get("description") or "",
                    })
            if articles:
                return articles
    except Exception as exc:
        print(f"[WARN] {source_name} JSON API selhal: {exc}", file=sys.stderr)

    # --- Pokus 2: HTML scraping ---
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()

        # Detekce JS-only SPA — stránka neobsahuje obsah, jen "JavaScript required"
        if "JavaScript" in resp.text and len(resp.text) < 8000:
            print(f"[WARN] {source_name}: stránka vyžaduje JavaScript (SPA), přepínám na Playwright...", file=sys.stderr)
            return fetch_nukib_portal_playwright(url, source_name, path_segment, since)

        soup = BeautifulSoup(resp.text, "lxml")

        # Hledáme všechny linky vedoucí do příslušné sekce
        links = [a for a in soup.find_all("a", href=True)
                 if path_segment in a.get("href", "")]

        print(f"[INFO] {source_name}: HTML scraping nalezl {len(links)} odkazů", file=sys.stderr)

        seen_urls = set()
        for a_tag in links:
            href = a_tag["href"]
            if not href.startswith("http"):
                href = "https://portal.nukib.gov.cz" + href
            if href in seen_urls:
                continue
            seen_urls.add(href)

            full_text = a_tag.get_text(separator=" ", strip=True)

            # Datum ve formátu "12. 3. 2026"
            date_match = re.search(r"(\d{1,2})\.,?\s*(\d{1,2})\.,?\s*(\d{4})", full_text)
            pub = None
            if date_match:
                try:
                    day   = int(date_match.group(1))
                    month = int(date_match.group(2))
                    year  = int(date_match.group(3))
                    pub   = datetime(year, month, day, tzinfo=timezone.utc)
                except ValueError:
                    pass

            if pub and pub < since:
                continue

            # Odstraň datum a TLP z textu → zbytek je název
            title = re.sub(r"^\d{1,2}\.,?\s*\d{1,2}\.,?\s*\d{4}\s*", "", full_text).strip()
            title = re.sub(r"^[·•\-–]\s*", "", title).strip()
            title = re.sub(r"^TLP\s*:\s*\w+\s*[·•\-–]?\s*", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"^[·•\-–]\s*", "", title).strip()

            if not title or len(title) < 5:
                continue

            articles.append({
                "title":     title,
                "url":       href,
                "source":    source_name,
                "published": pub.isoformat() if pub else "",
                "summary":   "",
            })

    except Exception as exc:
        print(f"[ERROR] {source_name}: {exc}", file=sys.stderr)

    return articles


def deduplicate(articles: list[dict]) -> list[dict]:
    """Odstraní duplicity podle URL."""
    seen = set()
    result = []
    for a in articles:
        url = a["url"].rstrip("/")
        if url not in seen:
            seen.add(url)
            result.append(a)
    return result


def scrape_all() -> list[dict]:
    since = cutoff_time()
    all_articles = []

    print(f"[INFO] Stahuji novinky od {since.strftime('%Y-%m-%d %H:%M UTC')} …", file=sys.stderr)

    # RSS feedy
    for name, url in RSS_FEEDS:
        items = fetch_rss(name, url, since)
        print(f"[INFO] {name}: {len(items)} článků", file=sys.stderr)
        all_articles.extend(items)
        time.sleep(0.3)

    # ENISA - zvlášť (bozo feed, ale má obsah)
    enisa = fetch_rss("ENISA", ENISA_RSS, since)
    print(f"[INFO] ENISA: {len(enisa)} článků", file=sys.stderr)
    all_articles.extend(enisa)

    # NÚKIB klasické stránky (HTML scraping — RSS přestalo fungovat)
    for name, url in NUKIB_CLASSIC_PAGES:
        time.sleep(0.3)
        items = fetch_nukib_classic(name, url, since)
        all_articles.extend(items)

    # NÚKIB portál
    time.sleep(0.5)
    portal_aktualne = fetch_nukib_portal(
        NUKIB_PORTAL_AKTUALNE_URL, "NUKIB Portal - Aktualne", "aktualne", since
    )
    print(f"[INFO] NUKIB Portal Aktualne: {len(portal_aktualne)} článků", file=sys.stderr)
    all_articles.extend(portal_aktualne)

    time.sleep(0.5)
    portal_materialy = fetch_nukib_portal(
        NUKIB_PORTAL_MATERIALY_URL, "NUKIB Portal - Materialy", "podpurne-materialy", since
    )
    print(f"[INFO] NUKIB Portal Materialy: {len(portal_materialy)} článků", file=sys.stderr)
    all_articles.extend(portal_materialy)

    # Deduplikace a řazení
    all_articles = deduplicate(all_articles)
    all_articles.sort(key=lambda x: x.get("published", ""), reverse=True)

    print(f"[INFO] Celkem po deduplikaci: {len(all_articles)} článků", file=sys.stderr)
    return all_articles


if __name__ == "__main__":
    import json
    results = scrape_all()
    print(json.dumps(results, ensure_ascii=False, indent=2))
