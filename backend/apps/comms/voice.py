"""Call Amina — the voice line (Africa's Talking Voice; no sandbox, needs a live number).

One callback per caller action; state lives in VoiceSession so any worker can answer the next hop.
Outbound calls we place (safety alerts to Amina, optional welcome walkthroughs to guests) are
pre-registered by the sessionId AT returns, so we know what the call is for when it connects.
"""

import logging
from datetime import timedelta
from xml.sax.saxutils import escape, quoteattr

from django.conf import settings
from django.utils import timezone

from apps.accounts.services import get_or_create_user
from apps.bookings import services as bookings
from apps.core.models import OnceMarker, SiteSettings
from apps.core.utils import first_name, normalize_phone, spoken_digits, today, weekend_start
from apps.messaging import services as messaging
from apps.properties.services import available_units
from apps.properties.services import quote as price_quote

from . import deferred
from .models import VoiceSession

log = logging.getLogger("amina.voice")

T = {
    "en": {
        "welcome": "Welcome to Amina Stays. For English, press 1. Kwa Kiswahili, bonyeza 2.",
        "main": "Press 1 to check availability and book. Press 2 to hear our prices and breakfast. Press 3 for your booking and check-in directions. Press 4 to talk to Amina. Press 5 to make a complaint or report a problem. Press 6 for things to see and do nearby. Press 9 at any time for urgent help.",
        "back": "Welcome back{name}. ",
        "when": "When would you like to stay? Press 1 for tonight. Press 2 for tomorrow. Press 3 for this weekend. Press 4 to choose your dates by text message.",
        "nights": "How many nights? Press a number from 1 to 7.",
        "min_stay": "The homes free then need a stay of at least {nights} nights.",
        "guests": "How many guests? Press a number from 1 to 8.",
        "by_text": "We have sent you a text message. Just reply with your dates, for example 5 December for 3 nights. Asante, goodbye.",
        "none": "Sorry, nothing is free for those dates. We have added you to our waiting list and will text you if something opens up. Goodbye.",
        "option": "Press {i} for {name} in {area}, {total} shillings in total.",
        "held": "We are holding {name} for you. The total is {total} shillings. {pay} Your confirmation will arrive by text message. Asante, goodbye.",
        "pay_mpesa": "An M-Pesa prompt is coming to this phone now.",
        "pay_card": "We have sent a secure card payment link to this phone by text message.",
        "prices": "Our homes: {list}. Breakfast is {bf} shillings per person per day, with a Swahili breakfast of mahamri, chai and fruit, or continental. Press 1 to book, or 0 for the main menu.",
        "price_item": "{name} in {area}, from {price} shillings a night",
        "no_booking": "We could not find a booking for this number. Press 1 to book, or 0 for the main menu.",
        "booking": "Your booking at {unit} runs from {check_in} to {check_out}. Reference {ref}. Status: {status}. ",
        "booking_opts": "Press 1 to hear the directions. Press 2 to receive your door code by text message. Press 0 for the main menu.",
        "directions": "{unit}. {directions}. Look out for {landmark}. We have also sent the directions by text message. Goodbye.",
        "directions_early": "{unit} is in {area}. The full directions and Wi-Fi details are shared by text message 2 days before you arrive. Goodbye.",
        "code_sent": "We have sent your door code by text message. Goodbye.",
        "code_later": "Your door code will arrive by text message on the morning of {check_in}. Goodbye.",
        "ask": "Press 1 to be connected to Amina now. Press 2 to leave her a voice message.",
        "connecting": "Connecting you to Amina. Please hold.",
        "record": "Please leave your message after the beep, then press the hash key.",
        "recorded": "Thank you. Amina will get back to you. Goodbye.",
        "help": "We are alerting Amina and connecting you to her now. If you are in danger, hang up and call 9 9 9 or 1 1 2.",
        "invalid": "Sorry, that is not a valid choice.",
        "no_input": "We did not receive any input. Goodbye.",
        "error": "Sorry, something went wrong. Please try again later.",
        "alert": "Urgent alert from Amina Stays. {who}, {where}, needs help. Press 1 to be connected to the guest now.",
        "alert_none": "Amina Stays alert. There are no open alerts. Goodbye.",
        "alert_connect": "Connecting you to the guest now.",
        "alert_bye": "The details have also been sent to you by text. Goodbye.",
        "welcome_call": "Karibu {name}! This is Amina Stays. Your door code for {unit} has been sent to you by text message. Press 1 to hear the directions. Press 2 to talk to Amina.",
        "complaint": "Please tell us what went wrong after the beep, then press the hash key. We will text you a reference number.",
        "complaint_done": "Thank you. We will text you a reference number, and Amina will get back to you. Goodbye.",
        "guide": "Here are some favourites near you. {items} We have sent these and more to you by text message. Press 0 for the main menu.",
        "guide_item": "{name}: {summary}.",
        "guide_none": "Our local guide is being updated. Text the word EXPLORE to this number for tips. Press 0 for the main menu.",
        "call_gone": "This call-back is no longer needed. Goodbye.",
        "call_handled": "That request has already been handled. Goodbye.",
        "call_connect": "Connecting you to the guest now.",
        "call_bye": "We will remind you by text. Goodbye.",
    },
    "sw": {
        "main": "Bonyeza 1 kuangalia nafasi na kuweka nafasi. Bonyeza 2 kusikia bei na kifungua kinywa. Bonyeza 3 kwa nafasi yako na maelekezo. Bonyeza 4 kuongea na Amina. Bonyeza 5 kutoa malalamiko au kuripoti tatizo. Bonyeza 6 kusikia vivutio vya karibu. Bonyeza 9 wakati wowote kwa msaada wa dharura.",
        "back": "Karibu tena{name}. ",
        "when": "Ungependa kukaa lini? Bonyeza 1 kwa leo usiku. Bonyeza 2 kwa kesho. Bonyeza 3 kwa wikendi hii. Bonyeza 4 kuchagua tarehe kwa ujumbe mfupi.",
        "nights": "Usiku ngapi? Bonyeza nambari kati ya 1 na 7.",
        "min_stay": "Nyumba zilizo wazi zinahitaji angalau usiku {nights}.",
        "guests": "Wageni wangapi? Bonyeza nambari kati ya 1 na 8.",
        "by_text": "Tumekutumia ujumbe mfupi. Jibu na tarehe zako, kwa mfano 5 Desemba usiku 3. Asante, kwaheri.",
        "none": "Samahani, hakuna nafasi kwa tarehe hizo. Tumekuweka kwenye orodha ya kusubiri. Kwaheri.",
        "option": "Bonyeza {i} kwa {name}, {area}, shilingi {total} kwa jumla.",
        "held": "Tumekuwekea {name}. Jumla ni shilingi {total}. {pay} Uthibitisho utakuja kwa ujumbe mfupi. Asante, kwaheri.",
        "pay_mpesa": "Ombi la M-Pesa linakuja kwenye simu hii sasa.",
        "pay_card": "Tumekutumia kiungo cha kulipa kwa kadi kwa ujumbe mfupi.",
        "prices": "Nyumba zetu: {list}. Kifungua kinywa ni shilingi {bf} kwa mtu kwa siku. Bonyeza 1 kuweka nafasi, au 0 kurudi.",
        "price_item": "{name}, {area}, kuanzia shilingi {price} kwa usiku",
        "no_booking": "Hatukupata nafasi kwa nambari hii. Bonyeza 1 kuweka nafasi, au 0 kurudi.",
        "booking": "Nafasi yako ni {unit} kuanzia {check_in} hadi {check_out}. Nambari ya kumbukumbu {ref}. ",
        "booking_opts": "Bonyeza 1 kusikia maelekezo. Bonyeza 2 kupata nambari ya mlango kwa ujumbe mfupi. Bonyeza 0 kurudi.",
        "directions": "{unit}. {directions}. Tafuta {landmark}. Tumekutumia maelekezo kwa ujumbe mfupi pia. Kwaheri.",
        "directions_early": "{unit} iko {area}. Maelekezo kamili na Wi-Fi yatatumwa kwa ujumbe mfupi siku 2 kabla ya kufika. Kwaheri.",
        "code_sent": "Tumekutumia nambari ya mlango kwa ujumbe mfupi. Kwaheri.",
        "code_later": "Nambari ya mlango itakuja kwa ujumbe mfupi asubuhi ya {check_in}. Kwaheri.",
        "ask": "Bonyeza 1 kuunganishwa na Amina sasa. Bonyeza 2 kumwachia ujumbe wa sauti.",
        "connecting": "Tunakuunganisha na Amina. Tafadhali subiri.",
        "record": "Tafadhali acha ujumbe wako baada ya mlio, kisha bonyeza alama ya reli.",
        "recorded": "Asante. Amina atakujibu. Kwaheri.",
        "help": "Tunamjulisha Amina sasa na kukuunganisha naye. Ukiwa hatarini, kata simu na piga 9 9 9 au 1 1 2.",
        "invalid": "Samahani, chaguo hilo si sahihi.",
        "no_input": "Hatukupokea jibu lolote. Kwaheri.",
        "error": "Samahani, kuna tatizo. Tafadhali jaribu tena baadaye.",
        "welcome_call": "Karibu {name}! Hii ni Amina Stays. Nambari ya mlango wa {unit} imetumwa kwa ujumbe mfupi. Bonyeza 1 kusikia maelekezo. Bonyeza 2 kuongea na Amina.",
        "complaint": "Tafadhali tueleze tatizo baada ya mlio, kisha bonyeza alama ya reli. Tutakutumia nambari ya kumbukumbu kwa ujumbe mfupi.",
        "complaint_done": "Asante. Tutakutumia nambari ya kumbukumbu, na Amina atakujibu. Kwaheri.",
        "guide": "Hivi ni baadhi ya vivutio karibu nawe. {items} Tumekutumia hivi na zaidi kwa ujumbe mfupi. Bonyeza 0 kurudi.",
        "guide_item": "{name}: {summary}.",
        "guide_none": "Mwongozo wetu unasasishwa. Tuma neno EXPLORE kwa nambari hii kupata ushauri. Bonyeza 0 kurudi.",
    },
}


def tr(lang, key, **kw):
    text = T.get(lang, T["en"]).get(key) or T["en"][key]
    return text.format(**kw) if kw else text


# ---------- XML ----------


def callback_url():
    base = settings.PUBLIC_URL.rstrip("/")
    secret = settings.AT_WEBHOOK_SECRET
    return f"{base}/at/{secret}/voice" if secret else f"{base}/at/voice"


def say(text, lang="en"):
    voice = ' voice="swahili"' if lang == "sw" else ""
    return f"<Say{voice}>{escape(text)}</Say>"


def xml(inner):
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>'


def ask(prompt, lang, no_input=None, digits=1):
    return xml(
        f'<GetDigits timeout="15" numDigits="{digits}" finishOnKey="#" callbackUrl={quoteattr(callback_url())}>{say(prompt, lang)}</GetDigits>'
        f"{say(no_input or tr(lang, 'no_input'), lang)}"
    )


def end(text, lang="en"):
    return xml(say(text, lang))


def dial(prompt, numbers, lang="en"):
    nums = ",".join(p for p in (normalize_phone(n) for n in numbers if n) if p)  # AT only dials +E.164 numbers
    return xml(
        f'{say(prompt, lang)}<Dial phoneNumbers={quoteattr(nums)} sequential="true" record="false" maxDuration="900"/>'
    )


def record_msg(lang, prompt="record", after="recorded"):
    return xml(
        f'<Record finishOnKey="#" maxLength="90" trimSilence="true" playBeep="true" callbackUrl={quoteattr(callback_url())}>'
        f"{say(tr(lang, prompt), lang)}</Record>{say(tr(lang, after), lang)}"
    )


def _speak_date(d, lang):
    from apps.core.utils import nice_date

    return nice_date(d, lang)


# ---------- inbound IVR ----------


class Call:
    def __init__(self, session, phone, digits):
        self.s, self.phone, self.d = session, phone, digits
        self.st = session.state
        self.lang = self.st.get("lang", "en")

    def save(self, **updates):
        self.st.update(updates)
        self.s.state = self.st
        self.s.save(update_fields=["state", "updated_at"])

    def main_menu(self, prefix=""):
        self.st.pop("retry_guests", None)  # a new booking attempt asks for the guests again
        self.save(step="main")
        return ask(prefix + tr(self.lang, "main"), self.lang)

    def handle(self):
        step = self.st.get("step")
        if self.d == "9" and step not in (None, "lang"):
            from apps.safety.services import escalate

            alert = escalate(self.phone, "voice", call=False)
            self.save(step="help", dialed_host=True, alert_id=alert.pk)
            s = SiteSettings.load()
            return dial(tr(self.lang, "help"), [s.host_contact, s.backup_phone], self.lang)
        if self.d == "0" and step not in (None, "lang", "main"):
            return self.main_menu()

        if step is None:
            self.save(step="lang")
            return ask(T["en"]["welcome"], "en")
        if step == "lang":
            self.lang = "sw" if self.d == "2" else "en"
            user, _ = get_or_create_user(self.phone, channel="voice")
            if self.d in ("1", "2") and user.lang != self.lang:
                user.lang = self.lang
                user.save(update_fields=["lang"])
            self.save(lang=self.lang)
            back = user.bookings.filter(status__in=("confirmed", "checked_in", "completed")).exists()
            name = f" {first_name(user.name)}" if user.name else ""
            return self.main_menu(tr(self.lang, "back", name=name) if back else "")
        return getattr(self, f"step_{step}", self.step_main)()

    def step_main(self):
        if self.d == "1":
            self.save(step="when")
            return ask(tr(self.lang, "when"), self.lang)
        if self.d == "2":
            return self.prices()
        if self.d == "3":
            return self.my_booking()
        if self.d == "4":
            self.save(step="ask")
            return ask(tr(self.lang, "ask"), self.lang)
        if self.d == "5":
            self.save(step="complaint")  # the recording reaches the Record callback and becomes a support ticket
            return record_msg(self.lang, "complaint", "complaint_done")
        if self.d == "6":
            return self.guide()
        return self.main_menu(tr(self.lang, "invalid") + " ")

    def step_when(self):
        t = today()
        if self.d == "1":
            self.save(step="nights", check_in=t.isoformat())
            return ask(tr(self.lang, "nights"), self.lang)
        if self.d == "2":
            self.save(step="nights", check_in=(t + timedelta(days=1)).isoformat())
            return ask(tr(self.lang, "nights"), self.lang)
        if self.d == "3":
            ci = weekend_start(t)
            self.save(
                step="guests",
                check_in=ci.isoformat(),
                check_out=(ci + timedelta(days=2 if ci.weekday() == 4 else 1)).isoformat(),
            )
            return ask(tr(self.lang, "guests"), self.lang)
        if self.d == "4":
            from apps.messaging.models import Conversation

            Conversation.objects.update_or_create(
                phone=self.phone, defaults={"state": "collecting", "data": {"via": "voice"}}
            )
            messaging.send(
                self.phone, messaging.render("ask_dates", self.lang, hello="Hi from Amina Stays! "), kind="ask_dates"
            )
            return end(tr(self.lang, "by_text"), self.lang)
        return ask(tr(self.lang, "invalid") + " " + tr(self.lang, "when"), self.lang)

    def step_nights(self):
        if not (self.d.isdigit() and 1 <= int(self.d) <= 7):
            return ask(tr(self.lang, "invalid") + " " + tr(self.lang, "nights"), self.lang)
        from datetime import date

        ci = date.fromisoformat(self.st["check_in"])
        guests = self.st.pop("retry_guests", None)  # asked again after a minimum-stay miss
        self.save(step="guests", check_out=(ci + timedelta(days=int(self.d))).isoformat())
        if guests:
            return self.offer(guests)
        return ask(tr(self.lang, "guests"), self.lang)

    def step_guests(self):
        if not (self.d.isdigit() and 1 <= int(self.d) <= 8):
            return ask(tr(self.lang, "invalid") + " " + tr(self.lang, "guests"), self.lang)
        return self.offer(int(self.d))

    def offer(self, guests):
        from datetime import date

        ci, co = date.fromisoformat(self.st["check_in"]), date.fromisoformat(self.st["check_out"])
        nights = (co - ci).days
        free = list(available_units(ci, co, guests=guests))
        units = [u for u in free if u.min_nights <= nights <= u.max_nights][:4]  # only homes the hold accepts
        longer = [u.min_nights for u in free if nights < u.min_nights <= 7]
        if not units and longer:
            self.save(step="nights", retry_guests=guests)
            return ask(tr(self.lang, "min_stay", nights=min(longer)) + " " + tr(self.lang, "nights"), self.lang)
        if not units:
            user, _ = get_or_create_user(self.phone, channel="voice")
            bookings.add_to_waitlist(user, ci, co, guests=guests, channel="voice")
            return end(tr(self.lang, "none"), self.lang)
        options = [{"id": u.pk, "name": u.name} for u in units]
        prompt = " ".join(
            tr(
                self.lang,
                "option",
                i=i,
                name=u.name,
                area=u.area.name,
                total=price_quote(u, ci, co, guests=guests)["total"],
            )
            for i, u in enumerate(units, 1)
        )
        self.save(step="pick", guests=guests, options=options, prompt=prompt)
        return ask(prompt, self.lang)

    def step_pick(self):
        from datetime import date

        from apps.properties.models import Unit

        opts = self.st.get("options", [])
        if not (self.d.isdigit() and 1 <= int(self.d) <= len(opts)):
            return ask(tr(self.lang, "invalid") + " " + self.st.get("prompt", ""), self.lang)
        unit = Unit.objects.get(pk=opts[int(self.d) - 1]["id"])
        user, _ = get_or_create_user(self.phone, channel="voice")
        try:
            b = bookings.create_hold(
                unit=unit,
                guest=user,
                check_in=date.fromisoformat(self.st["check_in"]),
                check_out=date.fromisoformat(self.st["check_out"]),
                channel="voice",
                adults=self.st.get("guests", 1),
                lang=self.lang,
            )
        except bookings.BookingError as e:
            return end(str(e), self.lang)
        self.save(step="done", ref=b.ref)
        deferred.after_response(deferred.push_payment, b.pk)  # never wait on Daraja inside a voice callback
        from apps.payments.services import can_prompt

        pay_line = tr(self.lang, "pay_mpesa" if can_prompt(b.guest.phone) else "pay_card")
        return end(tr(self.lang, "held", name=unit.name, total=b.total, pay=pay_line), self.lang)

    def prices(self):
        from apps.bookings.models import Addon
        from apps.properties.models import Unit
        from apps.properties.services import from_price

        units = Unit.objects.filter(status="active").select_related("area")[:5]
        bf = Addon.objects.filter(code="breakfast", active=True).first()
        items = "; ".join(
            tr(self.lang, "price_item", name=u.name, area=u.area.name, price=from_price(u)) for u in units
        )
        self.save(step="after_prices")
        return ask(tr(self.lang, "prices", list=items, bf=bf.price if bf else 0), self.lang)

    def guide(self):
        """Three local favourites read out (closest to the caller's booking first); the full list follows by SMS."""
        from apps.guide import services as guide

        b = bookings.current_booking(self.phone)
        origin = guide.origin_of(b.unit) if b else None
        picks = guide.top_picks(origin, limit=6)
        self.save(step="after_guide")
        if not picks:
            return ask(tr(self.lang, "guide_none"), self.lang)
        guide.send_list(self.phone, "top", picks, self.lang)
        items = " ".join(
            tr(self.lang, "guide_item", name=p.name, summary=p.summary_in(self.lang).rstrip(".")) for p in picks[:3]
        )
        return ask(tr(self.lang, "guide", items=items), self.lang)

    def step_after_guide(self):
        return self.main_menu()

    def step_complaint(self):
        return end(tr(self.lang, "complaint_done"), self.lang)

    def step_after_prices(self):
        if self.d == "1":
            self.save(step="when")
            return ask(tr(self.lang, "when"), self.lang)
        return self.main_menu()

    def my_booking(self):
        b = bookings.current_booking(self.phone)
        if not b:
            self.save(step="after_prices")
            return ask(tr(self.lang, "no_booking"), self.lang)
        self.save(step="booking", ref=b.ref)
        head = tr(
            self.lang,
            "booking",
            unit=b.unit.name,
            check_in=_speak_date(b.check_in, self.lang),
            check_out=_speak_date(b.check_out, self.lang),
            ref=spoken_digits(b.ref),
            status=b.get_status_display(),
        )
        if b.status in ("confirmed", "checked_in"):
            return ask(head + tr(self.lang, "booking_opts"), self.lang)
        return end(head, self.lang)

    def step_booking(self):
        from apps.bookings.models import Booking

        b = Booking.objects.filter(ref=self.st.get("ref")).select_related("unit", "unit__area").first()
        if not b:
            return self.main_menu()
        if self.d == "1":
            # like the trip page and USSD: directions and Wi-Fi open 48 h before check-in, on every channel
            if not bookings.details_visible(b):
                return end(tr(self.lang, "directions_early", unit=b.unit.name, area=b.unit.area.name), self.lang)
            bookings.send_guest(b, "directions")
            return end(
                tr(
                    self.lang,
                    "directions",
                    unit=b.unit.name,
                    directions=b.unit.directions,
                    landmark=b.unit.landmark or b.unit.area.name,
                ),
                self.lang,
            )
        if self.d == "2":
            if b.status == "checked_in":
                bookings.send_guest(b, "checkin_code")
                return end(tr(self.lang, "code_sent"), self.lang)
            return end(tr(self.lang, "code_later", check_in=_speak_date(b.check_in, self.lang)), self.lang)
        return self.main_menu()

    def step_ask(self):
        s = SiteSettings.load()
        if self.d == "1":
            self.save(step="live", dialed_host=True)
            return dial(tr(self.lang, "connecting"), [s.host_contact, s.backup_phone], self.lang)
        if self.d == "2":
            self.save(step="record")
            return record_msg(self.lang)
        return ask(tr(self.lang, "invalid") + " " + tr(self.lang, "ask"), self.lang)

    def step_welcome(self):
        from apps.bookings.models import Booking

        b = Booking.objects.filter(ref=self.st.get("ref")).select_related("unit").first()
        if b and self.d == "1":
            return end(
                tr(
                    self.lang,
                    "directions",
                    unit=b.unit.name,
                    directions=b.unit.directions,
                    landmark=b.unit.landmark or b.unit.area.name,
                ),
                self.lang,
            )
        if self.d == "2":
            return self.step_ask_connect()
        return end(tr(self.lang, "recorded"), self.lang)

    def step_ask_connect(self):
        s = SiteSettings.load()
        self.save(step="live", dialed_host=True)
        return dial(tr(self.lang, "connecting"), [s.host_contact], self.lang)

    def step_done(self):
        return end(tr(self.lang, "recorded"), self.lang)

    def step_record(self):
        # Africa's Talking posts the recording to the Record callbackUrl: thank the caller, don't replay the menu
        return end(tr(self.lang, "recorded"), self.lang)


# ---------- outbound: support call-backs and escalations ----------


def support_call(session, digits):
    """'bridge': Amina asked to call a guest back - when she picks up she hears who it is and is connected.
    'ticket': a request nobody has answered - press 1 to call the guest now."""
    from apps.support import services as support
    from apps.support.models import Ticket

    st = session.state
    t = Ticket.objects.filter(pk=st.get("ticket_id")).select_related("guest").first()
    if t is None:
        return end(tr("en", "call_gone"))
    if st.get("purpose") == "bridge" or digits == "1":
        support.bridge_answered(t)
        session.state = {**st, "connected": True}
        session.save(update_fields=["state"])
        prompt = support.bridge_prompt(t) if st.get("purpose") == "bridge" else tr("en", "call_connect")
        return dial(prompt, [t.phone])
    if t.status not in support.OPEN:
        return end(tr("en", "call_handled"))
    return ask(support.alert_prompt(t), "en", no_input=tr("en", "call_bye"))


def _support_call_ended(session, data):
    from apps.support import services as support
    from apps.support.models import Ticket

    if session.session_id and not OnceMarker.mark(f"voice-support-ended:{session.session_id}"):
        return
    st = session.state
    t = Ticket.objects.filter(pk=st.get("ticket_id")).first()
    if t is not None:
        support.call_finished(
            t,
            answered=not _unanswered(data),
            talked_seconds=int(float(data.get("dialDurationInSeconds") or 0)),
            purpose=st.get("purpose", "bridge"),
        )


# ---------- outbound: Amina's safety call ----------


def alert_call(session, digits):
    from apps.safety.models import Alert
    from apps.safety.services import acknowledge, describe

    st = session.state
    alert = (
        Alert.objects.filter(pk=st.get("alert_id")).first()
        or Alert.objects.filter(status="open", kind="sos").order_by("-id").first()
    )
    if not alert:
        return end(T["en"]["alert_none"])
    if digits == "1":
        acknowledge(alert)
        return dial(T["en"]["alert_connect"], [alert.phone])
    session.state = {**st, "alert_id": alert.pk, "step": "alert"}
    session.save(update_fields=["state"])
    _, _, who, where = describe(alert.phone)
    who = who.replace(alert.phone, spoken_digits(alert.phone))
    return ask(T["en"]["alert"].format(who=who, where=where), "en", no_input=T["en"]["alert_bye"])


def place_welcome_call(booking):
    """Optional voice walkthrough on arrival day (Kenyan numbers; needs a live AT voice number)."""
    from . import at

    try:
        res = at.voice_call(booking.guest.phone, client_request_id=f"welcome-{booking.ref}")
    except Exception as e:
        log.warning("welcome call failed: %s", e)
        return None
    for entry in res.get("entries") or []:
        if sid := _placed(entry):
            VoiceSession.objects.update_or_create(
                session_id=sid,
                defaults={
                    "phone": booking.guest.phone,
                    "direction": "outbound",
                    "state": {"purpose": "welcome", "ref": booking.ref, "lang": booking.lang},
                },
            )
    return res


def register_outbound(res, purpose, **state):
    for entry in (res or {}).get("entries") or []:
        if sid := _placed(entry):
            VoiceSession.objects.update_or_create(
                session_id=sid,
                defaults={
                    "phone": entry.get("phoneNumber", ""),
                    "direction": "outbound",
                    "state": {"purpose": purpose, **state},
                },
            )


def _placed(entry):
    """The sessionId of a call Africa's Talking queued. A call it couldn't place has another status and sessionId
    "None" (a string), which must never become a session."""
    sid = str(entry.get("sessionId") or "")
    return sid if entry.get("status") == "Queued" and sid not in ("", "None") else None


# ---------- end of call ----------


def call_ended(session, data):
    from apps.safety.services import escalate

    st = session.state
    session.ended_at = timezone.now()
    session.duration_seconds = int(float(data.get("durationInSeconds") or 0))
    session.hangup_cause = (data.get("hangupCause") or "")[:40]
    session.save(update_fields=["ended_at", "duration_seconds", "hangup_cause"])
    if session.direction == "outbound":
        if st.get("purpose") in ("bridge", "ticket"):
            _support_call_ended(session, data)
        elif _unanswered(data):
            _missed_outbound(session, data)
        return
    if not st.get("dialed_host"):
        return
    if int(float(data.get("dialDurationInSeconds") or 0)) > 0:
        return
    phone, lang = session.phone, st.get("lang", "en")
    s = SiteSettings.load()
    if st.get("step") == "help":
        from apps.safety.models import Alert
        from apps.safety.services import recall

        alert = Alert.objects.filter(pk=st.get("alert_id")).first()
        if alert is not None and alert.status != "open":
            return  # Amina has already acknowledged it
        if alert is not None:
            recall(alert)  # Amina didn't pick up the bridged call: ring her phone now, same emergency
        else:
            escalate(phone, "voice-missed")
        messaging.send(
            phone,
            "Amina didn't answer yet - we're calling her again now. If you are in danger call 999 or 112."
            if lang != "sw"
            else "Amina hajajibu bado - tunampigia tena sasa. Ukiwa hatarini piga 999 au 112.",
            kind="sos",
        )
    else:
        from apps.support.services import open_ticket

        t = open_ticket(  # on the support desk with a reply-by time, and a Call button that connects them
            phone,
            category="callback",
            subject="Called and couldn't reach Amina",
            channel="voice",
            ack=False,
            tell_host=False,
        )
        messaging.send(
            s.host_contact,
            f"Missed call from guest {phone} who wanted to talk ({t.ref}). Please call back - reply CALL {t.ref} to be connected.",
            kind="missed_call",
        )
        messaging.send(
            phone,
            "Amina couldn't pick up just now. Text your question to this number and she'll reply here."
            if lang != "sw"
            else "Amina hakuweza kupokea sasa. Tuma swali lako kwa ujumbe na atakujibu.",
            kind="missed_call",
        )


# Africa's Talking's last notification for an outbound call that nobody picked up: callSessionState NotAnswered
# (Expired once its 6 hours of retries run out) and/or a hangupCause other than NORMAL_CLEARING.
UNANSWERED_STATES = {"NotAnswered", "Busy", "Failed", "Expired"}
UNANSWERED_CAUSES = {
    "NO_ANSWER",
    "USER_BUSY",
    "CALL_REJECTED",
    "NO_USER_RESPONSE",
    "SUBSCRIBER_ABSENT",
    "UNALLOCATED_NUMBER",
    "NORMAL_TEMPORARY_FAILURE",
    "RECOVERY_ON_TIMER_EXPIRE",
    "SERVICE_UNAVAILABLE",
    "USER_NOT_REGISTERED",
}


def _unanswered(data):
    state = str(data.get("callSessionState") or "")
    cause = str(data.get("hangupCause") or "").upper()
    return state in UNANSWERED_STATES or cause in UNANSWERED_CAUSES


def _missed_outbound(session, data):
    """A call we placed wasn't answered. An SOS call climbs the escalation ladder now instead of waiting for the
    3-minute timer; the arrival welcome call becomes a welcome SMS (once)."""
    if session.session_id and not OnceMarker.mark(f"voice-unanswered:{session.session_id}"):
        return  # the same final notification, delivered twice
    st = session.state
    why = data.get("callSessionState") or data.get("hangupCause") or "not answered"
    if st.get("purpose") == "alert":
        from apps.safety.models import Alert
        from apps.safety.services import call_next

        alert = Alert.objects.filter(pk=st.get("alert_id")).first()
        if alert is not None:
            call_next(alert, why=f"call not answered ({why})")
    elif st.get("purpose") == "welcome":
        from apps.bookings.models import Booking

        b = Booking.objects.filter(ref=st.get("ref")).select_related("guest", "unit", "unit__area").first()
        if b is not None and OnceMarker.mark(f"welcome-call-missed:{b.ref}"):
            bookings.send_guest(b, "welcome_call_missed")
            bookings.event(b, "welcome_call", f"Welcome call not answered ({why}) - welcome SMS sent instead")


def voicemail(session, url):
    if session.state.get("voicemail_sent"):
        return
    session.state = {**session.state, "voicemail_sent": True}
    session.save(update_fields=["state"])
    b = bookings.current_booking(session.phone)
    msg = messaging.record_inbound(session.phone, f"[voicemail] {url}", channel="voice", booking=b)
    messaging.mark(msg, "relayed", "voicemail")
    messaging.send(
        SiteSettings.load().host_contact,
        f"Voicemail from {session.phone}{' (' + b.ref + ')' if b else ''}: {url}",
        kind="voicemail",
    )


def voice_complaint(session, url):
    """A complaint left after pressing 5: a support ticket with the recording, and its reference by SMS."""
    from apps.support.services import open_ticket

    if session.state.get("complaint_logged"):
        return
    session.state = {**session.state, "complaint_logged": True}
    session.save(update_fields=["state"])
    open_ticket(
        session.phone,
        category="complaint",
        subject="Voice complaint - listen to the recording",
        description="Left by phone (option 5).",
        channel="voice",
        recording_url=url,
    )


def _placed_for(client_request_id):
    """Our outbound calls carry clientRequestId 'alert-<alert id>' (SOS) or 'welcome-<booking ref>'."""
    kind, _, key = str(client_request_id or "").partition("-")
    if kind == "alert" and key.isdigit():
        return {"purpose": "alert", "alert_id": int(key)}
    if kind in ("bridge", "ticket") and key.isdigit():
        return {"purpose": kind, "ticket_id": int(key), "lang": "en"}
    if kind == "welcome" and key:
        from apps.bookings.models import Booking

        lang = Booking.objects.filter(ref=key).values_list("lang", flat=True).first()
        return {"purpose": "welcome", "ref": key, "lang": lang or "en"}
    return None


def _their_number(data, outbound):
    """The other party on the call. Africa's Talking documents callerNumber as the phone user and destinationNumber as
    our number, so rather than trust the direction take whichever one isn't AT_VOICE_NUMBER (the direction decides
    only when neither number is ours)."""
    caller, destination = (
        normalize_phone(data.get(k)) or data.get(k) or "" for k in ("callerNumber", "destinationNumber")
    )
    ours = normalize_phone(settings.AT_VOICE_NUMBER)
    if ours and ours in (caller, destination):
        return destination if caller == ours else caller
    return destination if outbound else caller


def handle(data):
    """Entry point for the AT voice callback. Returns XML (or '' for the final notification)."""
    sid = data.get("sessionId") or ""
    outbound = (data.get("direction") or "").lower() == "outbound"
    phone = _their_number(data, outbound)
    session, created = VoiceSession.objects.get_or_create(
        session_id=sid, defaults={"phone": phone or "", "direction": "outbound" if outbound else "inbound"}
    )
    if created and outbound and (state := _placed_for(data.get("clientRequestId"))):
        session.state = state  # a call we placed that wasn't pre-registered (e.g. it was never answered)
        session.save(update_fields=["state"])
    if not session.phone and phone:
        session.phone = phone
        session.save(update_fields=["phone"])
    digits = (data.get("dtmfDigits") or "").strip()

    if data.get("recordingUrl") and session.state.get("step") == "record":
        voicemail(session, data["recordingUrl"])
    elif data.get("recordingUrl") and session.state.get("step") == "complaint":
        voice_complaint(session, data["recordingUrl"])
    if str(data.get("isActive")) == "0":
        call_ended(session, data)
        return ""
    purpose = session.state.get("purpose")
    if outbound or purpose == "alert":
        if purpose == "welcome":
            from apps.bookings.models import Booking

            b = Booking.objects.filter(ref=session.state.get("ref")).select_related("guest", "unit").first()
            if not digits and b:
                session.state = {**session.state, "step": "welcome"}
                session.save(update_fields=["state"])
                return ask(tr(b.lang, "welcome_call", name=first_name(b.guest.name), unit=b.unit.name), b.lang)
            return Call(session, session.phone, digits).handle()
        if purpose in ("bridge", "ticket"):
            return support_call(session, digits)
        return alert_call(session, digits)
    return Call(session, phone, digits).handle()
