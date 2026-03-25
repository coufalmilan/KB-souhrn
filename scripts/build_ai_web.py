"""
build_ai_web.py — Generuje statické HTML stránky pro AI digest.

Výstup:
  docs/ai/index.html               — dnešní AI souhrn + archív posledních 30 dní
  docs/ai/archive/YYYY-MM-DD.html  — archívní stránka pro konkrétní den
"""

import os
import sys
import re
import json
from pathlib import Path
from datetime import date, datetime, timezone
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR     = Path(__file__).resolve().parent.parent
DOCS_DIR     = BASE_DIR / "docs" / "ai"
ARCHIVE_DIR  = DOCS_DIR / "archive"
TEMPLATE_DIR = BASE_DIR / "templates"
ARCHIVE_INDEX = ARCHIVE_DIR / "index.json"

MAX_ARCHIVE_IN_INDEX = 30


def load_archive_index() -> list[dict]:
    if ARCHIVE_INDEX.exists():
        with open(ARCHIVE_INDEX, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_archive_index(entries: list[dict]) -> None:
    ARCHIVE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_INDEX, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def markdown_to_html(md: str) -> str:
    html_lines = []
    lines = md.split("\n")
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

    def inline(text: str) -> str:
        text = re.sub(
            r'(https?://[^\s<>"]+)',
            r'<a href="\1" target="_blank" rel="noopener">\1</a>',
            text,
        )
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        return text

    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("## "):
            close_ul()
            html_lines.append(f'<h2 class="digest-h2">{inline(stripped[3:])}</h2>')
        elif stripped.startswith("### "):
            close_ul()
            html_lines.append(f'<h3 class="digest-h3">{inline(stripped[4:])}</h3>')
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"  <li>{inline(stripped[2:])}</li>")
        elif stripped == "":
            close_ul()
            html_lines.append("")
        else:
            close_ul()
            html_lines.append(f"<p>{inline(stripped)}</p>")

    close_ul()
    return "\n".join(html_lines)


def format_date_cz(d: date | str) -> str:
    months = [
        "", "ledna", "února", "března", "dubna", "května", "června",
        "července", "srpna", "září", "října", "listopadu", "prosince",
    ]
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day}. {months[d.month]} {d.year}"


def build(summary_md: str, today: date | None = None) -> None:
    if today is None:
        today = date.today()

    today_str    = today.isoformat()
    today_cz     = format_date_cz(today)
    summary_html = markdown_to_html(summary_md)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown_to_html"] = markdown_to_html
    env.filters["format_date_cz"]   = format_date_cz

    # --- Archívní záznamy ---------------------------------------------------
    archive_entries = load_archive_index()

    existing = next((e for e in archive_entries if e["date"] == today_str), None)
    if existing:
        existing["title"] = f"AI Digest {today_cz}"
    else:
        archive_entries.insert(0, {
            "date":  today_str,
            "title": f"AI Digest {today_cz}",
            "url":   f"archive/{today_str}.html",
        })

    archive_entries = sorted(archive_entries, key=lambda e: e["date"], reverse=True)
    save_archive_index(archive_entries)

    recent_30 = archive_entries[:MAX_ARCHIVE_IN_INDEX]

    # --- Stránka dne --------------------------------------------------------
    day_tmpl = env.get_template("ai_day.html.j2")
    day_html = day_tmpl.render(
        date_iso  = today_str,
        date_cz   = today_cz,
        summary   = summary_html,
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    day_path = ARCHIVE_DIR / f"{today_str}.html"
    day_path.write_text(day_html, encoding="utf-8")
    print(f"[INFO] Zapsáno: {day_path}")

    # --- Index --------------------------------------------------------------
    index_tmpl = env.get_template("ai_index.html.j2")
    index_html = index_tmpl.render(
        date_iso  = today_str,
        date_cz   = today_cz,
        summary   = summary_html,
        archive   = recent_30,
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    index_path = DOCS_DIR / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    print(f"[INFO] Zapsáno: {index_path}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            md = f.read()
    else:
        md = sys.stdin.read()

    build(md)
