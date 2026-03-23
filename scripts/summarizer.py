"""
summarizer.py — Zavolá Gemini API a vytvoří strukturovaný přehled v češtině.
"""

import os
import sys
import json
import textwrap
import google.generativeai as genai

MODEL_NAME = "gemini-2.5-flash"

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
