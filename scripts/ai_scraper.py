"""
ai_scraper.py — Stahuje AI novinky z RSS feedů.
Vrátí seznam článků: title, url, source, published, summary
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import os
import time
import sys

# Fallback: kolik hodin zpět hledáme, pokud neexistuje last_run.txt
HOURS_BACK_FALLBACK = 32

RSS_FEEDS = [
    ("OpenAI Blog",          "https://openai.com/news/rss.xml"),
    ("Google DeepMind",      "https://deepmind.google/blog/rss.xml"),
    ("Hugging Face Blog",    "https://huggingface.co/blog/feed.xml"),
    ("MIT Technology Review","https://www.technologyreview.com/feed/"),
    ("VentureBeat AI",       "https://venturebeat.com/category/ai/feed/"),
    ("TechCrunch AI",        "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("Ars Technica AI",      "https://arstechnica.com/tag/ai/feed/"),
    ("The Verge AI",         "https://www.theverge.com/rss/ai-artificial-intelligence/rss/index.xml"),
    ("Wired AI",             "https://www.wired.com/feed/tag/artificial-intelligence/rss"),
    # EU AI Act & regulace
    ("EURACTIV Digital",     "https://www.euractiv.com/sections/digital/feed/"),
    ("AlgorithmWatch",       "https://algorithmwatch.org/en/feed/"),
    ("Future of Life Inst.", "https://futureoflife.org/feed/"),
]

# Google News RSS vyhledávání — agreguje zprávy o AI Act z mnoha zdrojů
AI_ACT_NEWS_FEEDS = [
    ("AI Act News (EN)",
     "https://news.google.com/rss/search?q=%22AI+Act%22+OR+%22Artificial+Intelligence+Act%22+EU&hl=en&gl=US&ceid=US:en"),
    ("AI Act News (CS)",
     "https://news.google.com/rss/search?q=%22AI+Act%22+OR+%22z%C3%A1kon+o+um%C4%9Bl%C3%A9+inteligenci%22&hl=cs&gl=CZ&ceid=CZ:cs"),
]

# Klíčová slova pro identifikaci AI Act článků z obecných feedů
AI_ACT_KEYWORDS = [
    "ai act", "artificial intelligence act", "eu ai", "ai regulation",
    "zákon o umělé inteligenci", "nařízení o ai", "eu ai regulation",
    "ai liability", "ai office", "eu ai office", "high-risk ai",
    "ai governance", "algorithmic accountability",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AIDigestBot/1.0; "
        "+https://github.com/coufalmilan/KB-souhrn)"
    )
}


def cutoff_time() -> datetime:
    """
    Vrátí čas od kdy hledat články.
    Pokud existuje env AI_LAST_RUN_TS (ISO 8601), použijeme ho.
    Jinak jdeme HOURS_BACK_FALLBACK hodin zpět.
    """
    last_run_ts = os.environ.get("AI_LAST_RUN_TS", "").strip()
    if last_run_ts:
        try:
            dt = datetime.fromisoformat(last_run_ts.replace("Z", "+00:00"))
            print(f"[INFO] Cutoff: od posledního runu {dt.strftime('%Y-%m-%d %H:%M UTC')}", file=sys.stderr)
            return dt
        except ValueError:
            print(f"[WARN] Nepodařilo se parsovat AI_LAST_RUN_TS='{last_run_ts}', používám fallback.", file=sys.stderr)
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
            print(f"[WARN] {name}: bozo feed, přeskakuji.", file=sys.stderr)
            return []
        for entry in feed.entries:
            pub = parse_entry_date(entry)
            if pub and pub < since:
                continue
            title   = getattr(entry, "title", "").strip()
            url_e   = getattr(entry, "link",  "").strip()
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
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


def is_ai_act_article(article: dict) -> bool:
    """Vrátí True pokud článek pravděpodobně pojednává o EU AI Act."""
    text = (article.get("title", "") + " " + article.get("summary", "")).lower()
    return any(kw in text for kw in AI_ACT_KEYWORDS)


def scrape_all() -> list[dict]:
    since = cutoff_time()
    all_articles = []

    print(f"[INFO] Stahuji AI novinky od {since.strftime('%Y-%m-%d %H:%M UTC')} …", file=sys.stderr)

    # Hlavní RSS feedy (obecné AI zprávy)
    for name, url in RSS_FEEDS:
        items = fetch_rss(name, url, since)
        # Článkům o AI Act přidáme označení zdroje pro lepší sumarizaci
        for item in items:
            if is_ai_act_article(item):
                item["source"] = f"{item['source']} [AI Act]"
        print(f"[INFO] {name}: {len(items)} článků", file=sys.stderr)
        all_articles.extend(items)
        time.sleep(0.5)

    # Dedikované AI Act / regulační feedy (Google News search + specializovaná média)
    print(f"[INFO] Stahuji AI Act zdroje …", file=sys.stderr)
    for name, url in AI_ACT_NEWS_FEEDS:
        items = fetch_rss(name, url, since)
        for item in items:
            item["source"] = f"{item['source']} [AI Act]"
        print(f"[INFO] {name}: {len(items)} článků", file=sys.stderr)
        all_articles.extend(items)
        time.sleep(0.5)

    all_articles = deduplicate(all_articles)
    all_articles.sort(key=lambda x: x.get("published", ""), reverse=True)

    ai_act_count = sum(1 for a in all_articles if "[AI Act]" in a.get("source", ""))
    print(f"[INFO] Celkem AI článků po deduplikaci: {len(all_articles)} (z toho AI Act: {ai_act_count})", file=sys.stderr)
    return all_articles


if __name__ == "__main__":
    import json
    results = scrape_all()
    print(json.dumps(results, ensure_ascii=False, indent=2))
