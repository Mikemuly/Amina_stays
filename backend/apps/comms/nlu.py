"""Rule-based understanding for SMS / USSD free text (English + Kiswahili, typo-tolerant where cheap).

Deliberately deterministic: the brief warns that a live model call failing mid-demo is worse than a
slightly stricter parser. Anything ambiguous falls back to the question-and-relay path.
"""

import re
from datetime import date, timedelta

from apps.core.utils import today, weekend_start

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    # Kiswahili / Italian / German / French spellings that differ
    "mac": 3,
    "mei": 5,
    "ago": 8,
    "okt": 10,
    "des": 12,
    "dis": 12,
    "januari": 1,
    "februari": 2,
    "machi": 3,
    "aprili": 4,
    "juni": 6,
    "julai": 7,
    "agosti": 8,
    "septemba": 9,
    "oktoba": 10,
    "novemba": 11,
    "desemba": 12,
    "gen": 1,
    "mag": 5,
    "giu": 6,
    "lug": 7,
    "set": 9,
    "ott": 10,
    "dic": 12,
    "mär": 3,
    "mai": 5,
    "dez": 12,
    "janv": 1,
    "févr": 2,
    "fev": 2,
    "avr": 4,
    "juil": 7,
    "aoû": 8,
    "aou": 8,
    "déc": 12,
}
SW_NUMBERS = {
    "moja": 1,
    "mmoja": 1,
    "mbili": 2,
    "wawili": 2,
    "tatu": 3,
    "watatu": 3,
    "nne": 4,
    "wanne": 4,
    "tano": 5,
    "watano": 5,
    "sita": 6,
    "saba": 7,
}
EN_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "a couple": 2, "couple": 2}
SWAHILI_HINTS = {
    "habari",
    "nataka",
    "naomba",
    "chumba",
    "vyumba",
    "bei",
    "kesho",
    "leo",
    "usiku",
    "wikendi",
    "watu",
    "sisi",
    "nafasi",
    "asante",
    "sawa",
    "ndiyo",
    "hapana",
    "mambo",
    "jambo",
    "tafadhali",
    "lini",
    "ngapi",
    "wapi",
    "kulala",
    "maji",
    "stima",
}

_WS = re.compile(r"\s+")


def clean(text):
    return _WS.sub(" ", (text or "").strip())


def looks_swahili(text):
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return len(words & SWAHILI_HINTS) >= 1


def _num(token):
    token = token.lower()
    if token.isdigit():
        return int(token)
    return SW_NUMBERS.get(token) or EN_NUMBERS.get(token)


def parse_guests(text):
    t = (text or "").lower()
    m = re.search(r"(\d+|one|two|three|four|five|six|seven)\s*(people|persons?|guests?|pax|adults?|of us|ppl)", t)
    if m:
        return _num(m.group(1))
    m = re.search(r"\bfor\s+(\d+|two|three|four|five|six)\b(?!\s*(nights?|days?|n\b))", t)
    if m:
        return _num(m.group(1))
    m = re.search(r"\bwatu\s+(\d+|\w+)", t) or re.search(r"\bsisi\s+(wawili|watatu|wanne|watano)", t)
    if m:
        return _num(m.group(1))
    if re.search(r"\b(couple|my (wife|husband|partner)|two of us)\b", t):
        return 2
    return None


def parse_nights(text):
    t = (text or "").lower()
    m = re.search(r"(\d+|one|two|three|four|five|six|seven)\s*(nights?|n\b|nts|days?)", t) or re.search(
        r"\b(usiku|siku)\s*(\d+|\w+)", t
    )
    if not m:
        return None
    n = _num(m.group(2) if m.group(1) in ("usiku", "siku") else m.group(1))
    return n if n and 0 < n <= 60 else None


def _date(day, month, ref):
    year = ref.year
    try:
        d = date(year, month, day)
    except ValueError:
        return None
    if d < ref - timedelta(days=1):
        try:
            d = date(year + 1, month, day)
        except ValueError:
            return None
    return d


def parse_dates(text, ref=None):
    """Returns (check_in, check_out); either may be None. check_out defaults from 'N nights'."""
    ref = ref or today()
    t = (text or "").lower()
    nights = parse_nights(t)
    ci = co = None

    m = re.search(r"(\d{4})-(\d{2})-(\d{2})(?:\s*(?:to|-|until|hadi)\s*(\d{4})-(\d{2})-(\d{2}))?", t)
    if m:
        ci = _safe(int(m[1]), int(m[2]), int(m[3]))
        if m[4]:
            co = _safe(int(m[4]), int(m[5]), int(m[6]))
    if not ci:  # "5-8 dec", "5 to 8 december", "from 5th to 8th dec"
        for m in re.finditer(
            r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:-|to|until|till|hadi|–)\s*(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?([a-zäéûô]{3,9})",
            t,
        ):
            month = _month(m[3])
            if month:
                ci, co = _date(int(m[1]), month, ref), _date(int(m[2]), month, ref)
                if ci and co and co <= ci:
                    co = None
                break
    # "5 dec", "5th of december", "dec 5" - the first number+word pair isn't always the date ("2 people on 5 dec")
    if not ci:
        for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?([a-zäéûô]{3,9})\b", t):
            if month := _month(m[2]):
                ci = _date(int(m[1]), month, ref)
                break
    if not ci:
        for m in re.finditer(r"\b([a-zäéûô]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\b", t):
            if month := _month(m[1]):
                ci = _date(int(m[2]), month, ref)
                break
    if not ci:  # "5/12" or "05/12/2026" (day first, as in Kenya)
        m = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t)
        if m and 1 <= int(m[2]) <= 12:
            ci = (
                _date(int(m[1]), int(m[2]), ref)
                if not m[3]
                else _safe(int(m[3]) + (2000 if len(m[3]) == 2 else 0), int(m[2]), int(m[1]))
            )
    if not ci:
        if re.search(r"\b(tonight|today|leo|usiku wa leo|stasera|heute|ce soir)\b", t):
            ci = ref
        elif re.search(r"\b(tomorrow|kesho|domani|morgen|demain)\b", t):
            ci = ref + timedelta(days=1)
        elif re.search(r"\b(next weekend|wikendi ijayo)\b", t):
            ci = weekend_start(ref) + timedelta(days=7)
            co = co or ci + timedelta(days=2)
        elif re.search(r"\b(this weekend|weekend|wikendi|week-end|wochenende|fine settimana)\b", t):
            ci = weekend_start(ref)
            co = co or ci + timedelta(days=2 if ci.weekday() == 4 else 1)
    if ci and not co:
        co = ci + timedelta(days=nights or 1)
    return ci, co


def _safe(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _month(word):
    return MONTHS.get(word[:4]) or MONTHS.get(word[:3])


def parse_area(text, areas):
    t = (text or "").lower()
    for a in areas:
        if a.name.lower() in t or a.slug.replace("-", " ") in t:
            return a
    return None


def parse_eta(text):
    t = (text or "").lower()
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|h|hrs|uhr)?\b", t)
    if not m:
        return None
    h, mins, suffix = int(m[1]), int(m[2] or 0), m[3]
    if suffix == "pm" and h < 12:
        h += 12
    if suffix == "am" and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= mins <= 59):
        return None
    return f"{h:02d}:{mins:02d}"


BOOKING_WORDS = re.compile(
    r"\b(free|available|availability|vacan\w*|book|reserve|stay|room|rooms|apartment|studio|place|nights|nafasi|chumba|vyumba|"
    r"kulala|nyumba|malazi|kukaa|usiku|same as last time|the usual|disponib\w*|libero|notti|frei|zimmer|n[aä]chte|chambre|nuits)\b",
    re.IGNORECASE,
)


def looks_like_booking(text):
    if BOOKING_WORDS.search(text or ""):
        return True
    ci, co = parse_dates(text or "")
    # "Diani 12 Dec - 15 Dec, 2 of us" / "Old Town 5 Dec 1 night"
    return bool(ci and co and (parse_guests(text or "") or parse_nights(text or "")))
