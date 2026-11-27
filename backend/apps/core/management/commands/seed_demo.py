"""python manage.py seed_demo [--reset]

Builds a realistic Amina Stays: 6 homes, staff, 150 days of history across every channel, guests
in-house right now, arrivals, requests waiting for Amina, inbox threads, tasks and an Airbnb iCal
feed, plus the local guide, support tickets, service alerts and rewards. Seeded people are tagged
'seed' and never receive real SMS, airtime or data (see messaging.dispatch, rewards.dispatch)."""

import random
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings import locks
from apps.bookings.models import (
    ACTIVE_STATUSES,
    AccessCode,
    Addon,
    Booking,
    BookingAddon,
    BookingEvent,
    BookingGuest,
    Waitlist,
)
from apps.core import seed_data as D
from apps.core.models import Activity, SiteSettings
from apps.core.utils import at_local, normalize_phone, same_phone, today
from apps.messaging.automations import ensure_defaults
from apps.messaging.models import FAQ, Message, Thread
from apps.operations.models import Task
from apps.payments.models import Payment, Refund
from apps.properties.models import Amenity, Area, CalendarBlock, ICalFeed, PriceRule, Unit, UnitPhoto
from apps.properties.services import quote, sync_feed
from apps.reviews.models import Review
from apps.safety.models import Alert


def sample_ics(unit_slug, ref=None):
    t = ref or today()
    events = [(14, 17, "Airbnb (HMQ4X2)"), (30, 34, "Airbnb (HM8K1P)")]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Airbnb Inc//Hosting Calendar 1.0//EN"]
    for start, end, summary in events:
        a, b = t + timedelta(days=start), t + timedelta(days=end)
        lines += [
            "BEGIN:VEVENT",
            f"DTSTART;VALUE=DATE:{a:%Y%m%d}",
            f"DTEND;VALUE=DATE:{b:%Y%m%d}",
            f"UID:{unit_slug}-{start}@airbnb.com",
            f"SUMMARY:{summary}",
            "END:VEVENT",
        ]
    return "\r\n".join(lines + ["END:VCALENDAR"]) + "\r\n"


class Command(BaseCommand):
    help = "Seed Amina Stays with realistic demo data."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Wipe ALL data first")

    def handle(self, *args, **opts):
        if opts["reset"]:
            call_command("flush", interactive=False, verbosity=0)
        elif Unit.objects.exists():
            self.stdout.write("Already seeded. Use --reset to start over.")
            return
        self.rng = random.Random(2026)
        self.t = today()
        with transaction.atomic():
            self.settings()
            self.people()
            self.catalogue()
            self.history()
            self.current()
            self.extras()
            self.addons()
            simulator = self.simulator_guests()
        n = {m.__name__: m.objects.count() for m in (Unit, Booking, Review, Message, Task)}
        self.stdout.write(self.style.SUCCESS(f"Seeded: {n}"))
        self.stdout.write(
            f"Host console login: {settings.AMINA_PHONE} (OTP code is printed in the server log / shown in DEMO mode)"
        )
        for line in simulator:
            self.stdout.write(f"Simulator guest {line}")

    def addons(self):
        """The local guide, support desk, service alerts and rewards (rewards first: they mark past stays as
        already rewarded, so the scheduler never texts seeded guests about old stays)."""
        from apps.guide.seed import seed as guide
        from apps.notices.seed import seed as notices
        from apps.rewards.seed import seed as rewards
        from apps.support.seed import seed as support

        guide()
        rewards()
        support()
        notices()

    # ---------- setup ----------
    def settings(self):
        s = SiteSettings.load()
        s.business_name, s.host_name, s.host_phone = "Amina Stays", "Amina", settings.AMINA_PHONE
        s.backup_phone = "+254700000012"
        s.support_email = "karibu@aminastays.co.ke"
        s.tra_licence_number = "TRA/A/MSA/2026/0417"
        s.tra_licence_expiry = self.t.replace(month=12, day=31)
        s.odpc_registration = "ODPC/DC/2026/1189"
        s.save()

    def people(self):
        self.owner, _ = User.objects.update_or_create(
            phone=settings.AMINA_PHONE,
            defaults={"name": "Amina Mohamed", "role": "owner", "lang": "en", "is_staff": True, "nationality": "KE"},
        )
        self.staff = {}
        for name, phone, role, lang in D.STAFF:
            u, _ = User.objects.update_or_create(
                phone=phone, defaults={"name": name, "role": role, "lang": lang, "tags": ["seed"], "nationality": "KE"}
            )
            self.staff[role] = u
        self.guests = []
        for name, phone, country, lang in D.GUESTS:
            u, _ = User.objects.update_or_create(
                phone=phone,
                defaults={
                    "name": name,
                    "nationality": country,
                    "lang": lang,
                    "tags": ["seed"],
                    "first_channel": "web" if country != "KE" else self.rng.choice(["ussd", "sms", "web", "voice"]),
                },
            )
            if self.rng.random() < 0.8:
                u.set_id_number(f"{'P' if country != 'KE' else ''}{self.rng.randint(10_000_000, 39_999_999)}")
                u.id_type = "national_id" if country == "KE" else "passport"
                u.id_submitted_at = u.consent_at = timezone.now() - timedelta(days=self.rng.randint(5, 140))
                u.save()
            self.guests.append(u)
        self.by_name = {g.name: g for g in self.guests}

    def catalogue(self):
        self.areas = {}
        for i, a in enumerate(D.AREAS):
            self.areas[a["slug"]] = Area.objects.create(
                name=a["name"],
                slug=a["slug"],
                summary=a["summary"],
                description=a["description"],
                photo_url=a["photo"],
                latitude=a["lat"],
                longitude=a["lng"],
                getting_there=a["getting_there"],
                tips=a["tips"],
                sort_order=i,
            )
        amen = {}
        for i, (code, name, icon, cat) in enumerate(D.AMENITIES):
            amen[code] = Amenity.objects.create(code=code, name=name, icon=icon, category=cat, sort_order=i)
        self.units = {}
        for i, u in enumerate(D.UNITS):
            unit = Unit.objects.create(
                name=u["name"],
                area=self.areas[u["area"]],
                property_type=u["property_type"],
                summary=u["summary"],
                description=u["description"],
                the_space=u["the_space"],
                guest_access=u["guest_access"],
                neighbourhood=u["neighbourhood"],
                bedrooms=u["bedrooms"],
                beds=u["beds"],
                bathrooms=u["bathrooms"],
                max_guests=u["max_guests"],
                size_sqm=u["size_sqm"],
                sleeping=u["sleeping"],
                base_price=u["base_price"],
                weekend_price=u["weekend_price"],
                cleaning_fee=u["cleaning_fee"],
                weekly_discount=u["weekly_discount"],
                monthly_discount=u["monthly_discount"],
                min_nights=u["min_nights"],
                cancellation_policy=u["cancellation_policy"],
                latitude=u["lat"],
                longitude=u["lng"],
                address=u["address"],
                directions=u["directions"],
                landmark=u["landmark"],
                map_link=f"https://maps.google.com/?q={u['lat']},{u['lng']}",
                wifi_name=u["wifi_name"],
                wifi_password=u["wifi_password"],
                access_method=u["access_method"],
                parking=u["parking"],
                house_rules=D.STD_RULES,
                safety_features=D.STD_SAFETY,
                house_manual=u["house_manual"],
                local_tips=u.get("local_tips", ""),
                highlights=u["highlights"],
                tags=u["tags"],
                is_featured=u["is_featured"],
                sort_order=i,
            )
            unit.amenities.set([amen[c] for c in u["amenities"] if c in amen])
            for j, (pid, room, caption) in enumerate(u["photos"]):
                UnitPhoto.objects.create(unit=unit, url=D.ph(pid), room=room, caption=caption, sort_order=j)
            self.units[u["name"]] = unit
        for i, a in enumerate(D.ADDONS):
            Addon.objects.create(
                code=a["code"],
                name=a["name"],
                category=a["category"],
                icon=a["icon"],
                photo_url=D.ph(a["photo"], 1200) if a.get("photo") else "",
                price=a["price"],
                pricing=a["pricing"],
                short=a.get("short", ""),
                description=a.get("description", ""),
                requires_approval=a.get("requires_approval", False),
                options=a.get("options", {}),
                sort_order=i,
            )
        y = self.t.year if self.t.month > 1 else self.t.year - 1  # the festive season that is next / in progress
        rules = [
            ("Festive season", "season", f"{y}-12-18", f"{y + 1}-01-03", 35, 30),
            ("High season (Jan-Mar)", "season", f"{y + 1}-01-04", f"{y + 1}-03-31", 15, 10),
            ("Easter weekend", "season", f"{y + 1}-03-25", f"{y + 1}-03-29", 20, 40),
            ("Long rains (low season)", "season", f"{y + 1}-04-12", f"{y + 1}-06-15", -15, 10),
            ("August peak", "season", f"{y + 1}-07-15", f"{y + 1}-08-31", 15, 10),
        ]
        for name, kind, start, end, value, prio in rules:
            PriceRule.objects.create(
                name=name, kind=kind, start_date=start, end_date=end, adjust_type="percent", value=value, priority=prio
            )
        PriceRule.objects.create(
            name="Last-minute deal", kind="last_minute", days_before=2, adjust_type="percent", value=-15
        )
        PriceRule.objects.create(name="Early bird", kind="early_bird", days_before=90, adjust_type="percent", value=-5)
        for i, (cat, q, kw, en, sw) in enumerate(D.FAQS):
            FAQ.objects.create(category=cat, question=q, keywords=kw, answer_en=en, answer_sw=sw, sort_order=i)
        ensure_defaults()
        for role in ("cleaner", "caretaker", "cook", "security"):
            self.staff[role].assigned_units.set(list(self.units.values()))

    # ---------- helpers ----------
    def _event(self, b, kind, text, at, channel=""):
        e = BookingEvent.objects.create(booking=b, kind=kind, text=text, channel=channel)
        BookingEvent.objects.filter(pk=e.pk).update(created_at=at)

    def _msg(
        self, phone, direction, body, at, booking=None, sender=None, kind="", handled="na", channel="sms", status=None
    ):
        thread, _ = Thread.objects.get_or_create(
            phone=phone, defaults={"guest": User.objects.filter(phone=phone).first()}
        )
        m = Message.objects.create(
            thread=thread,
            phone=phone,
            booking=booking,
            direction=direction,
            channel=channel,
            body=body,
            kind=kind,
            handled=handled,
            sender=sender or ("guest" if direction == "in" else "system"),
            status=status or ("received" if direction == "in" else "delivered"),
            sent_at=at if direction == "out" else None,
            delivered_at=at if direction == "out" else None,
        )
        Message.objects.filter(pk=m.pk).update(created_at=at)
        Thread.objects.filter(pk=thread.pk).update(last_message_at=at, last_preview=body[:160])
        return m

    def _booking(
        self,
        unit,
        guest,
        ci,
        co,
        *,
        status,
        channel,
        created,
        adults=2,
        breakfast=None,
        plan="full",
        paid=None,
        method=None,
    ):
        q = quote(
            unit,
            ci,
            co,
            guests=adults,
            ref_today=created.date() if hasattr(created, "date") else created,
            addons=[{"addon": self.breakfast, "quantity": adults}] if breakfast else None,
            payment_plan=plan,
        )
        b = Booking.objects.create(
            ref=Booking.new_ref(),
            unit=unit,
            guest=guest,
            check_in=ci,
            check_out=co,
            adults=adults,
            status=status,
            channel=channel,
            lang=guest.lang,
            nightly=q["nightly"],
            accommodation_amount=q["accommodation"],
            discount_amount=q["discount"],
            cleaning_fee=q["cleaning_fee"],
            addons_amount=q["addons"],
            levy_amount=q["levy"],
            vat_amount=q["vat"],
            total=q["total"],
            payment_plan=plan,
            amount_due_now=q["due_now"] if plan == "deposit" else q["total"],
            cancellation_policy=unit.cancellation_policy,
        )
        Booking.objects.filter(pk=b.pk).update(created_at=created)
        b.refresh_from_db()
        if breakfast:
            BookingAddon.objects.create(
                booking=b,
                addon=self.breakfast,
                quantity=adults,
                unit_price=self.breakfast.price,
                total=self.breakfast.price_for(b.nights, adults, adults),
                status="confirmed",
                details={"style": breakfast, "dietary": "", "time": "08:00"},
            )
        BookingGuest.objects.create(
            booking=b,
            full_name=guest.name,
            id_type=guest.id_type,
            id_number_enc=guest.id_number_enc,
            id_last4=guest.id_last4,
            nationality=guest.nationality,
            is_lead=True,
        )
        if adults > 1 and guest.nationality != "KE":
            BookingGuest.objects.create(
                booking=b, full_name=f"Travel companion of {guest.name.split(' ')[0]}", nationality=guest.nationality
            )
        amount = (b.amount_due_now if plan == "deposit" else b.total) if paid is None else paid
        if amount:
            method = method or ("mpesa" if guest.phone.startswith("+254") else "card")
            p = Payment.objects.create(
                booking=b,
                amount=amount,
                method=method,
                purpose="deposit" if amount < b.total else "full",
                status="success",
                phone=guest.phone,
                provider="simulate",
                transaction_id=f"SEED-{b.ref}-{amount}",
                provider_ref=("Q" if method == "mpesa" else "AUTH") + f"{self.rng.randint(10**7, 10**8 - 1)}",
                completed_at=created + timedelta(minutes=2),
            )
            Payment.objects.filter(pk=p.pk).update(created_at=created + timedelta(minutes=1))
            b.amount_paid = amount
            b.payment_status = "paid" if amount >= b.total else "deposit_paid"
            b.save(update_fields=["amount_paid", "payment_status"])
        label = dict(Booking.CHANNELS)[channel]
        self._event(b, "held", f"Held via {label} for 10 minutes", created, channel)
        if amount:
            self._event(
                b,
                "payment",
                f"{'M-Pesa' if (method or '') == 'mpesa' else 'Card'} payment received: KES {amount:,}",
                created + timedelta(minutes=2),
            )
            self._event(
                b,
                "confirmed",
                "Booking confirmed - door code generated (sent on arrival day)",
                created + timedelta(minutes=2),
            )
        return b

    # ---------- history ----------
    def history(self):
        self.breakfast = Addon.objects.get(code="breakfast")
        kenyans = [g for g in self.guests if g.nationality == "KE"]
        foreigners = [g for g in self.guests if g.nationality != "KE"]
        favourites = {"Diani Palm Suite", "Blue Reef Apartment", "Bamburi Family House"}
        for unit in self.units.values():
            weights = [(5, 92), (4, 7), (3, 1)] if unit.name in favourites else [(5, 70), (4, 24), (3, 4), (2, 2)]
            d = self.t - timedelta(days=150)
            while True:
                d += timedelta(days=self.rng.choice([0, 0, 1, 1, 2, 3, 4, 6, 9]))
                nights = max(unit.min_nights, self.rng.choice([1, 2, 2, 3, 3, 4, 5, 7]))
                ci, co = d, d + timedelta(days=nights)
                if co >= self.t - timedelta(days=2):
                    break
                local = self.rng.random() < 0.45
                guest = self.rng.choice(kenyans if local else foreigners)
                channel = self.rng.choices(
                    ["web", "ussd", "sms", "voice", "walk_in"], [20, 30, 28, 15, 7] if local else [80, 0, 12, 3, 5]
                )[0]
                lead = self.rng.choice([0, 1, 2, 4, 7, 14, 21, 30, 45, 60])
                created = timezone.make_aware(datetime.combine(ci - timedelta(days=lead), time.min)) + timedelta(
                    hours=self.rng.randint(7, 21), minutes=self.rng.randint(0, 59)
                )
                adults = min(unit.max_guests, self.rng.choice([1, 2, 2, 2, 3, 4]))
                cancelled = self.rng.random() < 0.06
                b = self._booking(
                    unit,
                    guest,
                    ci,
                    co,
                    status="cancelled" if cancelled else "completed",
                    channel=channel,
                    created=created,
                    adults=adults,
                    breakfast=self.rng.choice(["swahili", "continental", None, None])
                    if unit.breakfast_available
                    else None,
                )
                if cancelled:
                    refund = b.amount_paid
                    Refund.objects.create(
                        booking=b,
                        amount=refund,
                        method="mpesa_b2c" if guest.phone.startswith("+254") else "card",
                        status="success",
                        reason="Cancelled by guest",
                        completed_at=created + timedelta(days=1),
                    )
                    Booking.objects.filter(pk=b.pk).update(
                        amount_refunded=refund,
                        payment_status="refunded",
                        cancelled_by="guest",
                        cancelled_at=created + timedelta(days=1),
                    )
                    self._event(b, "cancelled", "Cancelled by guest", created + timedelta(days=1))
                else:
                    arrive = at_local(ci, "14:00") + timedelta(minutes=self.rng.randint(0, 300))
                    leave = at_local(co, "10:00") + timedelta(minutes=self.rng.randint(0, 80))
                    Booking.objects.filter(pk=b.pk).update(
                        code_released_at=at_local(ci, "08:00"),
                        checked_in_at=at_local(ci, "08:00"),
                        checked_out_at=leave,
                    )
                    AccessCode.objects.create(
                        booking=b,
                        code=f"{self.rng.randint(100000, 999999)}",
                        provider="simulated",
                        valid_from=at_local(ci, "13:00"),
                        valid_until=at_local(co, "11:30"),
                        sent_at=at_local(ci, "08:00"),
                        revoked_at=leave,
                        revoke_reason="checked_out",
                        last_used_at=arrive,
                    )
                    self._event(b, "code_released", "Door code released by SMS", at_local(ci, "08:00"))
                    self._event(
                        b,
                        "checked_out",
                        f"Checked out via {self.rng.choice(['sms', 'web', 'ussd'])} - code deactivated",
                        leave,
                    )
                    if self.rng.random() < 0.78:
                        rating = self.rng.choices([w[0] for w in weights], [w[1] for w in weights])[0]
                        cats = {
                            c: max(1, min(5, rating + self.rng.choice([0, 0, 0, 1, -1])))
                            for c in ("cleanliness", "accuracy", "check_in", "communication", "location", "value")
                        }
                        r = Review.objects.create(
                            booking=b,
                            unit=unit,
                            guest=guest,
                            rating=rating,
                            comment=self.rng.choice(D.REVIEW_COMMENTS[rating]),
                            channel=self.rng.choice(["sms", "web"]),
                            **cats,
                            host_response="Asante sana! Karibu tena anytime."
                            if rating >= 4 and self.rng.random() < 0.4
                            else "",
                        )
                        Review.objects.filter(pk=r.pk).update(
                            created_at=leave + timedelta(hours=self.rng.randint(2, 30))
                        )
                d = co

    # ---------- right now ----------
    def current(self):
        t, now = self.t, timezone.now()
        U, G = self.units, self.by_name

        def ago(days=0, hours=0):
            return now - timedelta(days=days, hours=hours)

        # A — Giulia (Italy) in-house at Diani, breakfast booked
        a = self._booking(
            U["Diani Palm Suite"],
            G["Giulia Rossi"],
            t - timedelta(days=1),
            t + timedelta(days=2),
            status="checked_in",
            channel="web",
            created=ago(days=12),
            adults=2,
            breakfast="swahili",
        )
        self._release(a, t - timedelta(days=1))
        # B — Wanjiku (Kenya, Kiswahili) booked by USSD, in-house at Blue Reef since this morning
        b = self._booking(
            U["Blue Reef Apartment"],
            G["Wanjiku Kamau"],
            t,
            t + timedelta(days=3),
            status="checked_in",
            channel="ussd",
            created=ago(days=4),
            adults=3,
        )
        self._release(b, t)
        # C — Hans (Germany) arrives today, ID missing so the code is waiting on the guest register
        hans = G["Hans Müller"]
        hans.id_type, hans.id_number_enc, hans.id_last4, hans.id_submitted_at = "", "", "", None
        hans.save()
        c = self._booking(
            U["Old Town Loft"],
            hans,
            t,
            t + timedelta(days=2),
            status="confirmed",
            channel="web",
            created=ago(days=20),
            adults=1,
        )
        BookingGuest.objects.filter(booking=c).update(id_type="", id_number_enc="", id_last4="")
        locks.create_code(c)
        # D — Sarah (UK) arrives tomorrow, paid a deposit, asked for early check-in
        d = self._booking(
            U["Bamburi Family House"],
            G["Sarah Thompson"],
            t + timedelta(days=1),
            t + timedelta(days=5),
            status="confirmed",
            channel="web",
            created=ago(days=9),
            adults=4,
            plan="deposit",
            breakfast="english",
        )
        d.arrival_mode, d.arrival_eta = "flight", "11:30"
        d.save(update_fields=["arrival_mode", "arrival_eta"])
        locks.create_code(d)
        early = BookingAddon.objects.create(
            booking=d,
            addon=Addon.objects.get(code="early_checkin"),
            quantity=1,
            unit_price=1500,
            total=1500,
            status="requested",
            details={"time": "11:00"},
        )
        pickup = Addon.objects.get(code="airport_pickup")
        BookingAddon.objects.create(
            booking=d,
            addon=pickup,
            quantity=1,
            unit_price=pickup.price,
            total=pickup.price,
            status="confirmed",
            details={"flight": "KQ612", "time": "10:40"},
        )
        from apps.bookings.services import recalc

        recalc(d)
        # E — Peter (Kenya) leaves today (auto-checkout fires after 11:30 if he forgets)
        e = self._booking(
            U["Nyali Breeze Studio"],
            G["Peter Njoroge"],
            t - timedelta(days=2),
            t,
            status="checked_in",
            channel="sms",
            created=ago(days=6),
            adults=1,
        )
        self._release(e, t - timedelta(days=2))
        # F..I — upcoming
        f = self._booking(
            U["Nyali Breeze Studio"],
            G["James Otieno"],
            t + timedelta(days=3),
            t + timedelta(days=5),
            status="confirmed",
            channel="voice",
            created=ago(days=1),
            adults=2,
        )
        g = self._booking(
            U["Mtwapa Creek Cottage"],
            G["Amélie Dubois"],
            t + timedelta(days=6),
            t + timedelta(days=10),
            status="confirmed",
            channel="web",
            created=ago(days=15),
            adults=2,
            breakfast="continental",
        )
        h = self._booking(
            U["Blue Reef Apartment"],
            G["Jessica Miller"],
            t + timedelta(days=12),
            t + timedelta(days=19),
            status="confirmed",
            channel="web",
            created=ago(days=30),
            adults=2,
        )
        i = self._booking(
            U["Diani Palm Suite"],
            G["Lukas Weber"],
            t + timedelta(days=24),
            t + timedelta(days=31),
            status="confirmed",
            channel="web",
            created=ago(days=40),
            adults=4,
            breakfast="swahili",
        )
        for bk in (f, g, h, i):
            locks.create_code(bk)
        Booking.objects.filter(pk=f.pk).update(risk_score=35, risk_flags=["last_minute", "new_guest"])

        # Waitlist
        Waitlist.objects.create(
            guest=G["Brian Kiprop"],
            area=self.areas["diani"],
            check_in=t + timedelta(days=26),
            check_out=t + timedelta(days=29),
            guests=2,
            channel="sms",
        )
        Waitlist.objects.create(
            guest=G["Mercy Achieng"],
            area=self.areas["nyali"],
            check_in=t + timedelta(days=2),
            check_out=t + timedelta(days=4),
            guests=2,
            channel="ussd",
        )

        # Conversations (one thread per guest, mixing channels)
        host = settings.AMINA_PHONE
        self._msg(
            G["Giulia Rossi"].phone,
            "out",
            "Booked! Diani Palm Suite, ... Ref " + a.ref,
            ago(days=12),
            a,
            kind="booking_confirmed",
        )
        self._msg(
            G["Giulia Rossi"].phone,
            "in",
            "What is the wifi password?",
            ago(hours=20),
            a,
            handled="auto",
            kind="faq:wifi",
        )
        self._msg(
            G["Giulia Rossi"].phone,
            "out",
            "Wi-Fi at Diani Palm Suite: DianiPalm / palm-4321-karibu",
            ago(hours=20),
            a,
            sender="bot",
            kind="faq:wifi",
        )
        self._msg(
            G["Giulia Rossi"].phone,
            "in",
            "The AC remote in the second bedroom isn't working",
            ago(hours=3),
            a,
            handled="auto",
            kind="issue",
        )
        gq = self._msg(
            G["Giulia Rossi"].phone,
            "in",
            "Ciao Amina! Could you book the sunset dhow cruise for tomorrow for 2 of us?",
            ago(hours=1),
            a,
            handled="relayed",
            kind="question",
        )
        self._msg(
            host,
            "out",
            f"#{gq.thread_id} Giulia Rossi [{a.ref} Diani Palm Suite]: Could you book the sunset dhow cruise for tomorrow for 2 of us?",
            ago(hours=1),
            a,
            kind="relay",
        )
        self._msg(
            G["Wanjiku Kamau"].phone,
            "out",
            "Karibu Blue Reef Apartment! Nambari ya mlango: ****** ...",
            ago(hours=4),
            b,
            kind="checkin_code",
        )
        wq = self._msg(
            G["Wanjiku Kamau"].phone,
            "in",
            "Habari Amina, tunaweza kupata mtu wa kutusaidia kubeba mizigo saa nane?",
            ago(hours=0.4),
            b,
            handled="relayed",
            kind="question",
        )
        self._msg(
            host,
            "out",
            f"#{wq.thread_id} Wanjiku Kamau [{b.ref} Blue Reef Apartment]: Habari Amina, tunaweza kupata mtu wa kutusaidia kubeba mizigo saa nane?",
            ago(hours=0.4),
            b,
            kind="relay",
        )
        self._msg(
            hans.phone,
            "out",
            "Kenias Tourismusregeln verlangen ein Gästeregister. Bitte trage deinen Pass vor der Ankunft ein...",
            ago(days=2),
            c,
            kind="id_request",
        )
        self._msg(
            hans.phone, "in", "Do I need to bring my passport?", ago(days=1), c, handled="auto", kind="faq:booking"
        )
        self._msg(
            hans.phone,
            "out",
            "Kenyan tourism regulations require a guest register for every stay. Your ID is encrypted...",
            ago(days=1),
            c,
            sender="bot",
            kind="faq:booking",
        )
        self._msg(
            G["Sarah Thompson"].phone,
            "in",
            "Hi! We land at 10:40 on KQ612 tomorrow - any chance of checking in early?",
            ago(hours=5),
            d,
            handled="auto",
            kind="early",
        )
        self._msg(
            G["Sarah Thompson"].phone,
            "out",
            "We've asked Amina about early check-in (from 11am). You'll hear back shortly.",
            ago(hours=5),
            d,
            sender="bot",
            kind="request_sent",
        )
        self._msg(
            host,
            "out",
            f"REQUEST #{early.pk}: Sarah Thompson ({d.ref}, Bamburi Family House) asks for Early check-in (from 11am) at 11:00. Reply YES {early.pk} or NO {early.pk}.",
            ago(hours=5),
            d,
            kind="addon_request",
        )
        Thread.objects.filter(pk__in=[gq.thread_id, wq.thread_id]).update(needs_reply=True, unread=1)
        Thread.objects.filter(pk=gq.thread_id).update(waiting_since=gq.created_at)
        Thread.objects.filter(pk=wq.thread_id).update(waiting_since=wq.created_at)

        # Tasks
        Task.objects.create(
            type="maintenance",
            title="AC: The AC remote in the second bedroom isn't working",
            category="ac",
            unit=a.unit,
            booking=a,
            priority="normal",
            assignee=self.staff["caretaker"],
            source="guest",
            due_at=now + timedelta(hours=3),
            description="Reported by SMS by Giulia Rossi",
        )
        Task.objects.create(
            type="inspection",
            title="Check the pool pump pressure",
            unit=U["Bamburi Family House"],
            priority="low",
            assignee=self.staff["caretaker"],
            due_at=now + timedelta(hours=20),
            source="host",
        )
        done = Task.objects.create(
            type="restock",
            title="Restock toiletries & drinking water",
            unit=U["Blue Reef Apartment"],
            status="done",
            assignee=self.staff["cleaner"],
            completed_at=ago(hours=26),
            source="host",
        )
        Task.objects.filter(pk=done.pk).update(created_at=ago(days=2))

        # Safety history (resolved), so the console shows the log without an open alarm
        sos = Alert.objects.create(
            kind="sos",
            severity="critical",
            status="resolved",
            source="sms",
            phone=G["Emma Clarke"].phone,
            guest=G["Emma Clarke"],
            summary="SOS from Emma Clarke (+447700900103), staying at Blue Reef Apartment - lift stuck during a power cut",
            call_status="Queued",
            calls_made=1,
            acknowledged_at=ago(days=18),
            resolved_at=ago(days=18),
            resolution_note="Generator restarted, guest out of the lift in 6 minutes",
        )
        Alert.objects.filter(pk=sos.pk).update(created_at=ago(days=18, hours=0.2))
        Activity.objects.create(kind="system", title="Demo data loaded", detail="Six homes, staff, 150 days of history")

    def _release(self, b, day):
        code = locks.create_code(b)
        released = at_local(day, "08:00")
        code.sent_at = released
        code.save(update_fields=["sent_at"])
        Booking.objects.filter(pk=b.pk).update(code_released_at=released, checked_in_at=released)
        self._event(b, "code_released", "Door code released by SMS", released)

    def extras(self):
        unit = self.units["Mtwapa Creek Cottage"]
        # Its stand-in Airbnb calendar is only served in DEMO mode, so otherwise import it once and leave it paused.
        feed = ICalFeed.objects.create(
            unit=unit,
            name="Airbnb",
            url=f"{settings.BACKEND_URL}/api/demo/ical/{unit.slug}.ics",
            active=settings.DEMO,
        )
        sync_feed(feed, text=sample_ics(unit.slug))

    # ---------- the presenter's phones in Africa's Talking's simulator ----------
    SIM_STAGES = {
        # stage: status, (from, to) days from today to try, guests, payment plan, channel, homes tried first
        "arriving": ("confirmed", [(2, 4), (1, 3), (3, 5)], 2, "full", "ussd", ["Diani Palm Suite", "Old Town Loft"]),
        "staying": ("checked_in", [(-1, 1), (0, 1), (-1, 2)], 2, "full", "sms", ["Mtwapa Creek Cottage"]),
        "upcoming": ("confirmed", [(5, 8), (6, 9), (7, 10), (4, 7)], 4, "deposit", "voice", ["Bamburi Family House"]),
        "returning": ("completed", [(-40, -37), (-45, -42), (-33, -30)], 2, "full", "ussd", ["Nyali Breeze Studio"]),
    }

    def simulator_guests(self, phones=None):
        """Make the phones used in Africa's Talking's simulator (SIMULATOR_GUESTS) real guests, each at another point
        of a stay (D.SIM_GUESTS): unlike the 'seed' people, their SMS really go out. A number that already has
        bookings keeps them. Returns a line per number."""
        host = SiteSettings.load().host_contact
        phones = list(settings.SIMULATOR_GUESTS if phones is None else phones)
        lines = [f"{p}: not used - only the first {len(D.SIM_GUESTS)} numbers are" for p in phones[len(D.SIM_GUESTS) :]]
        for raw, (name, lang, stage) in zip(phones, D.SIM_GUESTS, strict=False):
            phone = normalize_phone(raw)
            if not phone or same_phone(phone, host) or User.objects.filter(phone=phone).exclude(role="guest").exists():
                lines.append(f"{raw}: skipped - Amina's or a staff number, not a guest's")
                continue
            user, _ = User.objects.get_or_create(phone=phone, defaults={"first_channel": "ussd", "nationality": "KE"})
            if not user.name:
                user.name, user.lang = name, lang
            user.tags = [t for t in user.tags or [] if t != "seed"]
            if not user.has_id:  # on the guest register, so a door code can be released on arrival day
                user.set_id_number(str(self.rng.randint(20_000_000, 39_999_999)))
                user.id_type = "national_id"
                user.id_submitted_at = user.consent_at = timezone.now() - timedelta(days=30)
            user.save()
            b = user.bookings.order_by("-check_in").first()
            if b is None and stage != "new":
                b = self._sim_stay(user, *self.SIM_STAGES[stage])
            stay = f"{b.ref} {b.unit.name} {b.check_in:%d/%m}-{b.check_out:%d/%m} ({b.status})" if b else "no booking"
            lines.append(f"{phone} {user.name}: {stay}")
        return lines

    def _sim_stay(self, user, status, ranges, adults, plan, channel, prefer):
        """The first free home (those named first) for the first date range that has one."""
        from apps.messaging.automations import skip_overdue
        from apps.rewards import services as rewards
        from apps.rewards.models import PointsEntry

        units = sorted(
            Unit.objects.filter(status="active", max_guests__gte=adults),
            key=lambda u: (prefer.index(u.name) if u.name in prefer else len(prefer), u.sort_order),
        )
        for start, end in ranges:
            ci, co = self.t + timedelta(days=start), self.t + timedelta(days=end)
            for unit in units:
                if (
                    Booking.objects.filter(unit=unit, check_in__lt=co, check_out__gt=ci)
                    .filter(status__in=(*ACTIVE_STATUSES, "completed"))
                    .exists()
                    or CalendarBlock.objects.filter(unit=unit, start_date__lt=co, end_date__gt=ci).exists()
                ):
                    continue
                created = min(timezone.now() - timedelta(days=5), at_local(ci, "10:00") - timedelta(days=14))
                b = self._booking(
                    unit, user, ci, co, status=status, channel=channel, created=created, adults=adults, plan=plan
                )
                if status == "checked_in":
                    self._release(b, ci)
                elif status == "confirmed":
                    locks.create_code(b)
                else:
                    leave = at_local(co, "10:30")
                    Booking.objects.filter(pk=b.pk).update(
                        code_released_at=at_local(ci, "08:00"),
                        checked_in_at=at_local(ci, "14:30"),
                        checked_out_at=leave,
                    )
                    self._event(b, "checked_out", "Checked out via USSD - code deactivated", leave)
                    b.refresh_from_db()
                    points = rewards.award(
                        user,
                        rewards.stay_points(b),
                        "stay",
                        booking=b,
                        note=f"{b.ref} {unit.name}",
                        key=f"rewards:stay:{b.ref}",
                    )
                    if points is not None:
                        PointsEntry.objects.filter(pk=points.pk).update(created_at=leave)
                    short = rewards.program().redeem_points - rewards.balance(user)
                    if short > 0:  # enough to redeem airtime on the day
                        rewards.award(user, short, "bonus", note="Welcome back", key=f"rewards:welcome:{b.ref}")
                skip_overdue(b)
                return b
        return None
