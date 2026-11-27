"""USSD (no data, any phone). Africa's Talking posts the whole input chain ('1*2*3') on every hop;
we replay it through a cursor, so the menu is stateless and survives any number of workers.

Conventions: 0 = back, 00 = main menu, 98 = more. Every screen stays within Safaricom's 160
characters, and we answer well inside AT's 10-second window (SMS go through the outbox, and M-Pesa
prompts are pushed after the screen has gone back - see comms.deferred).
"""

import logging
import re
from datetime import date, timedelta

from django.utils import timezone

from apps.accounts.services import get_or_create_user
from apps.bookings import services as bookings
from apps.bookings.models import Addon, BookingAddon
from apps.core.activity import record
from apps.core.api import STAFF_ROLES
from apps.core.models import SiteSettings
from apps.core.utils import first_name, kes, same_phone, today, weekend_start
from apps.guide.services import plain
from apps.messaging import services as messaging
from apps.properties.models import Amenity, Area, PriceOverride, Unit
from apps.properties.services import available_units, from_price
from apps.properties.services import quote as price_quote

from . import deferred, nlu

log = logging.getLogger("amina.ussd")
LIMIT = 160

S = {
    "en": {
        "welcome": "Karibu Amina Stays",
        "back": "Karibu tena {name}!",
        "main": [
            "Book a stay",
            "Prices & homes",
            "My booking",
            "Breakfast",
            "Report problem",
            "Talk to Amina",
            "Check out",
            "More",
            "EMERGENCY",
        ],
        "where": "Where?",
        "anywhere": "Anywhere",
        "when": "Check-in:",
        "when_opts": ["Tonight", "Tomorrow", "This weekend", "Next weekend", "Enter date"],
        "ddmm": "Enter check-in date as DDMM, e.g. 0512",
        "nights": "How many nights? (1-14)",
        "min_stay": "Homes free then need {n}+ nights. How many nights? ({n}-14)",
        "guests": "How many guests? (1-8)",
        "pick": "Pick a home ({dates}):",
        "more": "98. More",
        "none": "Nothing free then. We'll SMS you if something opens up.",
        "bf_q": "Add breakfast? ({price}/person/day)",
        "bf_opts": ["Swahili", "Continental", "Full English", "Vegetarian", "No thanks"],
        "pay_q": "Total {total}",
        "pay_full": "Pay all now",
        "pay_dep": "Pay {pct}% now ({dep})",
        "confirm": "Confirm & pay",
        "held": "Holding {unit} ({ref}). {pay}",
        "invalid": "Invalid choice.",
        "no_booking": "No active booking for this number. Dial again and choose 1 to book.",
        "mine": "{ref} {unit}\n{dates} {status}\nPaid {paid} of {total}",
        "status": {"held": "Awaiting payment", "confirmed": "Confirmed", "checked_in": "Checked in"},
        "mine_opts": ["Resend check-in info", "Pay balance", "Late checkout", "Cancel booking"],
        "sent": "Sent to you by SMS.",
        "cancel_q": "{text}",
        "cancel_opts": ["Yes, cancel", "No, keep it"],
        "kept": "Your booking is kept. See you soon!",
        "bf_menu": "Breakfast ({price}/person/day):",
        "bf_offer": "Breakfast {price}/person/day, {hours}: {styles}. Choose it when you book (1).",
        "bf_people": "For how many people? (1-{max})",
        "bf_saved": "Breakfast saved: {summary}. Kitchen told.",
        "bf_unavailable": "Breakfast isn't available at this home.",
        "issue_q": "What's wrong?",
        "issue_opts": [
            "No water",
            "Power/lights",
            "Wi-Fi",
            "AC/fan",
            "Cleanliness",
            "Lock/keys",
            "Noise/security",
            "Other",
        ],
        "issue_ok": "Logged #{task}. {who} has been told and will sort it. Reply HELP by SMS if urgent.",
        "talk_opts": ["Call me back", "Ask a question", "Make a complaint", "My requests"],
        "ask_q": "Ask anything, e.g. prices, free suites this weekend, breakfast, check-in time:",
        "ask_more": " More by SMS.",
        "ask_relayed": "Asante! Amina has your question and will reply by SMS shortly.",
        "found_free": "Free {dates}:",
        "found_free_with": "Free {dates} with {what}:",
        "found_homes": "Per night from:",
        "found_with": "With {what}, per night from:",
        "found_none": "Nothing free {dates}. Try other dates, or redial and choose 1: we'll SMS you if one opens.",
        "found_no_match": "None of our homes matches that. Redial and choose 2 for all homes and prices.",
        "found_tail": "Redial & choose 1 to book. Links by SMS.",
        "complaint_q": "What's it about?",
        "complaint_opts": [
            "Noise/neighbours",
            "Cleanliness",
            "Staff/service",
            "Billing/payment",
            "My booking",
            "Something else",
        ],
        "complaint_detail": "Tell us briefly what happened:",
        "complaint_ok": "Logged {ref}. {host} will reply by SMS within {sla}. Text {ref} any time for updates.",
        "mine_none": "No requests yet. Choose 3 to make a complaint, or 1 for a call back.",
        "more_title": "More",
        "more_opts": ["Explore the area", "Service status", "Rewards", "Language"],
        "explore": "Explore the coast",
        "guide_none": "Our local guide is being updated. Text EXPLORE for Amina's tips.",
        "guide_sent": "{name}: {summary} Hours, prices and a map sent by SMS.",
        "rewards_head": "{points} points. Your code {code}",
        "rewards_opts": ["KES {airtime} airtime", "{data}MB data", "Enter a friend's code", "How it works (SMS)"],
        "enter_code": "Enter your friend's code:",
        "callback": "Amina will call you back shortly.",
        "co_q": "Check out of {unit} now? Your door code will stop working.",
        "yes_no": ["Yes", "No"],
        "co_done": "Checked out. Asante, safe travels!",
        "lang_set": "Language saved.",
        "sos": "Amina is being alerted and called now. If you are in danger call 999 or 112.",
        "unit_info": "{name}, {area}: {beds} bed, sleeps {guests}. From {price}/night.{bf} Details sent by SMS.",
        "late_q": "Late checkout ({price}) is requested from Amina. You'll get an SMS.",
        "prompt": "Check your phone for the M-Pesa prompt of {amount}.",
        "card_link": "We'll text you a secure card payment link for {amount}.",
        "paid_up": "You're fully paid - asante!",
        "hold_gone": "Your hold has expired. Dial again to book.",
    },
    "sw": {
        "welcome": "Karibu Amina Stays",
        "back": "Karibu tena {name}!",
        "main": [
            "Weka nafasi",
            "Bei na nyumba",
            "Nafasi yangu",
            "Kifungua kinywa",
            "Ripoti tatizo",
            "Ongea na Amina",
            "Toka",
            "Zaidi",
            "DHARURA",
        ],
        "where": "Wapi?",
        "anywhere": "Popote",
        "when": "Kuingia:",
        "when_opts": ["Leo usiku", "Kesho", "Wikendi hii", "Wikendi ijayo", "Andika tarehe"],
        "ddmm": "Andika tarehe kama SSMM, mf. 0512",
        "nights": "Usiku ngapi? (1-14)",
        "min_stay": "Nyumba zilizo wazi zinahitaji usiku {n}+. Usiku ngapi? ({n}-14)",
        "guests": "Wageni wangapi? (1-8)",
        "pick": "Chagua nyumba ({dates}):",
        "more": "98. Zaidi",
        "none": "Hakuna nafasi. Tutakutumia SMS nafasi ikipatikana.",
        "bf_q": "Ongeza kifungua kinywa? ({price}/mtu/siku)",
        "bf_opts": ["Cha Kiswahili", "Continental", "Kiingereza", "Mboga", "Hapana"],
        "pay_q": "Jumla {total}",
        "pay_full": "Lipa yote sasa",
        "pay_dep": "Lipa {pct}% sasa ({dep})",
        "confirm": "Thibitisha & lipa",
        "held": "Tumekuwekea {unit} ({ref}). {pay}",
        "invalid": "Chaguo si sahihi.",
        "no_booking": "Hakuna nafasi kwa nambari hii. Piga tena uchague 1.",
        "mine": "{ref} {unit}\n{dates} {status}\nUmelipa {paid} kati ya {total}",
        "status": {"held": "Inasubiri malipo", "confirmed": "Imethibitishwa", "checked_in": "Umeingia"},
        "mine_opts": ["Tuma maelezo tena", "Lipa salio", "Kutoka baadaye", "Ghairi"],
        "sent": "Tumekutumia kwa SMS.",
        "cancel_q": "{text}",
        "cancel_opts": ["Ndiyo, ghairi", "Hapana, iweke"],
        "kept": "Nafasi yako iko. Karibu!",
        "bf_menu": "Kifungua kinywa ({price}/mtu/siku):",
        "bf_offer": "Kifungua kinywa {price}/mtu/siku, {hours}: {styles}. Kichague ukiweka nafasi (1).",
        "bf_people": "Kwa watu wangapi? (1-{max})",
        "bf_saved": "Kimehifadhiwa: {summary}.",
        "bf_unavailable": "Kifungua kinywa hakipatikani katika nyumba hii.",
        "issue_q": "Tatizo ni nini?",
        "issue_opts": [
            "Hakuna maji",
            "Stima",
            "Wi-Fi",
            "AC/feni",
            "Usafi",
            "Kufuli/funguo",
            "Kelele/usalama",
            "Nyingine",
        ],
        "issue_ok": "Tumeandika #{task}. {who} ameambiwa. Tuma MSAADA kwa SMS kama ni dharura.",
        "talk_opts": ["Nipigie", "Uliza swali", "Toa malalamiko", "Maombi yangu"],
        "ask_q": "Uliza chochote, mf. bei, nyumba wazi wikendi hii, kifungua kinywa, wifi:",
        "ask_more": " Zaidi kwa SMS.",
        "ask_relayed": "Asante! Amina amepata swali lako na atakujibu kwa SMS hivi karibuni.",
        "found_free": "Wazi {dates}:",
        "found_free_with": "Wazi {dates} zenye {what}:",
        "found_homes": "Kwa usiku kuanzia:",
        "found_with": "Zenye {what}, kwa usiku kuanzia:",
        "found_none": "Hakuna nafasi {dates}. Jaribu tarehe nyingine, au piga tena uchague 1: tutakutumia SMS.",
        "found_no_match": "Hakuna nyumba inayolingana. Piga tena uchague 2 kuona nyumba zote na bei.",
        "found_tail": "Piga tena uchague 1 kuweka nafasi. Viungo kwa SMS.",
        "complaint_q": "Ni kuhusu nini?",
        "complaint_opts": ["Kelele/majirani", "Usafi", "Wafanyakazi", "Malipo", "Nafasi yangu", "Kitu kingine"],
        "complaint_detail": "Tueleze kwa ufupi kilichotokea:",
        "complaint_ok": "Tumeandika {ref}. {host} atajibu kwa SMS ndani ya {sla}. Tuma {ref} kwa SMS kupata taarifa.",
        "mine_none": "Huna maombi bado. Chagua 3 kutoa malalamiko, au 1 tukupigie.",
        "more_title": "Zaidi",
        "more_opts": ["Gundua eneo", "Hali ya huduma", "Zawadi", "Lugha"],
        "explore": "Gundua pwani",
        "guide_none": "Mwongozo unasasishwa. Tuma EXPLORE kupata ushauri wa Amina.",
        "guide_sent": "{name}: {summary} Saa, bei na ramani kwa SMS.",
        "rewards_head": "Pointi {points}. Nambari yako {code}",
        "rewards_opts": ["Salio KES {airtime}", "Data MB {data}", "Weka nambari ya rafiki", "Inavyofanya kazi (SMS)"],
        "enter_code": "Andika nambari ya rafiki yako:",
        "callback": "Amina atakupigia hivi karibuni.",
        "co_q": "Toka {unit} sasa? Nambari ya mlango itazimwa.",
        "yes_no": ["Ndiyo", "Hapana"],
        "co_done": "Umetoka. Asante, safari njema!",
        "lang_set": "Lugha imehifadhiwa.",
        "sos": "Amina anaarifiwa na kupigiwa sasa. Ukiwa hatarini piga 999 au 112.",
        "unit_info": "{name}, {area}: vyumba {beds}, wageni {guests}. Kuanzia {price}/usiku.{bf} Maelezo kwa SMS.",
        "late_q": "Ombi la kutoka baadaye ({price}) limetumwa kwa Amina. Utapata SMS.",
        "prompt": "Angalia simu yako upate ombi la M-Pesa la {amount}.",
        "card_link": "Tutakutumia kiungo salama cha kulipa {amount} kwa kadi kwa SMS.",
        "paid_up": "Umelipa yote - asante!",
        "hold_gone": "Muda wa kukushikilia umeisha. Piga tena uweke nafasi.",
    },
}
ISSUE_CATEGORIES = ["water", "power", "wifi", "ac", "cleanliness", "lock", "security", "other"]
COMPLAINT_CATEGORIES = ["complaint", "complaint", "complaint", "billing", "booking", "other"]
BF_STYLES = ["swahili", "continental", "english", "vegetarian"]

# ---------- typed questions (6 Talk to Amina > 2 Ask a question) ----------
HOME_NOUNS = {
    "home",
    "homes",
    "house",
    "houses",
    "suite",
    "suites",
    "apartment",
    "apartments",
    "studio",
    "studios",
    "loft",
    "lofts",
    "cottage",
    "cottages",
    "room",
    "rooms",
    "nyumba",
    "chumba",
    "vyumba",
    "malazi",
}
FREE_WORDS = re.compile(r"\b(free|available|availability|vacan\w*|tonight|nafasi|wazi)\b", re.IGNORECASE)
PRICE_WORDS = re.compile(r"\b(prices?|costs?|rates?|how much|bei|ngapi)\b", re.IGNORECASE)
# words that add nothing to "which homes?": "homes in Diani", "what do you have in Nyali?"
FILLER = {"in", "at", "the", "a", "an", "any", "show", "me", "your", "you", "what", "which", "do", "have", "near"}
FILLER |= {"around", "of", "for", "is", "are", "there", "and", "katika", "huko", "za", "ya", "zenu", "kwenye"}
# words in home and amenity names too general to pick one out ("is the apartment safe?", "free parking")
GENERIC_WORDS = HOME_NOUNS | {"family", "villa", "free", "secure", "full", "fast", "shared", "private", "standby"}
GENERIC_WORDS |= {"dedicated", "available", "storage", "exterior", "hour", "access", "view", "self", "first"}
GENERIC_WORDS |= {"high", "smart", "board", "games", "step", "entrance", "alarm", "safe", "backup", "ceiling"}
GENERIC_WORDS |= {"machine", "breakfast", "water", "power", "inverter", "only", "gate"}


def _words(text):
    return re.findall(r"[a-z]+", (text or "").lower())


def named_homes(words):
    """Homes a question names by their own words ("Blue Reef", "Palm"), not by area or by type."""
    area_words = {w for name in Area.objects.values_list("name", flat=True) for w in _words(name)}
    homes = Unit.objects.filter(status="active").select_related("area").order_by("sort_order")
    return [u for u in homes if ({w for w in _words(u.name) if len(w) > 3} - area_words - GENERIC_WORDS) & words]


def asked_amenities(words):
    """Amenities a question names ("pool", "kitchen", "ocean view", "kayaks") and the words it named them with."""
    found, said = [], set()
    for a in Amenity.objects.all():
        for w in _words(a.name):
            if len(w) < 4 or w in GENERIC_WORDS:
                continue
            hit = next((q for q in words if q == w or (min(len(q), len(w)) >= 5 and q[:5] == w[:5])), None)
            if hit:
                found.append(a)
                said.add(hit)
                break
    return found, sorted(said)


class Reply(Exception):
    def __init__(self, text, end=False):
        super().__init__(text)
        self.text, self.end = text, end


def fit(text, limit=LIMIT - 4):
    """Shorten to the limit with an ASCII "..." (telcos can't render special characters like a Unicode ellipsis)."""
    return text if len(text) <= limit else text[: max(limit - 3, 0)].rstrip() + "..."


class Cursor:
    def __init__(self, raw):
        tokens = []
        for t in (raw or "").split("*") if raw else []:
            t = t.strip()
            if t == "00":
                tokens = []
            elif t == "0":
                if tokens:
                    tokens.pop()
            else:
                tokens.append(t)
        self.tokens, self.i = tokens, 0

    def take(self):
        if self.i >= len(self.tokens):
            return None
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def has_more(self):
        return self.i < len(self.tokens)


class Ussd:
    def __init__(self, phone, raw):
        self.phone, self.c = phone, Cursor(raw)
        self.user, _ = get_or_create_user(phone, channel="ussd")
        self.lang = self.user.lang if self.user.lang in S else "en"
        self.t = S[self.lang]

    # ---------- primitives ----------
    def choose(self, title, options, per_page=None):
        """Numbered list with paging. Returns the 0-based index chosen."""
        pages = self._pages(title, options, per_page or len(options))
        page = 0
        while True:
            more = page + 1 < len(pages)
            items = "".join(pages[page]) + (f"\n{self.t['more']}" if more else "")
            tok = self.c.take()
            if tok is None:
                raise Reply(self._screen(title, items))
            if tok == "98" and more:
                page += 1
                continue
            if tok.isdigit() and 1 <= int(tok) <= len(options):
                return int(tok) - 1
            if not self.c.has_more():
                raise Reply(self._screen(title, items, invalid=True))

    def _pages(self, title, options, per_page):
        """Split the numbered options into pages that each fit one screen next to (the start of) the title."""
        lines = [f"\n{i}. {o}" for i, o in enumerate(options, 1)]
        keep = min(len(title), 30)
        if len(lines) <= per_page and keep + sum(map(len, lines)) <= LIMIT - 4:
            return [lines]
        room = LIMIT - 4 - keep - len(f"\n{self.t['more']}")
        pages = [[]]
        for line in lines:
            if pages[-1] and (len(pages[-1]) >= per_page or sum(map(len, pages[-1])) + len(line) > room):
                pages.append([])
            pages[-1].append(line)
        return pages

    def _screen(self, title, items, invalid=False):
        """Title + options within the limit: only the title is ever shortened, never an option."""
        room = LIMIT - 4 - len(items)
        if invalid:
            both = f"{self.t['invalid']}\n{title}"
            title = both if len(both) <= room else self.t["invalid"]
        return fit(title, room) + items

    def number(self, prompt, lo, hi):
        while True:
            tok = self.c.take()
            if tok is None:
                raise Reply(prompt)
            if tok.isdigit() and lo <= int(tok) <= hi:
                return int(tok)
            if not self.c.has_more():
                raise Reply(f"{self.t['invalid']} {prompt}")

    def text(self, prompt):
        tok = self.c.take()
        if tok is None:
            raise Reply(prompt)
        return tok

    def end(self, text):
        raise Reply(fit(text), end=True)

    # ---------- entry ----------
    def run(self):
        s = SiteSettings.load()
        if same_phone(self.phone, s.host_contact) or self.user.role in ("owner", "manager"):
            return self.ops()
        if self.user.role in STAFF_ROLES:
            return self.staff()
        return self.guest()

    def guest(self):
        last = self.user.bookings.filter(status__in=("confirmed", "checked_in", "completed")).exists()
        name = first_name(self.user.name)[:10]
        title = self.t["back"].format(name=name) if last and name else self.t["welcome"]
        choice = self.choose(title, self.t["main"])
        return [
            self.book,
            self.prices,
            self.my_booking,
            self.breakfast,
            self.problem,
            self.talk,
            self.checkout,
            self.more,
            self.sos,
        ][choice]()

    # ---------- guest flows ----------
    def book(self):
        areas = list(Area.objects.filter(units__status="active").distinct()[:5])
        a = self.choose(self.t["where"], [x.name for x in areas] + [self.t["anywhere"]])
        area = areas[a] if a < len(areas) else None
        w = self.choose(self.t["when"], self.t["when_opts"])
        t = today()
        if w == 4:
            ci = self.check_in_date()
        else:
            ci = [t, t + timedelta(days=1), weekend_start(t), weekend_start(t) + timedelta(days=7)][w]
        nights = self.number(self.t["nights"], 1, 14)
        guests = self.number(self.t["guests"], 1, 8)
        while True:
            co = ci + timedelta(days=nights)
            free = list(available_units(ci, co, area=area.slug if area else None, guests=guests))
            units = [u for u in free if u.min_nights <= nights <= u.max_nights][:9]  # only homes the hold accepts
            longer = [u.min_nights for u in free if u.min_nights > nights]
            if units or not longer or min(longer) > 14:
                break
            nights = self.number(self.t["min_stay"].format(n=min(longer)), min(longer), 14)
        if not units:
            bookings.add_to_waitlist(self.user, ci, co, area=area, guests=guests, channel="ussd")
            self.end(self.t["none"])
        dates = f"{ci:%d/%m}-{co:%d/%m}"
        quotes = {u.pk: price_quote(u, ci, co, guests=guests) for u in units}
        idx = self.choose(
            self.t["pick"].format(dates=dates),
            [f"{u.name[:18]} {kes(quotes[u.pk]['total'])}" for u in units],
            per_page=3,
        )
        unit = units[idx]
        addons = []
        bf = Addon.objects.filter(code="breakfast", active=True).first()
        if bf and unit.breakfast_available:
            b_idx = self.choose(self.t["bf_q"].format(price=kes(bf.price)), self.t["bf_opts"])
            if b_idx < 4:
                addons.append({"code": "breakfast", "quantity": guests, "details": {"style": BF_STYLES[b_idx]}})
        q = price_quote(
            unit,
            ci,
            co,
            guests=guests,
            addons=[{"addon": bf, "quantity": guests}] if addons else None,
            payment_plan="deposit",
        )
        s = SiteSettings.load()
        if q["deposit_available"]:
            plan = ["full", "deposit"][
                self.choose(
                    self.t["pay_q"].format(total=kes(q["total"])),
                    [self.t["pay_full"], self.t["pay_dep"].format(pct=s.deposit_percent, dep=kes(q["deposit"]))],
                )
            ]
        else:
            self.choose(self.t["pay_q"].format(total=kes(q["total"])), [self.t["confirm"]])
            plan = "full"
        try:
            b = bookings.create_hold(
                unit=unit,
                guest=self.user,
                check_in=ci,
                check_out=co,
                channel="ussd",
                adults=guests,
                addons=addons,
                payment_plan=plan,
            )
        except bookings.BookingError as e:
            self.end(str(e))
        self.end(self.t["held"].format(unit=unit.name, ref=b.ref, pay=self.pay_line(b)))

    def pay_line(self, b):
        """What to say about paying now. The M-Pesa prompt itself is pushed once this screen has gone back
        (comms.deferred): a slow Daraja call must never eat the session's few seconds."""
        due = max(0, b.amount_due_now - b.amount_paid) if b.status == "held" else b.balance_due
        if due <= 0:
            return self.t["paid_up"]
        if b.status == "held" and not b.hold_active:
            return self.t["hold_gone"]
        deferred.after_response(deferred.push_payment, b.pk)
        from apps.payments.services import can_prompt

        return self.t["prompt" if can_prompt(b.guest.phone) else "card_link"].format(amount=kes(due))

    def check_in_date(self):
        """Check-in typed as DDMM ('0512'); a day already past means next year. A typo is asked again."""
        t = today()
        while True:
            tok = self.c.take()
            if tok is None:
                raise Reply(self.t["ddmm"])
            m = re.fullmatch(r"(\d{1,2})[/.-]?(\d{2})", tok)
            if m:
                try:
                    d = date(t.year, int(m[2]), int(m[1]))
                    return d if d >= t else d.replace(year=t.year + 1)
                except ValueError:
                    pass
            if not self.c.has_more():
                raise Reply(f"{self.t['invalid']} {self.t['ddmm']}")

    def unit_info(self, u):
        """One home: a screen with its size, price and breakfast, and an SMS with its summary and page."""
        from django.conf import settings

        bf = Addon.objects.filter(code="breakfast", active=True).first()
        screen = self.t["unit_info"].format(
            name=u.name,
            area=u.area.name,
            beds=u.bedrooms,
            guests=u.max_guests,
            price=kes(from_price(u)),
            bf=f" Breakfast {kes(bf.price)}." if bf and u.breakfast_available else "",
        )
        return screen, f"{u.name} ({u.area.name}): {u.summary} Photos & booking: {settings.FRONTEND_URL}/stays/{u.slug}"

    def prices(self):
        units = list(Unit.objects.filter(status="active").select_related("area"))
        idx = self.choose(
            self.t["pick"].format(dates="/night"), [f"{u.name[:18]} {kes(from_price(u))}" for u in units], per_page=4
        )
        screen, sms = self.unit_info(units[idx])
        messaging.send(self.phone, sms, kind="ussd_info")
        self.end(screen)

    def my_booking(self):
        b = bookings.current_booking(self.phone)
        if not b:
            self.end(self.t["no_booking"])
        head = self.t["mine"].format(
            ref=b.ref,
            unit=b.unit.name[:18],
            dates=f"{b.check_in:%d/%m}-{b.check_out:%d/%m}",
            status=self.t["status"].get(b.status, b.get_status_display()),
            paid=kes(b.amount_paid),
            total=kes(b.total),
        )
        choice = self.choose(head, self.t["mine_opts"])
        if choice == 0:
            if b.status == "checked_in":
                bookings.send_guest(b, "checkin_code")
            elif b.status == "confirmed":
                # directions and Wi-Fi open 48 h before check-in, as on the trip page; until then the confirmation
                bookings.send_guest(
                    b, "directions" if bookings.details_visible(b) else "booking_confirmed", balance_note=""
                )
            else:
                bookings.send_guest(b, "status")
            self.end(self.t["sent"])
        if choice == 1:
            self.end(self.pay_line(b))
        if choice == 2:
            from .smsbot import addon_defaults

            late = Addon.objects.filter(code="late_checkout", active=True).first()
            try:
                bookings.add_addon(b, "late_checkout", channel="ussd", details=addon_defaults("late_checkout"))
            except bookings.BookingError as e:
                self.end(str(e))
            self.end(self.t["late_q"].format(price=kes(late.price) if late else ""))
        q = bookings.refund_quote(b)
        if self.choose(fit(self.t["cancel_q"].format(text=q["text"]), 120), self.t["cancel_opts"]) == 0:
            try:
                bookings.cancel(b, by="guest", reason="Cancelled by USSD")
            except bookings.BookingError as e:
                self.end(str(e))
            self.end(q["text"])
        self.end(self.t["kept"])

    def breakfast(self):
        b = bookings.current_booking(self.phone)
        bf = Addon.objects.filter(code="breakfast", active=True).first()
        if not b:
            if bf:  # not booked yet: what's served, chosen while booking
                hours = (bf.options or {}).get("hours", "7:30-10:00")
                styles = ", ".join(self.t["bf_opts"][:4])
                self.end(self.t["bf_offer"].format(price=kes(bf.price), hours=hours, styles=styles))
            self.end(self.t["no_booking"])
        if not bf or not b.unit.breakfast_available:
            self.end(self.t["bf_unavailable"])
        idx = self.choose(self.t["bf_menu"].format(price=kes(bf.price)), self.t["bf_opts"])
        if idx == 4:
            bookings.set_breakfast(b, None, channel="ussd")
            self.end(self.t["bf_saved"].format(summary="-"))
        people = self.number(self.t["bf_people"].format(max=b.guests_count), 1, max(1, b.guests_count))
        try:
            ba = bookings.set_breakfast(b, BF_STYLES[idx], people=people, channel="ussd")
        except bookings.BookingError as e:
            self.end(str(e))
        self.end(self.t["bf_saved"].format(summary=bookings.breakfast_summary(ba)))

    def problem(self):
        from apps.operations.services import report_issue

        b = bookings.current_booking(self.phone)
        if not b:
            self.end(self.t["no_booking"])
        idx = self.choose(self.t["issue_q"], self.t["issue_opts"])
        from apps.notices.services import known_issue_text

        known = known_issue_text(b, ISSUE_CATEGORIES[idx], self.lang)
        if known:  # an outage we've already announced: no second work order
            self.end(known)
        task = report_issue(
            b, f"{self.t['issue_opts'][idx]} (reported by USSD)", category=ISSUE_CATEGORIES[idx], channel="ussd"
        )
        bookings.notify_host(
            f"Issue #{task.pk} at {b.unit.name} via USSD: {self.t['issue_opts'][idx]} ({self.user.display_name})",
            booking=b,
        )
        who = first_name(task.assignee.name) if task.assignee and task.assignee.name else "Our caretaker"
        self.end(self.t["issue_ok"].format(task=task.pk, who=who))

    def talk(self):
        from apps.messaging.models import Thread
        from apps.support import services as support

        choice = self.choose(self.t["main"][5], self.t["talk_opts"])
        if choice == 0:
            b = bookings.current_booking(self.phone)
            thread = messaging.get_thread(self.phone, self.user)
            messaging.record_inbound(
                self.phone, "[USSD] Please call me back", channel="ussd", booking=b, handled="relayed"
            )
            Thread.objects.filter(pk=thread.pk).update(needs_reply=True, waiting_since=timezone.now())
            ticket = support.open_ticket(  # on the support desk too, with a reply-by time and a Call button
                self.phone,
                category="callback",
                subject="Please call me back",
                channel="ussd",
                booking=b,
                tell_host=False,
            )
            bookings.notify_host(
                f"CALL BACK {ticket.ref}: {self.user.display_name} {self.phone}"
                f"{' (' + b.ref + ' ' + b.unit.name + ')' if b else ''} asked by USSD. Reply CALL {ticket.ref} to be connected.",
                booking=b,
            )
            self.end(self.t["callback"])
        if choice == 1:
            self.ask()
        if choice == 2:
            self.complaint()
        self.my_requests()

    def ask(self):
        """A typed question, answered on the spot from the same data as the website and the SMS line: the homes it
        names or asks about (free on the dates asked, with prices), else the knowledge base (with this guest's own
        Wi-Fi and directions). Anything else goes to Amina's phone, and her '#<thread> reply' comes back by SMS."""
        from .smsbot import relay_to_host

        question = nlu.clean(self.text(self.t["ask_q"]))[:300]
        b = bookings.current_booking(self.phone)
        asked = messaging.record_inbound(self.phone, f"[USSD] {question}", channel="ussd", booking=b)
        answer, kind, sms = self._answer(question, b)
        if answer is None:
            relay_to_host(self.phone, self.user, question, b)
            messaging.mark(asked, "relayed", "question")
            self.end(self.t["ask_relayed"])
        messaging.mark(asked, "auto", kind)
        screen = plain(answer)
        if len(screen) > LIMIT - 4:
            sms = sms or answer
            screen = fit(screen, LIMIT - 4 - len(self.t["ask_more"])) + self.t["ask_more"]
        messaging.send(self.phone, screen, kind=kind, sender="bot", booking=b, channel="ussd")  # Amina sees it
        if sms:
            messaging.send(self.phone, sms, kind=kind, sender="bot", booking=b)
        self.end(screen)

    def _answer(self, question, b):
        """(screen text, kind, SMS or None) for a typed question, or no text when only Amina can answer it. A question
        about homes ("free suites this weekend", "Diani", "Blue Reef price", "rooms with a pool") is answered from the
        homes and their calendars; anything else from the knowledge base, then by the homes it names or asks about."""
        words = _words(question)
        area = nlu.parse_area(question, Area.objects.filter(units__status="active").distinct())
        named = named_homes(set(words))
        amenities, said = asked_amenities(words)
        ci, co = nlu.parse_dates(question)
        guests = nlu.parse_guests(question)
        about_homes = bool(HOME_NOUNS.intersection(words))
        dated = bool(FREE_WORDS.search(question) or ci or guests)
        priced = bool(PRICE_WORDS.search(question))
        place = area is not None or bool(named)
        place_words = {w for x in [*([area] if area else []), *named] for w in _words(x.name)}
        only_place = place and all(w in place_words or w in HOME_NOUNS or w in FILLER for w in words)

        def homes():
            return self._homes(area, named, amenities, said, ci, co, guests, question)

        if (place and (dated or priced or only_place)) or (about_homes and (dated or priced or amenities)):
            return homes()
        if SiteSettings.load().auto_answer:
            ctx = messaging.faq_context(self.phone, b)
            hit = messaging.match_faq(question, self.lang, unit=b.unit if b else None, ctx=ctx)
            if hit:
                return hit[1], f"faq:{hit[0].category}", None
        if place or about_homes or amenities or dated or nlu.looks_like_booking(question):
            return homes()
        return None, "", None

    def _homes(self, area, named, amenities, said, ci, co, guests, question):
        """The homes asked about (named, else in the area; with the amenity; sleeping that many). With dates (tonight
        for 'free'), those a booking would accept then, with the stay's price - without a length, the shortest stay
        that has one. Without dates, each one's price per night, or one home's details. The SMS has their pages."""
        from django.conf import settings

        units = named or list(Unit.objects.filter(status="active", **({"area": area} if area else {})))
        if amenities:
            having = set(Unit.objects.filter(amenities__in=amenities).values_list("pk", flat=True))
            units = [u for u in units if u.pk in having]
        units = [u for u in units if u.max_guests >= (guests or 1)]
        what = "/".join(said)
        if ci is None and FREE_WORDS.search(question):
            ci = today()
        if ci:
            # parse_dates makes it one night unless told: then try the shortest stay that a free home takes
            given = co and co > ci and (nlu.parse_nights(question) or (co - ci).days > 1)
            lengths = [(co - ci).days] if given else [1, 2, 3]
            dates = f"{ci:%d/%m}-{ci + timedelta(days=lengths[0]):%d/%m}"
            for nights in lengths:
                end = ci + timedelta(days=nights)
                free = set(available_units(ci, end, guests=guests).values_list("pk", flat=True))
                found = [u for u in units if u.pk in free and u.min_nights <= nights <= u.max_nights]
                if found:
                    break
            if not found:
                return self.t["found_none"].format(dates=dates), "ussd_search", None
            dates = f"{ci:%d/%m}-{end:%d/%m}"
            priced = [(u, price_quote(u, ci, end, guests=guests or 1)["total"]) for u in found]
            head = self.t["found_free_with" if what else "found_free"].format(dates=dates, what=what)
        else:
            if not units:
                return self.t["found_no_match"], "ussd_search", None
            if len(units) == 1:
                screen, sms = self.unit_info(units[0])
                return screen, "ussd_search", sms
            priced = [(u, from_price(u)) for u in units]
            head = self.t["found_with" if what else "found_homes"].format(what=what)
        tail = "\n" + self.t["found_tail"]
        screen = head
        for u, price in priced:
            line = plain(f"\n{u.name[:20]} {kes(price)}")
            if len(screen) + len(line) + len(tail) > LIMIT - 4:
                break
            screen += line
        sms = "; ".join(
            f"{u.name} ({u.area.name}) {kes(p)}: {settings.FRONTEND_URL}/stays/{u.slug}" for u, p in priced[:4]
        )
        return screen + tail, "ussd_search", sms

    def complaint(self):
        from apps.support import services as support

        idx = self.choose(self.t["complaint_q"], self.t["complaint_opts"])
        detail = self.text(self.t["complaint_detail"]).strip()
        label = S["en"]["complaint_opts"][idx]  # Amina reads them in English
        t = support.open_ticket(
            self.phone,
            category=COMPLAINT_CATEGORIES[idx],
            subject=f"{label}: {detail}"[:140],
            description=f"{label}: {detail} (by USSD)",
            channel="ussd",
            booking=bookings.current_booking(self.phone),
        )
        self.end(
            self.t["complaint_ok"].format(
                ref=t.ref, host=SiteSettings.load().host_name, sla=support.sla_text(t.priority, self.lang)
            )
        )

    def my_requests(self):
        from apps.support import services as support

        tickets = list(support.guest_tickets(self.phone).exclude(status="closed")[:4])
        if not tickets:
            self.end(self.t["mine_none"])
        self.end(
            "\n".join(
                f"{t.ref} {support.category_in(t, self.lang)}: {support.status_in(t, self.lang)}" for t in tickets
            )
        )

    # ---------- 8. More: local guide, service status, rewards, language ----------
    def more(self):
        choice = self.choose(self.t["more_title"], self.t["more_opts"])
        [self.explore, self.service_status, self.rewards, self.language][choice]()

    def explore(self):
        from apps.guide import services as guide

        entries = guide.menu(self.lang)
        if not entries:
            self.end(self.t["guide_none"])
        key = entries[self.choose(self.t["explore"], [label for _, label in entries], per_page=6)][0]
        if key == "events":
            messaging.send(self.phone, guide.events_sms(self.lang), kind="guide_events")
            self.end(f"{guide.events_ussd(self.lang)}\n{self.t['sent']}")
        b = bookings.current_booking(self.phone)
        places = guide.places_for(key, guide.origin_of(b.unit) if b else None)
        if not places:
            self.end(self.t["guide_none"])
        names = [guide.plain(x.name)[:24] for x in places]
        p = places[self.choose(guide.short(key, self.lang), names, per_page=5)]
        guide.record_hit(p)
        messaging.send(self.phone, guide.details_sms(p, self.lang), kind="guide_place")
        self.end(guide.plain(self.t["guide_sent"].format(name=p.name, summary=p.summary_in(self.lang))))

    def service_status(self):
        from apps.notices.services import status_text

        self.end(status_text(self.phone, self.lang))

    def rewards(self):
        from apps.rewards import services as rewards

        prog = rewards.program()
        if not prog.enabled:
            self.end(messaging.render("rewards_off", self.lang))
        m = rewards.member(self.user)
        head = self.t["rewards_head"].format(points=rewards.balance(self.user), code=m.code)
        opts = [o.format(airtime=prog.redeem_airtime, data=prog.redeem_data_mb) for o in self.t["rewards_opts"]]
        choice = self.choose(head, opts)
        if choice in (0, 1):
            _, text = rewards.redeem(self.user, "airtime" if choice == 0 else "data", defer=True)
            self.end(text)
        if choice == 2:
            _, text = rewards.apply_referral(self.user, self.text(self.t["enter_code"]))
            self.end(text)
        messaging.send(self.phone, rewards.summary_text(self.user), kind="rewards_summary")
        self.end(self.t["sent"])

    def checkout(self):
        b = bookings.active_stay(self.phone)
        if not b:
            self.end(self.t["no_booking"])
        if self.choose(self.t["co_q"].format(unit=b.unit.name), self.t["yes_no"]) == 0:
            bookings.check_out(b, channel="ussd")
            self.end(self.t["co_done"])
        self.end(self.t["kept"])

    def language(self):
        codes = ["en", "sw", "it", "de", "fr"]
        idx = self.choose("Language / Lugha", ["English", "Kiswahili", "Italiano", "Deutsch", "Francais"])
        self.user.lang = codes[idx]
        self.user.save(update_fields=["lang"])
        self.end(S.get(codes[idx], S["en"])["lang_set"])

    def sos(self):
        from apps.safety.services import escalate

        escalate(self.phone, "ussd")
        self.end(self.t["sos"])

    # ---------- Amina's ops menu ----------
    def ops(self):
        from apps.operations import services as ops

        t = today()
        choice = self.choose(
            "Amina ops",
            ["Today", "Free tonight", "Arrivals/departures", "Requests", "Message guests", "Last-minute deal", "Tasks"],
        )
        if choice == 0:
            n = ops.digest_numbers()
            self.end(
                f"Today: {n['arrivals']} in, {n['departures']} out, {n['in_house']} staying, {n['breakfasts']} breakfasts, "
                f"{n['tasks']} tasks, {n['unread']} chats, {n['alerts']} alerts. Week {n['occ']}%."
            )
        if choice == 1:
            free = list(available_units(t, t + timedelta(days=1)))
            self.end("Free tonight: " + ("; ".join(f"{u.name} {kes(u.base_price)}" for u in free) or "none"))
        if choice == 2:
            from apps.bookings.models import Booking

            ins = Booking.objects.filter(check_in=t, status__in=("confirmed", "checked_in")).select_related("unit")
            outs = Booking.objects.filter(check_out=t, status__in=("checked_in", "completed")).select_related("unit")
            self.end(
                f"IN: {', '.join(b.unit.name for b in ins) or '-'}. OUT: {', '.join(b.unit.name for b in outs) or '-'}"
            )
        if choice == 3:
            reqs = list(BookingAddon.objects.filter(status="requested").select_related("addon", "booking")[:6])
            if not reqs:
                self.end("No pending requests.")
            r = reqs[self.choose("Requests", [f"{x.addon.name[:14]} {x.booking.ref}" for x in reqs])]
            ok = self.choose(f"{r.addon.name} for {r.booking.ref}", ["Approve", "Decline"]) == 0
            bookings.decide_addon(r, ok, actor=self.user)
            self.end(f"{'Approved' if ok else 'Declined'}. Guest told by SMS.")
        if choice == 4:
            aud = ["in_house", "arriving", "waitlist"][
                self.choose("Message who?", ["Guests staying now", "Arriving in 7 days", "Waitlist"])
            ]
            body = self.text("Type your message:")
            phones = messaging.audience_phones(aud)
            for p in phones:
                messaging.send(
                    p,
                    f"{SiteSettings.load().business_name}: {body[:300]}",
                    kind="broadcast",
                    sender="host",
                    user=self.user,
                )
            record("broadcast", f"USSD broadcast to {len(phones)} ({aud})", actor=self.user)
            self.end(f"Sent to {len(phones)} guest(s).")
        if choice == 5:
            free = list(available_units(t, t + timedelta(days=1)))
            if not free:
                self.end("Everything is booked tonight!")
            u = free[self.choose("Discount which?", [f"{x.name[:20]} {kes(x.base_price)}" for x in free])]
            pct = self.number("Discount %? (10-50)", 10, 50)
            price = round(u.base_price * (100 - pct) / 100)
            PriceOverride.objects.update_or_create(
                unit=u, date=t, defaults={"price": price, "note": f"Last-minute -{pct}%"}
            )
            offered = bookings.notify_waitlist(u)
            record("pricing", f"Last-minute deal: {u.name} tonight {kes(price)} (-{pct}%)", actor=self.user)
            self.end(f"{u.name} tonight now {kes(price)}. {offered} waitlisted guest(s) told.")
        tasks = list(ops.Task.objects.filter(status__in=("open", "in_progress")).select_related("unit")[:5])
        self.end("Open tasks: " + ("; ".join(f"#{x.pk} {x.title[:30]}" for x in tasks) or "none"))

    # ---------- staff ----------
    def staff(self):
        from apps.operations import services as ops

        choice = self.choose("Amina Stays staff", ["My tasks", "Breakfast tomorrow", "Today's arrivals"])
        if choice == 0:
            tasks = list(ops.open_tasks_for(self.user))
            if not tasks:
                self.end("No open tasks. Asante!")
            task = tasks[self.choose("My tasks", [f"#{x.pk} {x.title[:24]}" for x in tasks], per_page=4)]
            if self.choose(f"#{task.pk} {task.title[:60]}", ["Start", "Done"]) == 0:
                ops.start_task(task, self.user)
                self.end(f"Task #{task.pk} started.")
            ops.complete_task(task, self.user, note="via USSD")
            self.end(f"Task #{task.pk} done. Asante!")
        if choice == 1:
            self.end(ops.kitchen_sheet_text(today() + timedelta(days=1)) or "No breakfasts tomorrow.")
        arrivals = ops.gate_list()
        self.end("Arrivals: " + ("; ".join(f"{b.unit.name}: {b.guest.display_name}" for b in arrivals) or "none"))


def handle(phone, raw_text):
    try:
        Ussd(phone, raw_text).run()
        return "END Thank you."
    except Reply as r:
        return f"{'END' if r.end else 'CON'} {r.text}"
