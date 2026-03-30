"""
scraper.py — Stahuje kybernetické novinky z RSS feedů a scrapuje NÚKIB.
Vrátí seznam článků: title, url, source, published, summary
"""

import feedparser
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import os
import time
import sys

# Fallback: kolik hodin zpět hledáme, pokud neexistuje last_run.txt
HOURS_BACK_FALLBACK = 32

RSS_FEEDS = [
    ("CERT.CZ",              "https://www.cert.cz/feed/"),
    ("Krebs on Security",    "https://krebsonsecurity.com/feed/"),
    ("The Hacker News",      "https://feeds.feedburner.com/TheHackersNews"),
    ("BleepingComputer",     "https://www.bleepingcomputer.com/feed/"),
    ("ENISA",                "https://www.enisa.europa.eu/media/news-items/news-wires/RSS"),
    ("Schneier on Security", "https://schneier.com/feed/"),
]

NUKIB_URL              = "https://nukib.gov.cz/cs/infoservis/hrozby/"
NUKIB_PORTAL_AKTUALNE  = "https://portal.nukib.gov.cz/informacni-servis/aktualne"
NUKIB_PORTAL_MATERIALY = "https://portal.nukib.gov.cz/informacni-servis/podpurne-materialy"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; KyberDigestBot/1.0; "
        "+https://github.com/kyber-digest)"
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
    """Stáhne RSS feed a vrátí články novější než since."""
    articles = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
        if feed.bozo and not feed.entries:
            print(f"[WARN] {name}: bozo feed, přeskakuji.", file=sys.stderr)
            return []
        for entry in feed.entries:
            pub = parse_entry_date(entry)
            if pub and pub < since:
                continue
            title   = getattr(entry, "title",   "").strip()
            url_e   = getattr(entry, "link",    "").strip()
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            if summary:
                summary = BeautifulSoup(summary, "lxml").get_text(separator=" ").strip()
                summary = summary[:500]
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


def fetch_nukib(since: datetime) -> list[dict]:
    """Scrapuje NÚKIB stránku hrozeb (nukib.gov.cz)."""
    articles = []
    try:
        resp = requests.get(NUKIB_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        items = (
            soup.select("article")
            or soup.select(".news-item")
            or soup.select(".article-list__item")
            or soup.select("li.item")
        )
        for item in items:
            a_tag = item.find("a", href=True)
            if not a_tag:
                continue
            title = a_tag.get_text(strip=True)
            href  = a_tag["href"]
            if not href.startswith("http"):
                href = "https://nukib.gov.cz" + href
            date_tag = item.find("time") or item.find(class_=lambda c: c and "date" in c)
            pub = None
            if date_tag:
                dt_str = date_tag.get("datetime") or date_tag.get_text(strip=True)
                for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        pub = datetime.strptime(dt_str[:10], fmt[:len(dt_str[:10])]).replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        pass
            if pub and pub < since:
                continue
            summary_tag = item.find("p") or item.find(class_=lambda c: c and "perex" in (c or ""))
            summary = summary_tag.get_text(strip=True)[:500] if summary_tag else ""
            if title and href:
                articles.append({
                    "title":     title,
                    "url":       href,
                    "source":    "NÚKIB",
                    "published": pub.isoformat() if pub else "",
                    "summary":   summary,
                })
    except Exception as exc:
        print(f"[ERROR] NÚKIB: {exc}", file=sys.stderr)
    return articles


def fetch_nukib_portal(url: str, source_name: str, since: datetime) -> list[dict]:
    """Scrapuje portál NÚKIB (aktuálně / podpůrné materiály)."""
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        path_segment = url.split("portal.nukib.gov.cz")[1]
        links = soup.select('a[href*="' + path_segment + '/"]')
        seen_hrefs = set()
        for a_tag in links:
            href = a_tag.get("href", "").strip()
            if not href:
                continue
            if not href.startswith("http"):
                href = "https://portal.nukib.gov.cz" + href
            if href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            raw_text = a_tag.get_text(separator="\n", strip=True)
            lines_txt = [l.strip() for l in raw_text.split("\n") if l.strip()]
            pub = None
            title_parts = []
            for line in lines_txt:
                date_match = re.match(r"(\d{1,2})\.,?\s*(\d{1,2})\.,?\s*(\d{4})", line)
                if date_match and pub is None:
                    try:
                        d, m, y = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                        pub = datetime(y, m, d, 8, 0, 0, tzinfo=timezone.utc)
                    except ValueError:
                        pass
                elif re.match(r"TLP:", line) or line in ("Aktuality", "Upozornění", "Materiály", "Analýzy", "Legislativa"):
                    continue
                elif pub is not None:
                    title_parts.append(line)
            title = " ".join(title_parts).strip()
            if not title or not href:
                continue
            if pub and pub < since:
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
        time.sleep(0.5)

    # NÚKIB – nukib.gov.cz/hrozby
    nukib_items = fetch_nukib(since)
    print(f"[INFO] NÚKIB hrozby: {len(nukib_items)} článků", file=sys.stderr)
    all_articles.extend(nukib_items)

    # NÚKIB portál – aktuálně
    portal_aktualne = fetch_nukib_portal(NUKIB_PORTAL_AKTUALNE, "NÚKIB portál – Aktuálně", since)
    print(f"[INFO] NÚKIB portál Aktuálně: {len(portal_aktualne)} článků", file=sys.stderr)
    all_articles.extend(portal_aktualne)

    # NÚKIB portál – podpůrné materiály
    portal_materialy = fetch_nukib_portal(NUKIB_PORTAL_MATERIALY, "NÚKIB portál – Materiály", since)
    print(f"[INFO] NÚKIB portál Materiály: {len(portal_materialy)} článků", file=sys.stderr)
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