"""Local guide: the same places and events by USSD, SMS, voice and the web.

A tourist on a feature phone, or with no data, gets the same local knowledge as one browsing the site: categories
on a 160-character USSD screen, the details and a map link by SMS, the top picks read out on a call."""

import math
import unicodedata
from datetime import timedelta

from django.db.models import F

from apps.core.utils import nice_date, today

from .models import Event, Place

LABELS = dict(Place.CATEGORIES)
# short labels for USSD screens and SMS menus ("top" and "events" aren't place categories)
SHORT = {
    "en": {
        "top": "Top picks",
        "beaches": "Beaches & sea",
        "sights": "Sights & history",
        "nature": "Nature & wildlife",
        "food": "Food & drink",
        "markets": "Markets & crafts",
        "culture": "Culture & faith",
        "evenings": "Evenings out",
        "transport": "Getting around",
        "essentials": "Health & essentials",
        "events": "What's on",
    },
    "sw": {
        "top": "Bora zaidi",
        "beaches": "Fukwe na bahari",
        "sights": "Historia",
        "nature": "Wanyama na mazingira",
        "food": "Chakula",
        "markets": "Masoko na sanaa",
        "culture": "Utamaduni na dini",
        "evenings": "Jioni",
        "transport": "Usafiri",
        "essentials": "Afya na huduma",
        "events": "Matukio",
    },
}
NOT_NEARBY = ("transport", "essentials")  # "near your home" means things to do, not the airport
WORD_KEYS = {  # "EXPLORE BEACHES" by SMS goes straight to the list
    "top": ("top", "best", "favourites", "bora"),
    "beaches": ("beach", "beaches", "sea", "snorkel", "snorkelling", "fukwe", "bahari"),
    "sights": ("sights", "history", "historic", "museum", "fort", "historia"),
    "nature": ("nature", "wildlife", "animals", "park", "wanyama"),
    "food": ("food", "eat", "restaurant", "restaurants", "chakula"),
    "markets": ("market", "markets", "shopping", "crafts", "soko", "masoko"),
    "culture": ("culture", "mosque", "temple", "church", "utamaduni"),
    "evenings": ("evening", "evenings", "night", "nightlife", "sunset", "jioni"),
    "transport": ("transport", "taxi", "travel", "getting around", "usafiri"),
    "essentials": ("hospital", "pharmacy", "doctor", "health", "atm", "afya"),
    "events": ("events", "event", "whats on", "what's on", "matukio"),
}


def short(key, lang="en"):
    return SHORT.get(lang, SHORT["en"]).get(key) or LABELS.get(key, key)


def key_for(text):
    """The menu entry a guest named after EXPLORE ('explore beaches' -> 'beaches'), or None."""
    low = (text or "").lower().strip(" .!?")
    return next((k for k, words in WORD_KEYS.items() if low in words), None)


def active_places():
    return Place.objects.filter(active=True).select_related("area")


def menu(lang="en"):
    """[(key, label)]: top picks, then each category that has something in it, then what's on."""
    present = set(active_places().values_list("category", flat=True))
    if not present:
        return []
    keys = ["top"] + [k for k, _ in Place.CATEGORIES if k in present]
    if upcoming(days=14):
        keys.append("events")
    return [(k, short(k, lang)) for k in keys]


# ---------- distance ----------


def distance_km(a_lat, a_lng, b_lat, b_lng):
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def origin_of(unit):
    """Where a guest is staying: the home's own pin, else its area's."""
    for obj in (unit, getattr(unit, "area", None)):
        if obj is not None and obj.latitude is not None and obj.longitude is not None:
            return float(obj.latitude), float(obj.longitude)
    return None


def with_distance(places, origin):
    for p in places:
        has_pin = origin and p.latitude is not None and p.longitude is not None
        p.distance_km = round(distance_km(*origin, p.latitude, p.longitude), 1) if has_pin else None
    return places


def nearest(places, origin):
    """Closest first; places without a pin keep their order at the end."""
    return sorted(with_distance(list(places), origin), key=lambda p: (p.distance_km is None, p.distance_km or 0))


def nearby(unit, limit=4):
    origin = origin_of(unit) if unit else None
    if not origin:
        return top_picks(limit=limit)
    pinned = [p for p in active_places().exclude(category__in=NOT_NEARBY) if p.latitude is not None]
    return nearest(pinned, origin)[:limit]


def top_picks(origin=None, limit=6):
    featured = list(active_places().filter(featured=True))
    picks = featured or list(active_places().exclude(category__in=NOT_NEARBY).order_by("-hits", "sort_order"))
    return (nearest(picks, origin) if origin else picks)[:limit]


def places_for(key, origin=None):
    """The places behind a menu entry, the closest to the guest's home first."""
    if key == "top":
        return top_picks(origin, limit=8)
    places = list(active_places().filter(category=key))
    return nearest(places, origin) if origin else places


def record_hit(place):
    Place.objects.filter(pk=place.pk).update(hits=F("hits") + 1)


# ---------- events ----------


def upcoming(days=7, start=None):
    """[(date, event)] for the next `days` days, soonest first."""
    start = start or today()
    end = start + timedelta(days=days)
    out = []
    for e in Event.objects.filter(active=True).select_related("place", "area"):
        on = e.next_on(start)
        if on is not None and on <= end:
            out.append((on, e))
    return sorted(out, key=lambda x: (x[0], x[1].pk))


# ---------- text for SMS, USSD and voice ----------

WORDS = {
    "en": {
        "hours": "Hours",
        "tip": "Tip",
        "map": "Map",
        "none": "Nothing on our guide yet - text Amina for her personal tips.",
        "events_head": "What's on",
        "no_events": "Nothing special on in the next two weeks - reply EXPLORE for places to visit.",
        "more": "Reply EXPLORE for places to visit.",
    },
    "sw": {
        "hours": "Saa",
        "tip": "Ushauri",
        "map": "Ramani",
        "none": "Bado hakuna kwenye mwongozo - mtumie Amina ujumbe kwa ushauri wake.",
        "events_head": "Matukio",
        "no_events": "Hakuna tukio maalum wiki mbili zijazo - jibu EXPLORE kwa maeneo ya kutembelea.",
        "more": "Jibu EXPLORE kwa maeneo ya kutembelea.",
    },
}


def word(key, lang):
    return WORDS.get(lang, WORDS["en"])[key]


def km(p):
    d = getattr(p, "distance_km", None)
    return f" ({d:g} km)" if d is not None else ""


def details_sms(p, lang="en"):
    """Everything a guest needs to go there, in one message (2-3 SMS segments)."""
    head = f"{p.name}{' (' + p.area.name + ')' if p.area_id else ''}: {p.summary_in(lang)}"
    parts = [head]
    if p.hours:
        parts.append(f"{word('hours', lang)}: {p.hours.rstrip('.')}.")
    if p.price:
        parts.append(f"{p.price.rstrip('.')}.")
    if p.tips:
        parts.append(f"{word('tip', lang)}: {p.tips}")
    parts.append(f"{word('map', lang)}: {p.map_url}")
    return " ".join(parts)


def list_sms(places, lang="en", limit=5):
    return " ".join(f"{i}) {p.name}{km(p)} - {p.summary_in(lang)}" for i, p in enumerate(places[:limit], 1))


def plain(text):
    """USSD screens are plain ASCII on many phones: 'Cafe' rather than a garbled 'Caf?'."""
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()


def events_ussd(lang="en", limit=3):
    items = upcoming(7)
    if not items:
        return plain(word("no_events", lang))
    return plain("\n".join(f"{nice_date(on, lang)} {e.title}" for on, e in items[:limit]))


def events_sms(lang="en", days=14, limit=5):
    items = upcoming(days)
    if not items:
        return word("no_events", lang)
    lines = [f"{nice_date(on, lang)}{' ' + e.time if e.time else ''} {e.title}" for on, e in items[:limit]]
    return f"{word('events_head', lang)}: " + "; ".join(lines) + ". " + word("more", lang)


# ---------- SMS conversations: reply with a number ----------

STATES = ("idle", "guide_menu", "guide_list")
FRESH = timedelta(hours=24)


def _free_for_guide(phone):
    """Don't cut into a booking or payment the guest is in the middle of on SMS."""
    from django.utils import timezone

    from apps.messaging.models import Conversation

    c = Conversation.objects.filter(phone=phone).first()
    return c is None or c.state in STATES or c.updated_at < timezone.now() - FRESH


def remember(phone, state, data, force=False):
    """Let a numbered SMS reply pick from what we just sent. force: the guest asked for it by SMS (EXPLORE, FOOD...),
    so it takes over the conversation; a list sent from a call or USSD only does when nothing else is going on."""
    from apps.messaging.models import Conversation

    if force or _free_for_guide(phone):
        Conversation.objects.update_or_create(phone=phone, defaults={"state": state, "data": data})


def menu_message(lang="en"):
    from apps.messaging import services as messaging

    entries = menu(lang)
    if not entries:
        return None, []
    options = ", ".join(f"{i} {label}" for i, (_, label) in enumerate(entries, 1))
    return messaging.render("guide_menu", lang, options=options), [k for k, _ in entries]


def list_message(key, places, lang="en"):
    from apps.messaging import services as messaging

    return messaging.render("guide_list", lang, title=short(key, lang), list=list_sms(places, lang))


def send_list(phone, key, places, lang="en"):
    """Text a numbered list (from a call or USSD); a reply with a number gets that place's details."""
    from apps.messaging import services as messaging

    places = list(places)[:5]
    body = list_message(key, places, lang)
    messaging.send(phone, body, kind="guide_list")
    remember(phone, "guide_list", {"places": [p.pk for p in places]})
    return body
