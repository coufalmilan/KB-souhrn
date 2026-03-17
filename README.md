# 🛡️ Kybernetický bezpečnostní digest

Automatizovaný systém, který každý den ráno stáhne kybernetické novinky ze sedmi zdrojů, nechá je sumarizovat přes Gemini AI a výsledek:
- **publikuje jako statický web** na GitHub Pages
- **odešle emailem** přes Brevo SMTP

Vše běží zdarma na GitHub Actions — bez serveru, bez databáze.

---

## Sledované zdroje

| Zdroj | Metoda |
|-------|--------|
| [NÚKIB](https://nukib.gov.cz/cs/infoservis/hrozby/) | BeautifulSoup scraping |
| [CERT.CZ](https://www.cert.cz/) | RSS |
| [Krebs on Security](https://krebsonsecurity.com/) | RSS |
| [The Hacker News](https://thehackernews.com/) | RSS |
| [BleepingComputer](https://www.bleepingcomputer.com/) | RSS |
| [ENISA](https://www.enisa.europa.eu/) | RSS |
| [Schneier on Security](https://schneier.com/) | RSS |

---

## Rychlé nastavení

### 1. Forkni / klonuj repozitář

```bash
git clone https://github.com/TVŮJ_USERNAME/NÁZEV_REPO.git
cd NÁZEV_REPO
```

### 2. Nastav GitHub Secrets

Přejdi do repozitáře → **Settings → Secrets and variables → Actions → New repository secret** a přidej:

| Secret | Popis |
|--------|-------|
| `GEMINI_API_KEY` | API klíč z [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `BREVO_SMTP_USER` | Přihlašovací email u Breva (viz níže) |
| `BREVO_SMTP_PASSWORD` | SMTP heslo / master password z Breva |
| `EMAIL_FROM` | Adresa odesílatele, např. `digest@vasedomena.cz` |
| `EMAIL_TO` | Příjemce (nebo více oddělených čárkou), např. `ja@firma.cz,kolega@firma.cz` |

#### Jak získat Brevo SMTP přihlašovací údaje

1. Zaregistruj se na [brevo.com](https://www.brevo.com/) (zdarma do 300 emailů/den)
2. Přejdi na **Settings → SMTP & API → SMTP**
3. Zkopíruj **Login** (= `BREVO_SMTP_USER`) a **Master password** (= `BREVO_SMTP_PASSWORD`)

### 3. Povol GitHub Pages

1. V repozitáři přejdi na **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, složka: `/docs`
4. Ulož — web bude za chvíli dostupný na `https://TVŮJ_USERNAME.github.io/NÁZEV_REPO/`

### 4. První ruční spuštění

Přejdi na záložku **Actions → Kyber Digest — denní generování → Run workflow → Run workflow**.

Po úspěšném dokončení (~2 minuty) se:
- Aktualizuje `docs/index.html` s dnešním digestem
- Vytvoří `docs/archive/YYYY-MM-DD.html`
- Odešle email na `EMAIL_TO`

---

## Plánované spouštění

Workflow se spouští každý den v **6:45 UTC** (= 7:45 SEČ / 8:45 SELČ), viz `.github/workflows/daily.yml`:

```yaml
schedule:
  - cron: '45 6 * * *'
```

Čas můžeš změnit editací tohoto souboru.

---

## Struktura projektu

```
/
├── .github/
│   └── workflows/
│       └── daily.yml          ← GitHub Actions workflow
├── scripts/
│   ├── scraper.py             ← Stahuje novinky z RSS + NÚKIB
│   ├── summarizer.py          ← Volá Gemini API
│   ├── build_web.py           ← Generuje HTML stránky
│   └── mailer.py              ← Odesílá email přes Brevo SMTP
├── docs/                      ← GitHub Pages složka
│   ├── index.html             ← Dnešní digest + archív
│   └── archive/
│       ├── index.json         ← Metadata archívu
│       └── YYYY-MM-DD.html    ← Archívní stránky
├── templates/
│   ├── index.html.j2          ← Šablona hlavní stránky
│   ├── day.html.j2            ← Šablona archívní stránky
│   └── email.html.j2          ← Šablona emailu
├── requirements.txt
└── README.md
```

---

## Lokální testování

```bash
# Instalace závislostí
pip install -r requirements.txt

# Nastav env proměnné
export GEMINI_API_KEY="tvůj_klíč"
export BREVO_SMTP_USER="tvůj_brevo_login"
export BREVO_SMTP_PASSWORD="tvůj_brevo_heslo"
export EMAIL_FROM="digest@vasedomena.cz"
export EMAIL_TO="ja@firma.cz"

# Krok po kroku
python scripts/scraper.py > /tmp/articles.json
python scripts/summarizer.py /tmp/articles.json > /tmp/summary.md
python scripts/build_web.py /tmp/summary.md
python scripts/mailer.py "docs/archive/$(date +%Y-%m-%d).html"
```

---

## Řešení problémů

**Workflow se nespustí automaticky**
GitHub Actions může mít zpoždění až 15 minut. Pokud se nespouští vůbec, zkontroluj záložku Actions, zda není workflow deaktivované.

**NÚKIB scraping nefunguje**
NÚKIB občas mění strukturu HTML. Zkontroluj selektory v `scripts/scraper.py` ve funkci `fetch_nukib()`.

**Gemini API vrátí chybu**
Zkontroluj, zda máš platný `GEMINI_API_KEY` a zda model `gemini-2.0-flash` je dostupný ve tvém regionu.

**Email se neodesílá**
Ověř, že `BREVO_SMTP_USER` a `BREVO_SMTP_PASSWORD` jsou správně nastaveny. Bezplatný Brevo účet je omezen na 300 emailů/den.

---

## Licence

MIT — použij, uprav, sdílej dle libosti.
