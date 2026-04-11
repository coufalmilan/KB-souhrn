"""
check_workday.py — Zkontroluje, zda je dnešní den pracovní den.
Výstup: "skip=true" (víkend nebo svátek) nebo "skip=false" (pracovní den).
Používá se v GitHub Actions: výstup se čte jako step output.
"""

import datetime
import sys


def easter_date(year: int) -> datetime.date:
    """Gaussův algoritmus pro výpočet data Velikonoc (gregoriánský kalendář)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)


def czech_holidays(year: int) -> set:
    """Vrátí množinu českých státních svátků pro daný rok."""
    holidays = {
        datetime.date(year, 1, 1),   # Nový rok / Den obnovy samostatného českého státu
        datetime.date(year, 5, 1),   # Svátek práce
        datetime.date(year, 5, 8),   # Den vítězství
        datetime.date(year, 7, 5),   # Den slovanských věrozvěstů Cyrila a Metoděje
        datetime.date(year, 7, 6),   # Den upálení mistra Jana Husa
        datetime.date(year, 9, 28),  # Den české státnosti
        datetime.date(year, 10, 28), # Den vzniku samostatného československého státu
        datetime.date(year, 11, 17), # Den boje za svobodu a demokracii
        datetime.date(year, 12, 24), # Štědrý den
        datetime.date(year, 12, 25), # 1. svátek vánoční
        datetime.date(year, 12, 26), # 2. svátek vánoční
    }
    easter = easter_date(year)
    holidays.add(easter - datetime.timedelta(days=2))  # Velký pátek
    holidays.add(easter + datetime.timedelta(days=1))  # Velikonoční pondělí
    return holidays


def main():
    today = datetime.date.today()

    # Víkend (sobota=5, neděle=6)
    if today.weekday() >= 5:
        print(f"skip=true", flush=True)
        print(f"[INFO] Dnes je víkend ({today.strftime('%A, %d.%m.%Y')}), přeskakuji.", file=sys.stderr)
        return

    # Státní svátek
    holidays = czech_holidays(today.year)
    if today in holidays:
        print(f"skip=true", flush=True)
        print(f"[INFO] Dnes je státní svátek ({today.isoformat()}), přeskakuji.", file=sys.stderr)
        return

    print(f"skip=false", flush=True)
    print(f"[INFO] Dnes je pracovní den ({today.isoformat()}), spouštím digest.", file=sys.stderr)


if __name__ == "__main__":
    main()
