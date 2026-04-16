"""
summarizer.py — Zavolá Gemini API a vytvoří strukturovaný přehled v češtině.
Používá nový balíček google-genai (google.generativeai je deprecated).
Při 503/přetížení zkouší fallback modely: 2.5-flash → 2.0-flash → 1.5-flash.
"""

import os
import sys
import json
import textwrap
import time
from google import genai
from google.genai import types

# Modely v pořadí preference — při přetížení nebo nedostupnosti přechází na další
# gemini-2.0-flash byl stažen (404 NOT_FOUND), nepoužíváme ho
MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

# Počet pokusů na každý model při dočasné chybě
RETRIES_PER_MODEL = 2
RETRY_DELAY = 30  # sekund

SYSTEM_PROMPT = textwrap.dedent("""\
    Jsi expert na kybernetickou bezpečnost a píšeš denní přehled pro české IT profesionály a bezpečnostní analytiky.
    Odpovídáš VÝHRADNĚ v češtině. Nepoužívej žádný jiný jazyk.
    Zaměřuješ se především na dění v České republice a na zprávy relevantní pro české organizace.
""")


def build_user_prompt(articles: list[dict]) -> str:
    lines = [
        "Níže je seznam článků z oblasti kybernetické bezpečnosti z posledních 24 hodin.",
        "Vytvoř strukturovaný přehled v češtině přesně v tomto pořadí sekcí:",
        "",
        "  1. 🇨🇿 NÚKIB — Co publikoval Národní úřad pro kybernetickou a informační bezpečnost",
        "     Sem patří POUZE články ze zdroje 'NÚKIB'. Pokud NÚKIB nic nepublikoval, napiš to explicitně.",
        "",
        "  2. 🇨🇿 Česká republika a region — Kybernetická bezpečnost v ČR a střední Evropě",
        "     Sem patří: zprávy ze zdroje 'CERT.CZ', incidenty nebo hrozby týkající se českých",
        "     organizací, institucí nebo infrastruktury, legislativa ČR/EU relevantní pro ČR",
        "     (NIS2, DORA, zákon o kybernetické bezpečnosti), a regionální dění.",
        "",
        "  3. 🌍 Svět — Významné světové události v kybernetické bezpečnosti",
        "     Sem patří globální hrozby, velké incidenty, zranitelnosti v rozšířeném SW/HW,",
        "     zprávy od ENISA, a zahraniční zprávy (Krebs, Hacker News, BleepingComputer, Schneier).",
        "     Vyber jen nejdůležitější — max 6–8 položek, ne vše.",
        "",
        "Pravidla formátování:",
        "- Každou sekci uveď jako nadpis: ## 🇨🇿 NÚKIB / ## 🇨🇿 Česká republika a region / ## 🌍 Svět",
        "- Pod každou sekci vypiš položky jako seznam",
        "- Každá položka musí mít formát:",
        "  **Název článku** — 2 až 3 věty shrnutí v češtině: co se stalo, proč je to důležité, jaký to má dopad nebo co by měli čtenáři udělat. [Zdroj: NázevZdroje] URL: https://...",
        "- Vyber MÉNĚ, ale DŮLEŽITĚJŠÍCH zpráv — raději 3–4 kvalitní položky než 8 povrchních.",
        "- Sekce 🌍 Svět: vyber max 4–5 nejzásadnějších světových zpráv.",
        "- Pokud pro sekci nejsou žádné články, napiš: *Žádné novinky v této sekci.*",
        "- Na úplný konec přidej sekci: ## 📋 Shrnutí dne (3–4 věty o tom nejdůležitějším pro české IT profesionály a bezpečnostní analytiky)",
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


def call_gemini(client, model: str, user_prompt: str) -> str:
    """Zavolá jeden konkrétní model. Hodí výjimku při chybě."""
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=4096,
        ),
    )
    return response.text.strip()


def summarize(articles: list[dict]) -> str:
    """
    Zavolá Gemini API a vrátí markdown text souhrnu.
    Zkouší postupně MODELS; při přetížení (503) přechází na další model.
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

    client = genai.Client(api_key=api_key)
    user_prompt = build_user_prompt(articles)

    for model in MODELS:
        print(f"[INFO] Zkouším model {model} pro {len(articles)} článků …", file=sys.stderr)
        for attempt in range(1, RETRIES_PER_MODEL + 1):
            try:
                text = call_gemini(client, model, user_prompt)
                print(f"[INFO] {model} odpověděl, délka: {len(text)} znaků", file=sys.stderr)
                return text
            except Exception as exc:
                err_str = str(exc)
                is_transient = any(x in err_str for x in ["503", "overloaded", "high demand", "UNAVAILABLE", "Timeout"])
                is_model_gone = any(x in err_str for x in ["404", "NOT_FOUND", "no longer available", "deprecated"])
                if is_transient or is_model_gone:
                    if is_model_gone:
                        # Model neexistuje — okamžitě na další
                        print(f"[WARN] {model} nedostupný/stažen, zkouším další model …", file=sys.stderr)
                        break
                    elif attempt < RETRIES_PER_MODEL:
                        print(f"[WARN] {model} přetížen (pokus {attempt}/{RETRIES_PER_MODEL}), čekám {RETRY_DELAY}s …", file=sys.stderr)
                        time.sleep(RETRY_DELAY)
                        continue
                    else:
                        print(f"[WARN] {model} selhal {RETRIES_PER_MODEL}x, zkouším další model …", file=sys.stderr)
                        break  # přejdi na další model
                else:
                    # Jiná chyba (API klíč, syntax) — není smysl zkoušet dál
                    print(f"[ERROR] {model}: {exc}", file=sys.stderr)
                    sys.exit(1)

    print("[ERROR] Všechny Gemini modely selhaly. Zkuste spustit workflow znovu.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            articles = json.load(f)
    else:
        articles = json.load(sys.stdin)

    result = summarize(articles)
    print(result)
