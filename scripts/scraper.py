"""
scraper.py — Stahuje kybernetické novinky z RSS feedů a scrapuje NÚKIB.
Vrátí seznam článků: title, url, source, published, summary
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import time
import sys

# Kolik hodin zpět hledáme
HOURS_BACK = 24

RSS_FEEDS = [
    ("CERT.CZ",           "https://www.cert.cz/feed/"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
    ("The Hacker News",   "https://feeds.feedburner.com/TheHackersNews"),
    ("BleepingComputer",  "https://www.bleepingcomputer.com/feed/"),
    ("ENISA",             "https://www.enisa.europa.eu/media/news-items/news-wires/RSS"),
    ("Schneier on Security", "https://schneier.com/feed/"),
]

NUKIB_URL = "https://nukib.gov.cz/cs/infoservis/hrozby/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; KyberDigestBot/1.0; "
        "+https://github.com/kyber-digest)"
    )
}


def cutoff_time() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)


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
            print(f"[WARN] {name}: bozo feed, přeskakuji.", file=sys.stderr)
            return []
        for entry in feed.entries:
            pub = parse_entry_date(entry)
            # Pokud datum chybí, zahrneme článek (raději víc než méně)
            if pub and pub < since:
                continue
            title   = getattr(entry, "title", "").strip()
            url_e   = getattr(entry, "link",  "").strip()
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            # Odstraň HTML tagy ze summary
            if summary:
                summary = BeautifulSoup(summary, "lxml").get_text(separator=" ").strip()
            summary = summary[:500] if summary else ""
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
    """Scrapuje NÚKIB stránku hrozeb (nemá RSS)."""
    articles = []
    try:
        resp = requests.get(NUKIB_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # NÚKIB používá seznam článků s class "article-item" nebo podobné
        # Zkusíme několik selektorů, web se občas mění
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

            # Datum — hledáme time nebo .date element
            date_tag = item.find("time") or item.find(class_=lambda c: c and "date" in c)
            pub = None
            if date_tag:
                dt_str = date_tag.get("datetime") or date_tag.get_text(strip=True)
                for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        pub = datetime.strptime(dt_str[:10], fmt[:len(dt_str[:10])]).replace(
                            tzinfo=timezone.utc
                        )
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
        time.sleep(0.5)  # slušnost vůči serverům

    # NÚKIB scraping
    nukib_items = fetch_nukib(since)
    print(f"[INFO] NÚKIB: {len(nukib_items)} článků", file=sys.stderr)
    all_articles.extend(nukib_items)

    # Deduplikace
    all_articles = deduplicate(all_articles)

    # Seřadit od nejnovějšího
    all_articles.sort(key=lambda x: x.get("published", ""), reverse=True)

    print(f"[INFO] Celkem po deduplikaci: {len(all_articles)} článků", file=sys.stderr)
    return all_articles


if __name__ == "__main__":
    import json
    results = scrape_all()
    print(json.dumps(results, ensure_ascii=False, indent=2))
