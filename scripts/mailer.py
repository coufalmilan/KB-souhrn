"""
mailer.py — Odešle kybernetický digest emailem přes Brevo SMTP.

Environment proměnné:
  BREVO_SMTP_USER     — přihlašovací email u Breva
  BREVO_SMTP_PASSWORD — SMTP heslo / API klíč z Breva
  EMAIL_FROM          — adresa odesílatele (např. digest@vasedomena.cz)
  EMAIL_TO            — příjemce (lze více oddělených čárkou)
"""

import os
import sys
import smtplib
import json
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape

BREVO_SMTP_HOST = "smtp-relay.brevo.com"
BREVO_SMTP_PORT = 587

BASE_DIR     = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"


def format_date_cz(d) -> str:
    months = [
        "", "ledna", "února", "března", "dubna", "května", "června",
        "července", "srpna", "září", "října", "listopadu", "prosince",
    ]
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day}. {months[d.month]} {d.year}"


def render_email_html(summary_html: str, today: date) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    tmpl = env.get_template("email.html.j2")
    return tmpl.render(
        date_iso = today.isoformat(),
        date_cz  = format_date_cz(today),
        summary  = summary_html,
    )


def send(summary_html: str, today: date | None = None) -> None:
    if today is None:
        today = date.today()

    smtp_user = os.environ.get("BREVO_SMTP_USER")
    smtp_pass = os.environ.get("BREVO_SMTP_PASSWORD")
    email_from = os.environ.get("EMAIL_FROM")
    email_to_raw = os.environ.get("EMAIL_TO", "")

    missing = [k for k, v in {
        "BREVO_SMTP_USER":     smtp_user,
        "BREVO_SMTP_PASSWORD": smtp_pass,
        "EMAIL_FROM":          email_from,
        "EMAIL_TO":            email_to_raw,
    }.items() if not v]

    if missing:
        print(f"[ERROR] Chybí env proměnné: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    recipients = [r.strip() for r in email_to_raw.split(",") if r.strip()]
    date_cz    = format_date_cz(today)

    # Extrahuj dynamický předmět z první řádky (formát "SUBJECT: ...")
    subject = f"Kyber digest — {date_cz}"  # fallback
    lines_for_subject = summary_html.strip().splitlines()
    for line in lines_for_subject[:3]:
        if line.upper().startswith("SUBJECT:"):
            extracted = line.split(":", 1)[1].strip()
            if extracted:
                subject = f"{extracted} [{date_cz}]"
                # Odstraň SUBJECT řádku z obsahu emailu
                summary_html = summary_html.replace(line, "", 1).lstrip("\n")
            break

    # Sestavení emailu
    html_body = render_email_html(summary_html, today)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = email_from
    msg["To"]      = ", ".join(recipients)

    # Textová fallback verze — odstraň HTML tagy
    import re
    plain = re.sub(r"<[^>]+>", " ", html_body)
    plain = re.sub(r" {2,}", " ", plain).strip()

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"[INFO] Odesílám email: {subject} → {recipients}")

    try:
        with smtplib.SMTP(BREVO_SMTP_HOST, BREVO_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, recipients, msg.as_string())
        print("[INFO] Email úspěšně odeslán.")
    except smtplib.SMTPException as exc:
        print(f"[ERROR] SMTP chyba: {exc}", file=sys.stderr)
        sys.exit(1)


def markdown_to_html(md: str) -> str:
    """Převede markdown na HTML (stejná logika jako v build_web.py)."""
    import re as _re
    html_lines = []
    lines = md.split("\n")
    in_ul = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False

    def inline(text: str) -> str:
        text = _re.sub(r'(https?://[^\s<>"]+)',
                       r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)
        text = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = _re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        return text

    for line in lines:
        s = line.rstrip()
        if s.startswith("## "):
            close_ul()
            html_lines.append(f'<h2 class="digest-h2">{inline(s[3:])}</h2>')
        elif s.startswith("### "):
            close_ul()
            html_lines.append(f'<h3 class="digest-h3">{inline(s[4:])}</h3>')
        elif s.startswith("- ") or s.startswith("* "):
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            html_lines.append(f"  <li>{inline(s[2:])}</li>")
        elif s == "":
            close_ul()
            html_lines.append("")
        else:
            close_ul()
            html_lines.append(f"<p>{inline(s)}</p>")
    close_ul()
    return "\n".join(html_lines)


if __name__ == "__main__":
    # Přijímá markdown (.md) nebo HTML soubor / stdin
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            content = f.read()
    else:
        content = sys.stdin.read()

    # Pokud jde o markdown, převeď na HTML
    if sys.argv[1].endswith(".md") if len(sys.argv) > 1 else False:
        content = markdown_to_html(content)

    send(content)
