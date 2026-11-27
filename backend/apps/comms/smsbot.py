"""Ask Amina — the two-way SMS line (Africa's Talking two-way SMS / shortcode).

Every inbound SMS is first routed by *who* sent it (Amina, staff, guest) and then, for guests,
classified: safety word → opt-out/language → an answer the current conversation expects →
keyword commands → booking attempt → knowledge-base answer → relay to Amina. Anything that doesn't
fit drops to the relay path, so a guest is never stuck inside a menu.
"""

import logging
import re

from django.utils import timezone

from apps.accounts.services import AuthError, get_or_create_user, set_identity
from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.core.api import HOST_ROLES, STAFF_ROLES
from apps.core.models import SiteSettings
from apps.core.utils import first_name, kes, nice_date, same_phone, today
from apps.messaging import services as messaging
from apps.messaging.models import Conversation, Thread
from apps.properties.models import Area, Unit
from apps.properties.services import available_units
from apps.properties.services import quote as price_quote

from . import nlu

log = logging.getLogger("amina.sms")

SOS = re.compile(r"^\s*(help|sos|msaada|dharura|emergency|aiuto|hilfe|au secours|urgence)\b", re.IGNORECASE)
LANG_WORDS = {
    "english": "en",
    "en": "en",
    "kiswahili": "sw",
    "swahili": "sw",
    "sw": "sw",
    "italiano": "it",
    "italian": "it",
    "it": "it",
    "deutsch": "de",
    "german": "de",
    "de": "de",
    "francais": "fr",
    "français": "fr",
    "french": "fr",
    "fr": "fr",
}
YES = {"yes", "y", "ndiyo", "ndio", "sawa", "si", "ja", "oui", "ok", "confirm"}
NO = {"no", "n", "hapana", "la", "nein", "non"}
ARRIVAL_MODES = {"1": "flight", "2": "sgr", "3": "car", "4": "bus", "5": "local"}
BREAKFAST_CHOICES = {"1": "swahili", "2": "continental", "3": "english", "4": "vegetarian", "0": "none"}


def handle_sms(phone, text, inbound=None):
    text = nlu.clean(text)
    s = SiteSettings.load()
    from apps.accounts.models import User

    if (
        same_phone(phone, s.host_contact)
        or User.objects.filter(phone=phone, role__in=HOST_ROLES, is_active=True).exists()
    ):
        return HostCommands(phone, text, inbound).run()  # Amina, or a co-host (manager) acting for her
    staff = User.objects.filter(
        phone=phone, role__in=[r for r in STAFF_ROLES if r not in HOST_ROLES], is_active=True
    ).first()
    if staff:
        return StaffCommands(staff, text, inbound).run()
    guest, created = get_or_create_user(phone, channel="sms")
    if created and nlu.looks_swahili(text):
        guest.lang = "sw"
        guest.save(update_fields=["lang"])
    return GuestBot(guest, text, inbound).run()


# ---------- helpers ----------


def get_convo(phone):
    c, _ = Conversation.objects.get_or_create(phone=phone)
    if c.state != "idle" and c.updated_at < timezone.now() - timezone.timedelta(hours=24):
        c.state, c.data = "idle", {}
        c.save(update_fields=["state", "data", "updated_at"])
    return c


def set_convo(phone, state, data=None):
    Conversation.objects.update_or_create(phone=phone, defaults={"state": state, "data": data or {}})


def addon_defaults(code):
    """Details for an extra requested without a form (SMS, USSD): the offered time, e.g. late checkout until 14:00,
    which is what moves the door-code window and the automatic checkout once Amina approves it."""
    from apps.bookings.models import Addon

    addon = Addon.objects.filter(code=code).only("options").first()
    time = (addon.options or {}).get("time") if addon else None
    return {"time": time} if time else None


class GuestBot:
    def __init__(self, guest, text, inbound):
        self.g, self.text, self.inbound = guest, text, inbound
        self.phone, self.lang = guest.phone, guest.lang
        # "Hi!", "Status?" and "1." mean the same as "hi", "status" and "1"
        self.low = re.sub(r"[\s.!?,;:]+$", "", text.lower().strip())
        self.word = (self.low.split(" ", 1)[0] if self.low else "").strip(".!?,")
        self.rest = text.split(" ", 1)[1].strip() if " " in text else ""

    # -- plumbing
    def channel(self):
        # A question typed in the web chat is answered in the web chat; SMS questions get SMS answers.
        return "web" if getattr(self.inbound, "channel", "") == "web" else None

    def reply(self, body, kind="", handled="auto", booking=None):
        messaging.mark(self.inbound, handled, kind)
        messaging.send(
            self.phone, body, kind=kind or "bot_reply", sender="bot", booking=booking, channel=self.channel()
        )
        return body

    def say(self, key, handled="auto", booking=None, **ctx):
        return self.reply(messaging.render(key, self.lang, **ctx), kind=key, handled=handled, booking=booking)

    def booking(self):
        return bookings.current_booking(self.phone)

    # -- router
    def run(self):
        if SOS.match(self.text):
            return self.sos()
        if self.word in ("stop", "unsubscribe", "acha", "stopall"):
            self.g.sms_opt_out_at, self.g.marketing_opt_in = timezone.now(), False
            self.g.save(update_fields=["sms_opt_out_at", "marketing_opt_in"])
            return self.say("opted_out")
        if self.word in ("start", "subscribe", "unstop") and len(self.low.split()) == 1:
            self.g.sms_opt_out_at, self.g.marketing_opt_in = None, True
            self.g.save(update_fields=["sms_opt_out_at", "marketing_opt_in"])
            return self.say("opted_in")
        if self.word in ("lang", "lugha", "language", "lingua", "sprache", "langue") or (
            self.low in LANG_WORDS and len(self.low) > 2
        ):
            code = LANG_WORDS.get((self.rest or self.low).lower().strip())
            if code:
                self.g.lang = self.lang = code
                self.g.save(update_fields=["lang"])
                return self.say("lang_set")
            return self.reply("Reply LANG EN, LANG SW, LANG IT, LANG DE or LANG FR.", kind="lang_help")
        if self.low in ("checkout", "check out", "check-out", "toka", "nimetoka", "checking out"):
            return self.checkout()

        convo = get_convo(self.phone)
        handler = getattr(self, f"state_{convo.state}", None)
        if handler:
            result = handler(convo)
            if result is not None:
                return result

        for pattern, method in KEYWORDS:
            if re.match(pattern, self.low):
                result = getattr(self, method)()
                if result is not None:
                    return result

        from apps.operations.services import looks_like_issue

        if looks_like_issue(self.text) and self.booking() and self.booking().status in ("checked_in", "confirmed"):
            return self.issue(self.text)

        if nlu.looks_like_booking(self.text) and self._has_booking_details():
            return self.book(convo)
        answer = self.faq()
        if answer is not None:
            return answer
        if nlu.looks_like_booking(self.text) or convo.state == "collecting":
            result = self.book(convo)
            if result is not None:
                return result
        return self.relay()

    def _has_booking_details(self):
        ci, _ = nlu.parse_dates(self.text)
        return bool(
            ci or nlu.parse_guests(self.text) or nlu.parse_area(self.text, Area.objects.all()) or self.word == "book"
        )

    # -- safety
    def sos(self):
        from apps.safety.services import escalate

        alert = escalate(self.phone, "sms", text=self.rest)
        call_line = messaging.render(
            "help_calling" if alert.call_status in ("Queued", "dry_run") else "help_alerted", self.lang
        )
        return self.say("help_ack", handled="escalated", call_line=call_line)

    # -- conversation states
    def state_ticket_rating(self, convo):
        from apps.support import services as support
        from apps.support.models import Ticket

        set_convo(self.phone, "idle")
        if not re.fullmatch(r"[1-5](\s*(/5|stars?|\*))?", self.low):
            return None
        t = Ticket.objects.filter(pk=convo.data.get("ticket"), phone=self.phone).first()
        if t is None:
            return None
        rating = int(self.low[0])
        support.rate(t, rating, channel="sms")
        return self.say("ticket_sorry" if rating <= 2 else "ticket_thanks", rating=rating)

    def state_complaint(self, convo):
        set_convo(self.phone, "idle")
        if len(self.text.strip()) < 3:
            return None
        return self._complain(self.text)

    def state_guide_menu(self, convo):
        keys = convo.data.get("keys") or []
        if self.low.isdigit() and 1 <= int(self.low) <= len(keys):
            return self._guide(keys[int(self.low) - 1])
        set_convo(self.phone, "idle")
        return None

    def state_guide_list(self, convo):
        from apps.guide import services as guide
        from apps.guide.models import Place

        ids = convo.data.get("places") or []
        if self.low.isdigit() and 1 <= int(self.low) <= len(ids):
            p = Place.objects.filter(pk=ids[int(self.low) - 1], active=True).select_related("area").first()
            if p is not None:  # the list stays open: another number gets another place
                guide.record_hit(p)
                return self.reply(guide.details_sms(p, self.lang), kind="guide_place")
        set_convo(self.phone, "idle")
        return None

    def state_review(self, convo):
        from apps.reviews.services import record_rating

        if re.fullmatch(r"[1-5](\s*(/5|stars?|\*))?", self.low):
            b = Booking.objects.filter(ref=convo.data.get("ref")).first()
            if b:
                rating = int(self.low[0])
                review = record_rating(b, rating, channel="sms")
                set_convo(self.phone, "review_comment", {"review_id": review.pk, "rating": rating})
                return self.say("review_sorry" if rating <= 2 else "review_comment")
        set_convo(self.phone, "idle")
        return None

    def state_review_comment(self, convo):
        from apps.reviews.models import Review
        from apps.reviews.services import add_comment

        set_convo(self.phone, "idle")
        review = Review.objects.filter(pk=convo.data.get("review_id")).first()
        if not review:
            return None
        if self.word in ("skip", "no", "hapana", "none"):
            return self.say("review_thanks", rating=review.rating) if review.rating >= 3 else self.say("goodbye_ack")
        if SOS.match(self.text) or (nlu.looks_like_booking(self.text) and len(self.low.split()) < 6):
            return None
        add_comment(review, self.text)
        if review.rating <= 2:
            bookings.notify_host(
                f"Review comment from {self.g.display_name} ({review.rating}/5, {review.booking.ref}): {self.text[:300]}"
            )
            return self.reply(
                "Thank you for telling us - Amina will read this personally.", kind="review_comment_thanks"
            )
        return self.say("review_thanks", rating=review.rating)

    def state_offer(self, convo):
        if self.word not in ("book", "yes", "ndiyo", "ndio") and self.low not in YES:
            return None
        d = convo.data
        unit = Unit.objects.filter(pk=d.get("unit_id")).first()
        set_convo(self.phone, "idle")
        if not unit:
            return self.say("taken")
        from datetime import date

        return self.hold(
            unit, date.fromisoformat(d["check_in"]), date.fromisoformat(d["check_out"]), d.get("guests") or 1
        )

    def state_showing(self, convo):
        if not re.fullmatch(r"\d", self.low):
            return None
        opts = convo.data.get("options", [])
        idx = int(self.low) - 1
        if not 0 <= idx < len(opts):
            return None
        unit = Unit.objects.filter(pk=opts[idx]["id"]).first()
        from datetime import date

        d = convo.data
        return self.hold(
            unit, date.fromisoformat(d["check_in"]), date.fromisoformat(d["check_out"]), d.get("guests") or 1
        )

    def state_breakfast(self, convo):
        m = re.match(r"^([0-4])\b\s*(.*)$", self.low)
        if not m:
            return None
        b = Booking.objects.filter(ref=convo.data.get("ref")).first()
        set_convo(self.phone, "idle")
        if not b:
            return None
        style = BREAKFAST_CHOICES[m[1]]
        if style == "none":
            bookings.set_breakfast(b, None, channel="sms")
            return self.say("breakfast_none", booking=b)
        dietary = ", ".join(
            w.upper()
            for w in re.findall(r"halal|gluten|lactose|vegan|nut|kosher|diabet\w*|no pork|allerg\w*", m[2] or "")
        )
        try:
            ba = bookings.set_breakfast(b, style, dietary=dietary, channel="sms")
        except bookings.BookingError as e:
            return self.reply(str(e), kind="breakfast_error")
        return self.say("breakfast_saved", booking=b, summary=bookings.breakfast_summary(ba))

    def state_arrival(self, convo):
        mode = ARRIVAL_MODES.get(self.low.strip())
        if not mode:
            return None
        b = Booking.objects.filter(ref=convo.data.get("ref")).first()
        set_convo(self.phone, "idle")
        if not b:
            return None
        from apps.bookings.models import Addon

        tip = bookings.set_arrival_mode(b, mode)
        pickup = Addon.objects.filter(code="airport_pickup" if mode == "flight" else "sgr_pickup", active=True).first()
        if pickup and mode in ("flight", "sgr"):
            set_convo(self.phone, "pickup_offer", {"ref": b.ref, "code": pickup.code})
            return self.say("arrival_tips", booking=b, tip=tip, pickup_price=kes(pickup.price))
        return self.reply(tip, kind="arrival_tips", booking=b)

    def state_pickup_offer(self, convo):
        if self.word not in ("pickup", "yes", "ndiyo") and self.low not in YES:
            return None
        set_convo(self.phone, "idle")
        b = Booking.objects.filter(ref=convo.data.get("ref")).first()
        return self._add(b, convo.data.get("code", "airport_pickup")) if b else None

    def state_confirm_cancel(self, convo):
        b = Booking.objects.filter(ref=convo.data.get("ref")).first()
        if self.low in YES or self.word in YES:
            set_convo(self.phone, "idle")
            try:
                bookings.cancel(b, by="guest", reason="Cancelled by SMS")
            except bookings.BookingError as e:
                return self.reply(str(e), kind="cancel_error")
            messaging.mark(self.inbound, "auto", "cancel")
            return "cancelled"
        if self.low in NO or self.word in NO:
            set_convo(self.phone, "idle")
            return self.say("kept", ref=b.ref if b else "")
        return None

    def state_collecting(self, convo):
        return None  # handled by the booking path below

    def state_awaiting_payment(self, convo):
        if self.word in ("pay", "lipa", "retry"):
            return self.pay()
        return None

    # -- keyword commands
    def menu(self):
        prev = Booking.objects.filter(guest=self.g, status__in=("confirmed", "checked_in", "completed")).exists()
        hello = f"Karibu tena {first_name(self.g.name)}! " if prev and self.g.name else ""
        return self.reply(hello + messaging.render("menu", self.lang), kind="menu")

    def prices(self):
        from apps.properties.services import price_list_text

        return self.say("price_list", list=price_list_text())

    def breakfast(self):
        from apps.bookings.models import Addon

        b = self.booking()
        addon = Addon.objects.filter(code="breakfast", active=True).first()
        if not b or b.status not in ("held", "confirmed", "checked_in") or not addon:
            return None  # the knowledge base explains breakfast to non-guests
        set_convo(self.phone, "breakfast", {"ref": b.ref})
        return self.say(
            "breakfast_menu", booking=b, price=kes(addon.price), time=addon.options.get("hours", "7:30-10:00")
        )

    def eta(self):
        b = self.booking()
        hhmm = nlu.parse_eta(self.text)
        if not b or not hhmm:
            return None
        bookings.set_eta(b, hhmm)
        return self.say("eta_saved", booking=b, eta=hhmm)

    def arrive(self):
        b = self.booking()
        if not b:
            return None
        set_convo(self.phone, "arrival", {"ref": b.ref})
        return self.say("arrival_question", booking=b)

    def late(self):
        return self._add(self.booking(), "late_checkout")

    def early(self):
        return self._add(self.booking(), "early_checkin")

    def clean_request(self):
        return self._add(self.booking(), "mid_stay_clean")

    def pickup(self):
        return self._add(self.booking(), "airport_pickup")

    def extend(self):
        b = self.booking()
        if not b or b.status not in ("confirmed", "checked_in"):
            return None
        n = re.search(r"\d+", self.rest or "")
        text, handled = bookings.extend_by_sms(b, int(n.group()) if n else 1, thread_id=self._thread_id())
        return self.reply(text, kind="extend", handled=handled, booking=b)

    def _add(self, b, code):
        if not b or b.status not in ("held", "confirmed", "checked_in"):
            # a question about an extra ("airport pickup?", "late checkout?") is for the knowledge base
            if len(self.low.split()) > 1 and (answer := self.faq()) is not None:
                return answer
            return self.say("no_booking")
        try:
            ba = bookings.add_addon(b, code, channel="sms", details=addon_defaults(code))
        except bookings.BookingError as e:
            return self.reply(str(e), kind="addon_error", booking=b)
        if ba.status == "requested":
            return self.say("request_sent", booking=b, what=ba.addon.name.lower())
        return self.reply(
            f"Added: {ba.addon.name} ({kes(ba.total)}). Reply PAY to pay now.", kind="addon_added", booking=b
        )

    def register_id(self):
        number = re.sub(r"[^A-Za-z0-9]", "", self.rest or "")
        if len(number) < 5:
            return self.reply("Reply ID followed by your ID or passport number, e.g. ID 12345678.", kind="id_help")
        try:
            set_identity(self.g, id_type="", id_number=number, consent=True)
        except AuthError as e:
            return self.reply(str(e), kind="id_error")
        # id_last4 is stored masked ("••••7890"); the SMS says "ending 7890"
        return self.say("id_saved", id_type=self.g.get_id_type_display(), last4=self.g.id_last4.replace("•", ""))

    def code(self):
        b = bookings.active_stay(self.phone)
        if b:
            return self.say("checkin_code", booking=b, **bookings.guest_context(b))
        b = self.booking()
        if b and b.status == "confirmed":
            return self.reply(
                f"Your door code arrives by SMS on the morning of {bookings.guest_context(b)['check_in']}.",
                kind="code_info",
                booking=b,
            )
        return self.say("no_booking")

    def pay(self):
        from apps.payments.services import start_remote_payment

        b = self.booking()
        if not b or (b.status == "held" and not b.hold_active) or (b.status != "held" and b.balance_due <= 0):
            return (
                self.say("no_booking")
                if not b
                else self.reply("You're all paid up - thank you!", kind="paid", booking=b)
            )
        r = start_remote_payment(b)
        return self.reply(r["text"], kind="pay", booking=b)

    def paid_code(self):
        """PAID <M-Pesa code> [ref]: paid by Paybill, or a prompt that never confirmed - find the payment."""
        from apps.payments import c2b
        from apps.payments.providers import PaymentError

        code, *ref = self.rest.split()
        b = Booking.objects.filter(ref=c2b.normalise_ref("".join(ref)), guest=self.g).first() if ref else None
        b = b or self.booking() or Booking.objects.filter(guest=self.g).order_by("-created_at").first()
        if not b:
            return self.say("no_booking")
        try:
            r = c2b.claim(b, code, channel="sms")
        except PaymentError as e:
            return self.reply(str(e), kind="payment_claim", booking=b)
        return self.reply(r["message"], kind="payment_claim", booking=b)

    def status(self):
        b = self.booking()
        if not b:
            return self.say("no_booking")
        return self.say("status", booking=b, **bookings.guest_context(b))

    def cancel(self):
        ref = re.search(r"AMS-\d{4}|AMS-[A-Z0-9]+", self.text.upper())
        b = Booking.objects.filter(ref=ref.group(), guest=self.g).first() if ref else self.booking()
        if not b or b.status not in ("held", "confirmed"):
            return self.say("no_booking")
        q = bookings.refund_quote(b)
        set_convo(self.phone, "confirm_cancel", {"ref": b.ref})
        return self.say("cancel_quote", booking=b, refund_text=q["text"], **bookings.guest_context(b))

    def book_keyword(self):
        if self.rest:
            return None  # let the booking parser read "book 5 dec for 2"
        set_convo(self.phone, "collecting", {})
        return self.say("ask_dates", hello="")

    def checkin_ack(self):
        b = bookings.active_stay(self.phone)
        if b and self.low in ("1", "ok", "all good", "good", "sawa"):
            return self.say("goodbye_ack", booking=b)
        return None

    def report(self):
        b = self.booking()
        if not b:
            return None
        return self.issue(self.rest or self.text)

    # -- flows
    def checkout(self):
        reply = bookings.checkout_reply(self.phone, channel="sms")
        if reply:
            return self.reply(reply, kind="checkout")
        messaging.mark(self.inbound, "auto", "checkout")
        return "checked_out"

    def issue(self, text):
        from apps.operations.services import report_issue

        b = self.booking()
        if not b:
            return self.relay()
        from apps.notices.services import known_issue_text
        from apps.operations.services import classify_issue

        known = known_issue_text(b, classify_issue(text), self.lang)
        if known:
            return self.reply(known, kind="notice_known", booking=b)
        messaging.mark(self.inbound, "auto", "issue")
        task = report_issue(b, text, channel="sms")
        bookings.notify_host(f"Issue #{task.pk} at {b.unit.name} ({self.g.display_name}): {text[:120]}", booking=b)
        return "issue"

    def faq(self):
        s = SiteSettings.load()
        if not s.auto_answer:
            return None
        b = self.booking()
        ctx = messaging.faq_context(self.phone, b)
        hit = messaging.match_faq(self.text, self.lang, unit=b.unit if b else None, ctx=ctx)
        if not hit:
            return None
        faq, answer = hit
        return self.reply(answer, kind=f"faq:{faq.category}", booking=b)

    def book(self, convo):
        areas = list(Area.objects.all())
        found = {}
        ci, co = nlu.parse_dates(self.text)
        if ci:
            found.update(check_in=ci.isoformat(), check_out=co.isoformat())
        guests = nlu.parse_guests(self.text)
        if guests:
            found["guests"] = guests
        area = nlu.parse_area(self.text, areas)
        if area:
            found["area"] = area.slug
        data = {**(convo.data if convo.state == "collecting" else {}), **found}

        last = (
            Booking.objects.filter(guest=self.g, status__in=("confirmed", "checked_in", "completed"))
            .select_related("unit__area")
            .order_by("-id")
            .first()
        )
        if last and re.search(r"\b(same|usual|again|last time|kama mwisho)\b", self.low):
            data.setdefault("area", last.unit.area.slug)
            if self.g.last_guests:
                data.setdefault("guests", self.g.last_guests)
        hello = f"Welcome back{', ' + first_name(self.g.name) if self.g.name else ''}! " if last else ""

        if convo.state == "collecting" and not found and not re.search(r"\b(same|usual|again)\b", self.low):
            set_convo(self.phone, "idle")
            return None
        if not data.get("check_in"):
            set_convo(self.phone, "collecting", data)
            return self.say("ask_dates", hello=hello or ("" if self.lang != "en" else "Happy to help! "))
        from datetime import date

        ci, co = date.fromisoformat(data["check_in"]), date.fromisoformat(data["check_out"])
        if ci < today():
            set_convo(self.phone, "collecting", {k: v for k, v in data.items() if k not in ("check_in", "check_out")})
            return self.say("ask_dates", hello="That date has passed. ")
        guests = data.get("guests") or 1
        nights = (co - ci).days
        free = list(available_units(ci, co, area=data.get("area"), guests=guests))
        units = [u for u in free if u.min_nights <= nights <= u.max_nights]  # only homes the hold will accept
        if last:
            units.sort(key=lambda u: u.pk != last.unit_id)
        units = units[:3]
        dates = bookings.dates_text(ci, co, self.lang)
        longer = [u for u in free if u.min_nights > nights]
        if not units and longer:
            # free, but only for a longer stay: say so (and keep the area/guests) instead of waitlisting
            u = min(longer, key=lambda x: x.min_nights)
            set_convo(self.phone, "collecting", {k: v for k, v in data.items() if k not in ("check_in", "check_out")})
            example = f"{ci.day} {nice_date(ci, self.lang).split()[-1]}"
            return self.say("min_stay", unit=u.name, nights=u.min_nights, example=example)
        if not units:
            area_obj = Area.objects.filter(slug=data.get("area")).first()
            bookings.add_to_waitlist(self.g, ci, co, area=area_obj, guests=guests or 0, channel="sms")
            set_convo(self.phone, "idle")
            return self.say("none_free", dates=dates)
        options, parts = [], []
        for i, u in enumerate(units, 1):
            q = price_quote(u, ci, co, guests=guests)
            options.append({"id": u.pk, "name": u.name})
            parts.append(f"{i}) {u.name} ({u.area.name}) {kes(q['total'])}")
        set_convo(self.phone, "showing", {**data, "guests": guests, "options": options})
        return self.say(
            "options",
            hello=hello,
            dates=dates,
            list=" ".join(parts),
            choices=", ".join(str(i) for i in range(1, len(units) + 1)),
        )

    def hold(self, unit, ci, co, guests):
        from apps.payments.services import start_remote_payment

        try:
            b = bookings.create_hold(
                unit=unit, guest=self.g, check_in=ci, check_out=co, channel="sms", adults=max(1, int(guests))
            )
        except bookings.BookingError as e:
            set_convo(self.phone, "idle")
            return self.reply(str(e) + " Reply BOOK to see what's still free.", kind="hold_error")
        set_convo(self.phone, "awaiting_payment", {"ref": b.ref})
        pay = start_remote_payment(b)
        if pay.get("error"):
            return self.reply(pay["text"], kind="pay_error", booking=b)
        if pay["method"] == "card":
            messaging.mark(self.inbound, "auto", "hold_card")
            return "card_link_sent"
        return self.say("hold_mpesa", booking=b, amount=kes(pay["amount"]), **bookings.guest_context(b))

    # -- support desk (Voice + SMS)
    def complain(self):
        if len(self.rest) < 3:
            from apps.support.services import t_

            set_convo(self.phone, "complaint", {})
            return self.reply(t_("complaint_ask", self.lang, host=SiteSettings.load().host_name), kind="complaint_ask")
        return self._complain(self.rest)

    def _complain(self, text):
        from apps.support.services import open_ticket

        messaging.mark(self.inbound, "auto", "complaint")
        open_ticket(
            self.phone,
            category="complaint",
            subject=text.strip().split("\n", 1)[0][:140],
            description=text.strip(),
            channel=self.channel() or "sms",
            booking=self.booking(),
            reply_channel=self.channel(),
        )
        return "complaint"

    def callback(self):
        from apps.support.services import open_ticket

        messaging.mark(self.inbound, "auto", "callback")
        open_ticket(
            self.phone,
            category="callback",
            subject="Please call me back",
            description=self.rest,
            channel=self.channel() or "sms",
            booking=self.booking(),
            reply_channel=self.channel(),
        )
        return "callback"

    def tickets(self):
        from apps.support.services import list_text

        return self.reply(list_text(self.phone, self.lang), kind="tickets")

    def ticket_status(self):
        from apps.support.services import detail_text

        return self.reply(detail_text(self.phone, int(re.sub(r"\D", "", self.low)), self.lang), kind="ticket_status")

    # -- local guide (USSD + SMS)
    def explore(self):
        from apps.guide import services as guide

        key = guide.key_for(self.rest)
        if key:
            return self._guide(key)
        body, keys = guide.menu_message(self.lang)
        if not body:
            return self.reply(guide.word("none", self.lang), kind="guide_none")
        guide.remember(self.phone, "guide_menu", {"keys": keys}, force=True)
        return self.reply(body, kind="guide_menu")

    def events(self):
        return self._guide("events")

    def food(self):
        return self._guide("food")

    def _guide(self, key):
        from apps.guide import services as guide

        if key == "events":
            set_convo(self.phone, "idle")
            return self.reply(guide.events_sms(self.lang), kind="guide_events")
        b = self.booking()
        places = guide.places_for(key, guide.origin_of(b.unit) if b else None)[:5]
        if not places:
            set_convo(self.phone, "idle")
            return self.reply(guide.word("none", self.lang), kind="guide_none")
        guide.remember(self.phone, "guide_list", {"places": [p.pk for p in places]}, force=True)
        return self.reply(guide.list_message(key, places, self.lang), kind="guide_list")

    # -- service alerts (SMS) and the outage data bundle (Mobile Data)
    def alerts(self):
        from apps.notices.services import status_text

        return self.reply(status_text(self.phone, self.lang), kind="notice_status")

    def data(self):
        from apps.notices.services import data_request

        b = bookings.active_stay(self.phone)
        text = data_request(b, self.lang) if b else None
        return self.reply(text or messaging.render("data_none", self.lang), kind="notice_data")

    # -- rewards (Airtime + Mobile Data)
    def points(self):
        from apps.rewards.services import summary_text

        return self.reply(summary_text(self.g), kind="rewards_summary")

    def redeem(self):
        from apps.rewards.services import redeem, summary_text

        if re.search(r"\b(data|bundle|mb|internet)\b", self.low):
            kind = "data"
        elif re.search(r"\b(airtime|salio|credit|kes)\b", self.low):
            kind = "airtime"
        else:
            return self.reply(summary_text(self.g), kind="rewards_summary")
        _, text = redeem(self.g, kind)
        return self.reply(text, kind="rewards_redeem")

    def refer(self):
        from apps.rewards.services import refer_text

        return self.reply(refer_text(self.g), kind="rewards_refer")

    def referral_code(self):
        from apps.rewards.services import apply_referral

        _, text = apply_referral(self.g, self.low.split()[-1])
        return self.reply(text, kind="rewards_referral")

    def relay(self):
        b = self.booking()
        thread = relay_to_host(self.phone, self.g, self.text, b)
        messaging.mark(self.inbound, "relayed", "question")
        recently_acked = thread.messages.filter(
            direction="out", kind="relay_ack", created_at__gt=timezone.now() - timezone.timedelta(minutes=30)
        ).exists()
        if not recently_acked:
            messaging.send(
                self.phone,
                messaging.render("relay_ack", self.lang),
                kind="relay_ack",
                sender="bot",
                channel=self.channel(),
            )
        return "relayed"

    def _thread_id(self):
        return messaging.get_thread(self.phone, self.g).pk


def relay_to_host(phone, guest, text, booking=None):
    """Pass a guest's question to Amina's phone. She answers with '#<thread> <reply>' (HostCommands)."""
    thread = messaging.get_thread(phone, guest)
    context = f" [{booking.ref} {booking.unit.name}]" if booking else ""
    messaging.send(
        SiteSettings.load().host_contact,
        f"#{thread.pk} {guest.name or phone}{context}: {text[:300]} (reply #{thread.pk} <text>)",
        kind="relay",
        booking=booking,
    )
    return thread


# keyword → handler (checked in order; a handler returning None falls through)
KEYWORDS = [
    (r"^(menu|info|hi|hello|hey|jambo|habari|mambo|hujambo|ciao|hallo|bonjour|start)$", "menu"),
    (r"^(prices?|bei|rates?|cost|tariff|prezzi|preise|prix)\b", "prices"),
    (r"^(breakfast|kifungua|chakula cha asubuhi|colazione|frühstück|fruhstuck|petit)", "breakfast"),
    (r"^(eta|arriving|arrival time|tutafika|nitafika|we arrive|arriving at)\b", "eta"),
    (r"^(arrive|travel|transport|getting there|usafiri)$", "arrive"),
    (r"^(late|late checkout|late check-out)\b", "late"),
    (r"^(early|early check-?in)\b", "early"),
    (r"^(clean|cleaning|usafi)$", "clean_request"),
    (r"^(pickup|pick up|transfer|airport)\b", "pickup"),
    (r"^(extend|ongeza)\b", "extend"),
    (r"^(id|passport|kitambulisho)\s+\S+", "register_id"),
    (r"^(code|door code|nambari|pin)$", "code"),
    (r"^(pay|lipa|retry)$", "pay"),
    (r"^(paid|nimelipa|nimelipia)\s+[a-z0-9]{8,12}(\s+(ams)?[- ]?[a-z0-9]+)?$", "paid_code"),
    (r"^(status|my booking|booking|ref)$", "status"),
    (r"^(cancel|ghairi)\b", "cancel"),
    (r"^(book|booking please|nataka kubook)$", "book_keyword"),
    (r"^(complain|complaint|malalamiko|lalamiko|nalalamika)\b", "complain"),
    (r"^(call me|call me back|callback|call back|nipigie|nipigieni)\b", "callback"),
    (r"^(tickets?|my tickets|requests|my requests|maombi|maombi yangu)$", "tickets"),
    (r"^(t-?|ticket\s*#?\s*)\d{1,7}$", "ticket_status"),
    (r"^(explore|guide|tours?|things to do|sightseeing|vivutio|gundua)\b", "explore"),
    (r"^(events?|what'?s on|matukio)$", "events"),
    (r"^(food|eat|restaurants?|chakula)$", "food"),
    (r"^(alerts?|outages?|notices?|service status|huduma)$", "alerts"),
    (r"^(data|bundle|data bundle|internet)$", "data"),
    (r"^(points|rewards?|zawadi|pointi|loyalty)$", "points"),
    (r"^(redeem|tumia pointi)\b", "redeem"),
    (r"^(refer|invite|share|alika)$", "refer"),
    (r"^(ref|referral|invite code|promo)\s+[a-z]{3,}\d{2,6}$", "referral_code"),
    (r"^(issue|problem|report|tatizo|shida)\b", "report"),
    (r"^(1|ok|all good|good|sawa)$", "checkin_ack"),
]


class HostCommands:
    """Amina manages everything from her own phone: '#12 text' replies to guest thread 12, plain text
    replies to the last guest who asked, YES/NO 34 approves a request, OK acknowledges an alert."""

    def __init__(self, phone, text, inbound):
        self.phone, self.text, self.inbound = phone, text, inbound
        self.low = re.sub(r"[\s.!?,;:]+$", "", text.lower().strip())

    def say(self, body):
        messaging.mark(self.inbound, "na", "host_cmd")
        messaging.send(self.phone, body, kind="host_cmd_reply", sender="system")
        return body

    def run(self):
        from apps.accounts.models import User
        from apps.bookings.models import BookingAddon

        host = User.objects.filter(phone=self.phone).first()
        m = re.match(r"^#(\d+)\s+([\s\S]+)$", self.text)
        if m:
            thread = Thread.objects.filter(pk=int(m[1])).first()
            if not thread:
                return self.say(f"No guest thread #{m[1]}.")
            return self._reply(thread, m[2], host)
        m = re.match(r"^(yes|no|ndiyo|hapana)\s+c\s*(\d+)$", self.low)
        if m:  # YES C12 / NO C12: a date change waiting for Amina
            return self.say(bookings.decide_change_by_sms(int(m[2]), m[1] in ("yes", "ndiyo"), actor=host))
        m = re.match(r"^(yes|no|ndiyo|hapana)\s+(\d+)$", self.low)
        if m:
            ba = BookingAddon.objects.filter(pk=int(m[2])).select_related("booking", "addon").first()
            if not ba:
                return self.say(f"No request #{m[2]}.")
            bookings.decide_addon(ba, m[1] in ("yes", "ndiyo"), actor=host)
            return self.say(
                f"{'Approved' if m[1] in ('yes', 'ndiyo') else 'Declined'}: {ba.addon.name} for {ba.booking.ref}. Guest told."
            )
        if self.low in ("ok", "ack", "sawa", "handled"):
            from apps.safety.services import acknowledge_latest

            alert = acknowledge_latest(host)
            return self.say(f"Alert #{alert.pk} acknowledged." if alert else "No open alerts.")
        if self.low in ("status", "today", "leo"):
            from apps.operations.services import digest_numbers

            n = digest_numbers()
            return self.say(
                f"Today: {n['arrivals']} arriving, {n['departures']} leaving, {n['in_house']} in-house, {n['breakfasts']} breakfasts, "
                f"{n['tasks']} tasks, {n['unread']} chats waiting, {n['alerts']} alerts."
            )
        if self.low in ("menu", "help", "commands"):
            return self.say(
                "Commands: #12 <text> reply to guest 12 | <text> reply to last guest | YES/NO <id> requests | OK ack alert | STATUS"
                " | T12 <text> answer ticket 12 | CALL T12 | RESOLVE T12 | TICKETS"
                " | OUTAGE <power|water|wifi> <home|ALL> <message> | RESTORED <id> | ALERTS"
            )
        support_reply = self._support(host)
        if support_reply is not None:
            return support_reply
        if re.match(r"^(outage|maintenance|advisory)\s", self.low):
            from apps.notices.services import report_by_text

            return self.say(report_by_text(host, self.text))
        m = re.match(r"^(?:restored|back)\s+#?(\d+)\s*([\s\S]*)$", self.text, re.IGNORECASE)
        if m:
            from apps.notices.services import restore_by_text

            return self.say(restore_by_text(host, int(m[1]), m[2].strip()))
        if self.low in ("alerts", "notices", "outages"):
            from apps.notices.services import open_list_text

            return self.say(open_list_text())
        waiting = Thread.objects.filter(needs_reply=True).order_by("-last_message_at").first()
        if not waiting:
            return self.say("No guest is waiting for a reply. Start with #<thread> to pick a guest.")
        return self._reply(waiting, self.text, host)

    def _reply(self, thread, text, host):
        messaging.mark(self.inbound, "na", "host_reply")
        reply_as_host(thread.phone, text, user=host)
        return "replied"

    def _support(self, host):
        """T12 <text> answers a ticket, CALL T12 connects Amina to the guest, RESOLVE T12 [note] closes it."""
        from apps.support import services as support
        from apps.support.models import Ticket

        if self.low in ("tickets", "support", "complaints"):
            return self.say(support.host_list_text())
        bare = re.fullmatch(r"t-?(\d+)", self.low)
        if bare:  # just "T12": what is it and where is it at (never relayed to a guest as a reply)
            return self.say(support.host_detail_text(int(bare[1])))
        m = re.match(
            r"^(resolve|close|done|solved|call)\s+t-?(\d+)\s*([\s\S]*)$", self.text, re.IGNORECASE
        ) or re.match(r"^()t-?(\d+)\s+([\s\S]+)$", self.text, re.IGNORECASE)
        if not m:
            return None
        t = Ticket.objects.filter(pk=int(m[2])).select_related("guest", "booking").first()
        if t is None:
            return self.say(f"No ticket T{m[2]}.")
        verb, rest = m[1].lower(), m[3].strip()
        if verb == "call":
            return self.say(support.call_guest(t, user=host)["detail"])
        if verb:
            support.resolve(t, note=rest, user=host, channel="sms")
            return self.say(f"{t.ref} resolved - the guest has been told.")
        support.reply(t, rest, user=host)
        return self.say(f"Sent to {t.guest.display_name if t.guest_id else t.phone} ({t.ref}).")


def reply_as_host(phone, text, user=None, channel="sms"):
    """Amina's reply on the channel she picked: SMS, WhatsApp (SMS when WhatsApp isn't set up) or the web chat."""
    from django.conf import settings

    s = SiteSettings.load()
    b = bookings.current_booking(phone)
    if channel == "whatsapp" and not settings.AT_WHATSAPP_NUMBER:
        channel = "sms"
    return messaging.send(
        phone,
        f"{s.host_name}: {text}",
        sender="host",
        user=user,
        booking=b,
        kind="host_reply",
        channel=channel,
    )


class StaffCommands:
    def __init__(self, staff, text, inbound):
        self.staff, self.text, self.inbound = staff, text, inbound
        self.low = re.sub(r"[\s.!?,;:]+$", "", text.lower().strip())

    def say(self, body):
        messaging.mark(self.inbound, "na", "staff_cmd")
        messaging.send(self.staff.phone, body, kind="staff_cmd_reply", sender="system")
        return body

    def run(self):
        from apps.operations import services as ops
        from apps.operations.models import Task

        m = re.match(r"^(done|start|imeisha|nimemaliza|naanza)(?![a-z])\s*#?(\d+)?\s*(.*)$", self.low)
        if m:
            if m[2]:
                task = Task.objects.filter(pk=int(m[2])).select_related("unit").first()
                if not task:
                    return self.say(f"No task #{m[2]}.")
            else:  # a bare DONE / START means "my task" when there is only one
                mine = list(ops.open_tasks_for(self.staff)[:6])
                verb = "START" if m[1] in ("start", "naanza") else "DONE"
                if len(mine) != 1:
                    return self.say(
                        "; ".join(f"#{t.pk} {t.title}" for t in mine) + f". Reply {verb} <id>."
                        if mine
                        else "No open tasks. Asante!"
                    )
                task = mine[0]
            if m[1] in ("start", "naanza"):
                ops.start_task(task, self.staff)
                return self.say(f"Task #{task.pk} started. Reply DONE {task.pk} when finished.")
            ops.complete_task(task, self.staff, note=m[3])
            return self.say(f"Task #{task.pk} closed. Asante {first_name(self.staff.name)}!")
        if self.low in ("tasks", "kazi", "list"):
            tasks = list(ops.open_tasks_for(self.staff)[:5])
            if not tasks:
                return self.say("No open tasks. Asante!")
            return self.say("; ".join(f"#{t.pk} {t.title}" for t in tasks) + ". Reply DONE <id> when finished.")
        if self.low in ("breakfast", "kitchen", "jikoni") and self.staff.role in ("cook", "manager"):
            from datetime import timedelta

            return self.say(ops.kitchen_sheet_text(today() + timedelta(days=1)) or "No breakfasts booked for tomorrow.")
        if self.low in ("gate", "geti", "arrivals") and self.staff.role in ("security", "manager"):
            arrivals = ops.gate_list()
            return self.say(
                "; ".join(
                    f"{b.unit.name}: {b.guest.display_name}{' car ' + b.vehicle_plate if b.vehicle_plate else ''}"
                    for b in arrivals
                )
                or "No arrivals today."
            )
        if re.match(r"^(outage|maintenance)\s", self.low):
            from apps.notices.services import report_by_text

            return self.say(report_by_text(self.staff, self.text))
        m = re.match(r"^restored\s+#?(\d+)\s*([\s\S]*)$", self.text, re.IGNORECASE)
        if m:
            from apps.notices.services import restore_by_text

            return self.say(restore_by_text(self.staff, int(m[1]), m[2].strip()))
        bookings.notify_host(f"Staff {self.staff.display_name} ({self.staff.get_role_display()}): {self.text[:300]}")
        return self.say(
            "Sent to Amina. Commands: TASKS, DONE <id>, START <id>"
            + (", BREAKFAST" if self.staff.role == "cook" else "")
        )
