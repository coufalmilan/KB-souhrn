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
    subject    = f"Kyber digest — {date_cz}"

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


if __name__ == "__main__":
    # Čte HTML souhrn ze stdin nebo ze souboru
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            html = f.read()
    else:
        html = sys.stdin.read()

    send(html)
