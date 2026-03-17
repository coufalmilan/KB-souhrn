"""
summarizer.py — Zavolá Gemini API a vytvoří strukturovaný přehled v češtině.
"""

import os
import sys
import json
import textwrap
import google.generativeai as genai

MODEL_NAME = "gemini-1.5-flash"

CATEGORIES = [
    "Hrozby a incidenty",
    "Zranitelnosti",
    "Legislativa a regulace",
    "Zajímavosti",
]

SYSTEM_PROMPT = textwrap.dedent("""\
    Jsi expert na kybernetickou bezpečnost a píšeš denní přehled pro české IT profesionály.
    Odpovídáš VÝHRADNĚ v češtině. Nepoužívej žádný jiný jazyk.
""")


def build_user_prompt(articles: list[dict]) -> str:
    lines = [
        "Níže je seznam článků z oblasti kybernetické bezpečnosti z posledních 24 hodin.",
        "Vytvoř strukturovaný přehled v češtině rozdělený do těchto kategorií:",
        "  1. Hrozby a incidenty",
        "  2. Zranitelnosti",
        "  3. Legislativa a regulace",
        "  4. Zajímavosti",
        "",
        "Pravidla formátování:",
        "- Každou kategorii uveď jako nadpis: ## Název kategorie",
        "- Pod každou kategorii vypiš relevantní položky jako seznam",
        "- Každá položka musí mít formát:",
        "  **Název článku** — Jednověté shrnutí v češtině. [Zdroj: NázevZdroje] URL: https://...",
        "- Pokud pro kategorii nejsou žádné relevantní články, napiš: *Žádné novinky v této kategorii.*",
        "- Na konec přidej krátký odstavec ## Celkový přehled (2–3 věty, co je dnes nejdůležitější).",
        "- Celý výstup musí být v češtině.",
        "",
        "Články:",
    ]
    for i, a in enumerate(articles, 1):
        lines.append(
            f"{i}. [{a['source']}] {a['title']} | {a['url']}"
            + (f" | Perex: {a['summary'][:200]}" if a.get("summary") else "")
        )
    return "\n".join(lines)


def summarize(articles: list[dict]) -> str:
    """
    Zavolá Gemini API a vrátí markdown text souhrnu.
    Pokud articles je prázdný, vrátí informativní zprávu.
    """
    if not articles:
        return (
            "## Žádné novinky\n\n"
            "Za posledních 24 hodin nebyly nalezeny žádné nové články "
            "z monitorovaných zdrojů.\n"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] Chybí proměnná prostředí GEMINI_API_KEY", file=sys.stderr)
        sys.exit(1)

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
    )

    user_prompt = build_user_prompt(articles)

    print(f"[INFO] Volám Gemini ({MODEL_NAME}) pro {len(articles)} článků …")

    try:
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=4096,
            ),
        )
        text = response.text.strip()
        print("[INFO] Gemini odpověděl, délka:", len(text), "znaků")
        return text
    except Exception as exc:
        print(f"[ERROR] Gemini API: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    # Čte JSON ze stdin nebo ze souboru articles.json
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            articles = json.load(f)
    else:
        articles = json.load(sys.stdin)

    result = summarize(articles)
    print(result)
