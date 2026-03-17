"""
build_web.py — Generuje statické HTML stránky z výstupu summarizeru.

Výstup:
  docs/index.html               — dnešní souhrn + archív posledních 30 dní
  docs/archive/YYYY-MM-DD.html  — archívní stránka pro konkrétní den
"""

import os
import sys
import re
import json
from pathlib import Path
from datetime import date, datetime, timezone
from jinja2 import Environment, FileSystemLoader, select_autoescape

BASE_DIR     = Path(__file__).resolve().parent.parent
DOCS_DIR     = BASE_DIR / "docs"
ARCHIVE_DIR  = DOCS_DIR / "archive"
TEMPLATE_DIR = BASE_DIR / "templates"
ARCHIVE_INDEX = ARCHIVE_DIR / "index.json"

MAX_ARCHIVE_IN_INDEX = 30


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

def load_archive_index() -> list[dict]:
    """Načte seznam archívních záznamů z archive/index.json."""
    if ARCHIVE_INDEX.exists():
        with open(ARCHIVE_INDEX, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_archive_index(entries: list[dict]) -> None:
    ARCHIVE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(ARCHIVE_INDEX, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def markdown_to_html(md: str) -> str:
    """
    Velmi jednoduchý Markdown → HTML konvertor (bez závislostí).
    Zvládá: nadpisy ##/###, **tučný**, *kurzíva*, URL, odstavce, seznamy.
    """
    html_lines = []
    lines = md.split("\n")
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

    def inline(text: str) -> str:
        # Automaticky propojit URL
        text = re.sub(
            r'(https?://[^\s<>"]+)',
            r'<a href="\1" target="_blank" rel="noopener">\1</a>',
            text,
        )
        # **tučný**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # *kurzíva*
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        return text

    for line in lines:
        stripped = line.rstrip()

        if stripped.startswith("## "):
            close_ul()
            heading = inline(stripped[3:])
            html_lines.append(f'<h2 class="digest-h2">{heading}</h2>')
        elif stripped.startswith("### "):
            close_ul()
            heading = inline(stripped[4:])
            html_lines.append(f'<h3 class="digest-h3">{heading}</h3>')
        elif stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            item = inline(stripped[2:])
            html_lines.append(f"  <li>{item}</li>")
        elif stripped == "":
            close_ul()
            html_lines.append("")
        else:
            close_ul()
            html_lines.append(f"<p>{inline(stripped)}</p>")

    close_ul()
    return "\n".join(html_lines)


def format_date_cz(d: date | str) -> str:
    """Naformátuje datum česky: 17. března 2026."""
    months = [
        "", "ledna", "února", "března", "dubna", "května", "června",
        "července", "srpna", "září", "října", "listopadu", "prosince",
    ]
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day}. {months[d.month]} {d.year}"


# ---------------------------------------------------------------------------
# Hlavní funkce
# ---------------------------------------------------------------------------

def build(summary_md: str, today: date | None = None) -> None:
    if today is None:
        today = date.today()

    today_str     = today.isoformat()          # "2026-03-17"
    today_cz      = format_date_cz(today)      # "17. března 2026"
    summary_html  = markdown_to_html(summary_md)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Jinja2 environment
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["markdown_to_html"] = markdown_to_html
    env.filters["format_date_cz"]   = format_date_cz

    # --- Archívní záznamy ---------------------------------------------------
    archive_entries = load_archive_index()

    # Přidej nebo aktualizuj dnešní záznam
    existing = next((e for e in archive_entries if e["date"] == today_str), None)
    if existing:
        existing["title"] = f"Digest {today_cz}"
    else:
        archive_entries.insert(0, {
            "date":  today_str,
            "title": f"Digest {today_cz}",
            "url":   f"archive/{today_str}.html",
        })

    # Udržuj max 30 záznamů (nejnovější první)
    archive_entries = sorted(archive_entries, key=lambda e: e["date"], reverse=True)
    save_archive_index(archive_entries)

    recent_30 = archive_entries[:MAX_ARCHIVE_IN_INDEX]

    # --- Stránka dne (archive/YYYY-MM-DD.html) ------------------------------
    day_tmpl = env.get_template("day.html.j2")
    day_html = day_tmpl.render(
        date_iso  = today_str,
        date_cz   = today_cz,
        summary   = summary_html,
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )
    day_path = ARCHIVE_DIR / f"{today_str}.html"
    day_path.write_text(day_html, encoding="utf-8")
    print(f"[INFO] Zapsáno: {day_path}")

    # --- Index (docs/index.html) --------------------------------------------
    index_tmpl = env.get_template("index.html.j2")
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
