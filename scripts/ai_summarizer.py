"""
ai_summarizer.py — Zavolá Gemini API a vytvoří strukturovaný přehled AI novinek v češtině.
Používá nový balíček google-genai (google.generativeai je deprecated).
"""

import os
import sys
import json
import textwrap
import time
from google import genai
from google.genai import types

MODEL_NAME = "gemini-2.5-flash"

# Retry nastavení pro případ přetížení API (503)
MAX_RETRIES = 4
RETRY_BASE_DELAY = 30  # sekund, zdvojnásobí se s každým pokusem

SYSTEM_PROMPT = textwrap.dedent("""\
    Jsi expert na umělou inteligenci a technologie a píšeš denní přehled pro české technologické profesionály, výzkumníky a manažery.
    Odpovídáš VÝHRADNĚ v češtině. Nepoužívej žádný jiný jazyk.
    Zaměřuješ se na nejdůležitější dění ve světě AI — nové modely, výzkumné průlomy, byznysové dopady a regulaci.
""")


def build_user_prompt(articles: list[dict]) -> str:
    lines = [
        "Níže je seznam článků z oblasti umělé inteligence z posledních 24 hodin.",
        "Vytvoř strukturovaný přehled v češtině přesně v tomto pořadí sekcí:",
        "",
        "  1. 🤖 Modely & Výzkum — Nové AI modely, vědecké průlomy a technické novinky",
        "     Sem patří: vydání nových modelů (GPT, Gemini, Claude, Llama atd.), výzkumné články,",
        "     technické výsledky, benchmarky, nové architektonické přístupy.",
        "",
        "  2. 🏢 Byznys & Průmysl — AI ve firmách, investice a produkty",
        "     Sem patří: investiční kola, akvizice, nové AI produkty a služby, nasazení AI",
        "     ve firmách, strategická partnerství, výsledky velkých technologických společností.",
        "",
        "  3. 🇪🇺 Regulace & Etika — AI Act, politika, etická témata",
        "     Sem patří: EU AI Act a jeho implementace, národní AI strategie, etické otázky,",
        "     bezpečnost AI (AI safety), bias, deepfakes, autorská práva, dopady na trh práce.",
        "",
        "Pravidla formátování:",
        "- Každou sekci uveď jako nadpis: ## 🤖 Modely & Výzkum / ## 🏢 Byznys & Průmysl / ## 🇪🇺 Regulace & Etika",
        "- Pod každou sekci vypiš položky jako seznam",
        "- Každá položka musí mít formát:",
        "  **Název článku** — 2 až 3 věty shrnutí v češtině: co se stalo, proč je to důležité, jaký to má dopad. [Zdroj: NázevZdroje] URL: https://...",
        "- Vyber MÉNĚ, ale DŮLEŽITĚJŠÍCH zpráv — raději 3–4 kvalitní položky na sekci než 8 povrchních.",
        "- Pokud pro sekci nejsou žádné články, napiš: *Žádné novinky v této sekci.*",
        "- Na úplný konec přidej sekci: ## 📋 Shrnutí dne (3–4 věty o nejdůležitějším dění v AI pro české profesionály)",
        "- Celý výstup musí být v češtině.",
        "",
        "Články (zdroj je uveden v hranatých závorkách):",
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
            "z monitorovaných AI zdrojů.\n"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] Chybí proměnná prostředí GEMINI_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    user_prompt = build_user_prompt(articles)

    print(f"[INFO] Volám Gemini ({MODEL_NAME}) pro {len(articles)} AI článků …", file=sys.stderr)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.3,
                    max_output_tokens=4096,
                ),
            )
            text = response.text.strip()
            print(f"[INFO] Gemini odpověděl, délka: {len(text)} znaků", file=sys.stderr)
            return text

        except Exception as exc:
            err_str = str(exc)
            is_transient = any(x in err_str for x in ["503", "overloaded", "high demand", "Timeout", "quota"])
            if is_transient and attempt < MAX_RETRIES:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(
                    f"[WARN] Gemini API dočasná chyba (pokus {attempt}/{MAX_RETRIES}): {exc}",
                    file=sys.stderr,
                )
                print(f"[WARN] Čekám {delay}s před dalším pokusem …", file=sys.stderr)
                time.sleep(delay)
                continue
            print(f"[ERROR] Gemini API selhalo po {attempt} pokusech: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            articles = json.load(f)
    else:
        articles = json.load(sys.stdin)

    result = summarize(articles)
    print(result)
