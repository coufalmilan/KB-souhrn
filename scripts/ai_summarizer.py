"""
ai_summarizer.py — Zavolá Gemini API a vytvoří strukturovaný přehled AI novinek v češtině.
Používá nový balíček google-genai (google.generativeai je deprecated).
Při 503/přetížení zkouší fallback modely: 2.5-flash → 2.0-flash → 2.0-flash-lite.
"""

import os
import sys
import json
import textwrap
import time
from google import genai
from google.genai import types

# Modely v pořadí preference — při přetížení nebo nedostupnosti přechází na další
MODELS = [
    "gemini-2.5-flash",      # primární (nejkvalitnější)
    "gemini-2.0-flash",      # stabilní záloha
    "gemini-2.0-flash-lite", # odlehčená záloha
]

# Počet pokusů na každý model při dočasné chybě
RETRIES_PER_MODEL = 2
RETRY_DELAY = 30  # sekund

SYSTEM_PROMPT = textwrap.dedent("""\
    Jsi expert na umělou inteligenci a technologie a píšeš denní přehled pro české technologické profesionály, výzkumníky a manažery.
    Odpovídáš VÝHRADNĚ v češtině. Nepoužívej žádný jiný jazyk.
    Zaměřuješ se na nejdůležitější dění ve světě AI — nové modely, výzkumné průlomy, byznysové dopady a regulaci.
""")


def build_user_prompt(articles: list[dict]) -> str:
    lines = [
        "Níže je seznam článků z oblasti umělé inteligence z posledních 24 hodin.",
        "Vytvoř profesionální AI newsletter v češtině přesně v tomto pořadí sekcí.",
        "",
        "══════════════════════════════════════════",
        "PRVNÍ ŘÁDEK výstupu musí být předmět emailu ve formátu:",
        "SUBJECT: <konkrétní, úderný předmět — max 60 znaků, bez data, hlavní zpráva dne>",
        "Příklady: 'SUBJECT: OpenAI vydal GPT-5 — co to znamená pro vaši práci'",
        "          'SUBJECT: EU AI Act vstupuje v platnost — co musíte vědět'",
        "          'SUBJECT: Deepfake podvody rostou — jak se bránit'",
        "══════════════════════════════════════════",
        "",
        "Poté napiš newsletter s těmito sekcemi:",
        "",
        "  1. ## 🤖 Modely & Výzkum",
        "     Nové AI modely, vědecké průlomy, benchmarky. Sem patří: vydání nových modelů",
        "     (GPT, Gemini, Claude, Llama atd.), výzkumné výsledky, nové technické přístupy.",
        "     Max 4 položky — pouze ty nejdůležitější.",
        "",
        "  2. ## 🏢 Byznys & Průmysl",
        "     AI ve firmách, investice, produkty. Investiční kola, akvizice, nové AI služby,",
        "     nasazení AI ve firmách, strategická partnerství.",
        "     Max 3–4 položky.",
        "",
        "  3. ## 🇪🇺 Regulace & Etika",
        "     Pouze pokud jsou relevantní zprávy. EU AI Act, národní AI strategie, etické otázky,",
        "     AI safety, deepfakes, autorská práva, dopady na trh práce.",
        "     Pokud nic relevantního není, tuto sekci VYNECH úplně.",
        "",
        "  4. ## 💡 Příběh / Případ z praxe",
        "     Vyber JEDEN zajímavý případ, nasazení nebo incident týkající se AI z dnešních zpráv.",
        "     Popiš: co se stalo → jaký to mělo dopad → co si z toho odnést.",
        "     Délka: 3–5 vět. Srozumitelné i pro ne-technické čtenáře.",
        "",
        "  5. ## 🛠️ Praktický tip",
        "     JEDEN konkrétní a okamžitě použitelný tip vyplývající z dnešních zpráv.",
        "     Jak využít AI nástroj, jak se bránit AI hrozbám, nebo jak se připravit na změny.",
        "     Formát: **Co udělat:** [krok] **Proč:** [vysvětlení] **Jak:** [postup nebo odkaz]",
        "",
        "  6. ## 📋 Shrnutí a výzva k akci",
        "     2–3 věty o nejdůležitějším dění v AI pro české profesionály.",
        "     Pak POVINNĚ jedna konkrétní výzva k akci:",
        "     👉 **Doporučená akce:** [co přesně má čtenář udělat nebo vyzkoušet]",
        "",
        "Pravidla formátování:",
        "- Každou položku piš jako: **Název** — 2–3 věty co se stalo, proč je to důležité, co čtenář získá. [Zdroj: X] URL: https://...",
        "- Raději 3–4 kvalitní položky než 8 povrchních.",
        "- Vždy uváděj URL zdroje.",
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
            "z monitorovaných AI zdrojů.\n"
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] Chybí proměnná prostředí GEMINI_API_KEY", file=sys.stderr)
        sys.exit(1)

    client = genai.Client(api_key=api_key)
    user_prompt = build_user_prompt(articles)

    for model in MODELS:
        print(f"[INFO] Zkouším model {model} pro {len(articles)} AI článků …", file=sys.stderr)
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
