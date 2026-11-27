"""Small shared helpers: phone numbers, Kenya-time dates, money, text."""

import re
from datetime import date, datetime, timedelta

from django.utils import timezone

# ---------- phone numbers ----------


def normalize_phone(raw):
    """Normalise to E.164. Kenyan local formats (07.., 01.., 2547.., 7..) become +2547/+2541...
    A trunk 0 written after the country code ('+254 (0)712…', '+2540712…') is dropped, as it isn't dialled."""
    if not raw:
        return None
    p = re.sub(r"\(0\)", "", str(raw))
    p = re.sub(r"[\s\-().]", "", p)
    if p.startswith("00"):
        p = "+" + p[2:]
    if re.fullmatch(r"0[17]\d{8}", p):
        p = "+254" + p[1:]
    elif re.fullmatch(r"\+?2540?[17]\d{8}", p):
        p = "+254" + p[-9:]
    elif re.fullmatch(r"[17]\d{8}", p):
        p = "+254" + p
    return p if re.fullmatch(r"\+\d{9,15}", p) else None


def same_phone(a, b):
    if not a or not b:
        return False
    return re.sub(r"\D", "", a)[-9:] == re.sub(r"\D", "", b)[-9:]


def is_kenyan(phone):
    return bool(phone) and phone.startswith("+254")


def mask_phone(phone):
    if not phone or len(phone) < 7:
        return phone or ""
    return phone[:5] + "•" * (len(phone) - 8) + phone[-3:]


def spoken_digits(text):
    """'+254712' -> '2 5 4 7 1 2' so text-to-speech reads digits one by one."""
    return " ".join(ch for ch in str(text) if ch.isalnum())


# ---------- dates (all business dates are Kenya time, Africa/Nairobi) ----------


def now():
    return timezone.now()


def today():
    return timezone.localdate()


def local_now():
    return timezone.localtime()


def kenya_hour():
    return timezone.localtime().hour


def add_days(d, n):
    return d + timedelta(days=n)


def nights_between(check_in, check_out):
    return (check_out - check_in).days


def daterange(start, end):
    d = start
    while d < end:
        yield d
        d += timedelta(days=1)


def weekend_start(ref=None):
    """Friday check-in for 'this weekend' (if it's already Sat/Sun, start today)."""
    t = ref or today()
    dow = t.weekday()  # Mon=0 .. Sun=6
    if dow in (5, 6):
        return t
    return t + timedelta(days=(4 - dow) % 7)


def parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def at_local(d, hhmm):
    """Aware datetime for a local date + 'HH:MM'."""
    hour, minute = (int(x) for x in (hhmm or "00:00").split(":")[:2])
    return timezone.make_aware(datetime(d.year, d.month, d.day, hour, minute))


def nice_date(d, lang="en"):
    """'Fri 5 Dec' (English) / 'Ijumaa 5 Des' (Kiswahili)."""
    if not d:
        return ""
    if lang == "sw":
        days = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
        months = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"]
    elif lang == "fr":
        days = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
        months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
    elif lang == "de":
        days = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
        months = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]
    elif lang == "it":
        days = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]
        months = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
    else:
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{days[d.weekday()]} {d.day} {months[d.month - 1]}"


def nice_time(hhmm):
    """'14:00' -> '2pm', '10:30' -> '10:30am'."""
    if not hhmm:
        return ""
    h, m = (int(x) for x in hhmm.split(":")[:2])
    suffix = "am" if h < 12 else "pm"
    h12 = h % 12 or 12
    return f"{h12}{f':{m:02d}' if m else ''}{suffix}"


# ---------- money ----------


def kes(amount):
    return f"KES {round(amount or 0):,}"


# ---------- text ----------


def truncate(text, limit):
    text = text or ""
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


def first_name(name):
    return (name or "").strip().split(" ")[0] if name else ""
