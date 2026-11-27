"""Messaging core: the outbox, conversation threads, templates, knowledge-base answers and broadcasts.

Outbound messages are written to the database first (status 'queued') and handed to a small worker
pool only after the surrounding transaction commits — the transactional-outbox pattern. A USSD or
voice webhook therefore never waits on an SMS round-trip, and nothing is lost if Africa's Talking is
slow: the scheduler re-dispatches anything still queued.
"""

import logging
import re
import string
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, close_old_connections, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import SiteSettings
from apps.core.utils import normalize_phone

from .models import FAQ, Message, Template, Thread
from .templates_default import DEFAULTS

log = logging.getLogger("amina.messaging")
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="outbox")

# ---------- templates ----------


class _Safe(dict):
    def __missing__(self, key):
        return ""


def render(key, lang="en", **ctx):
    """Template text in the guest's language: console override → built-in → English override → English built-in."""
    lang = lang if lang in ("en", "sw", "it", "de", "fr") else "en"
    body = Template.objects.filter(key=key, lang=lang).values_list("body", flat=True).first() or DEFAULTS.get(
        key, {}
    ).get(lang)
    if body is None:
        body = Template.objects.filter(key=key, lang="en").values_list("body", flat=True).first() or DEFAULTS.get(
            key, {}
        ).get("en", key)
    s = SiteSettings.load()
    ctx.setdefault("business", s.business_name)
    ctx.setdefault("host", s.host_name)
    out = string.Formatter().vformat(body, (), _Safe(ctx))
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def placeholder_error(text):
    """Why text Amina typed can't be used as a message (a stray '{' or '}', '{0}'), or None if it's fine."""
    try:
        string.Formatter().vformat(text or "", (), _Safe())
    except (ValueError, IndexError, KeyError, AttributeError) as e:
        return f"Check the {{placeholders}}: {e}. Write them like {{first_name}}, or remove the braces."
    return None


# ---------- GSM-7 hygiene (one stray smart quote turns a 160-char SMS into 70-char segments) ----------

_GSM_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ ÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM_EXT = set("^{}\\[~]|€")
_REPLACE = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "…": "...",
    "•": "-",
    "→": "->",
    "★": "*",
    "\u00a0": " ",
}


def to_gsm(text):
    out = []
    for ch in text:
        ch = _REPLACE.get(ch, ch)
        if all(c in _GSM_BASIC or c in _GSM_EXT for c in ch):
            out.append(ch)
            continue
        base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
        out.append(base or "")
    return "".join(out)


def sms_segments(text):
    gsm = all(c in _GSM_BASIC or c in _GSM_EXT for c in text)
    length = sum(2 if c in _GSM_EXT else 1 for c in text) if gsm else len(text)
    single, multi = (160, 153) if gsm else (70, 67)
    return 1 if length <= single else -(-length // multi)


# ---------- threads ----------


def get_thread(phone, guest=None):
    thread, _ = Thread.objects.get_or_create(phone=phone, defaults={"guest": guest})
    if guest is not None and thread.guest_id is None:
        thread.guest = guest
        thread.save(update_fields=["guest"])
    return thread


def _guest(phone):
    from apps.accounts.models import User

    return User.objects.filter(phone=phone).first()


def record_inbound(phone, body, *, channel="sms", booking=None, provider_id="", sender="guest", handled="pending"):
    """Save a guest's message. Africa's Talking re-delivers a webhook it thinks we missed: a provider id we already
    hold returns that first message with .duplicate = True and changes nothing, so it is never answered twice."""
    provider_id = (provider_id or "")[:80]
    if provider_id and (first := _first_inbound(provider_id)):
        return first
    guest = _guest(phone)
    thread = get_thread(phone, guest)
    try:
        with transaction.atomic():
            msg = Message.objects.create(
                thread=thread,
                phone=phone,
                booking=booking,
                direction="in",
                channel=channel,
                sender=sender,
                body=body or "",
                status="received",
                handled=handled,
                provider_id=provider_id,
            )
    except IntegrityError:  # the same webhook, delivered twice at once
        first = _first_inbound(provider_id) if provider_id else None
        if first is None:
            raise
        return first
    msg.duplicate = False
    Thread.objects.filter(pk=thread.pk).update(
        unread=F("unread") + 1, last_message_at=msg.created_at, last_preview=(body or "")[:160], status="open"
    )
    return msg


def _first_inbound(provider_id):
    first = Message.objects.filter(direction="in", provider_id=provider_id).first()
    if first is not None:
        first.duplicate = True
        log.info("ignored a repeated inbound message %s from %s", provider_id, first.phone)
    return first


def mark(msg, handled, kind=""):
    """Record how an inbound message was dealt with. 'relayed' puts the thread in Amina's queue."""
    if msg is None:
        return
    msg.handled = handled
    if kind:
        msg.kind = kind[:40]
    msg.save(update_fields=["handled", "kind"])
    thread = msg.thread
    if handled == "relayed":
        thread.needs_reply = True
        thread.waiting_since = thread.waiting_since or msg.created_at
        thread.save(update_fields=["needs_reply", "waiting_since"])
    elif (
        handled in ("auto", "answered")
        and not Message.objects.filter(thread=thread, direction="in", handled="relayed").exists()
    ):
        thread.needs_reply = False
        thread.waiting_since = None
        thread.save(update_fields=["needs_reply", "waiting_since"])


# ---------- outbox ----------

REDACTED = "••••••"  # a login code wherever its message is stored or shown: only the SMS itself carries the code


def send(
    phone,
    body,
    *,
    booking=None,
    kind="",
    sender="system",
    user=None,
    channel=None,
    marketing=False,
    sync=False,
    secret="",
):
    """Queue an outbound message. Returns the Message (or None if suppressed by an opt-out).
    secret: a login code inside body. The message carries it, but it is never stored - the saved copy (inbox, admin,
    exports) reads REDACTED instead and doesn't touch the thread's preview - so it goes out at once, from memory."""
    phone = normalize_phone(phone) or phone
    if not phone or not body:
        log.warning("message skipped (no recipient/body): %s", kind)
        return None
    guest = _guest(phone)
    if marketing and guest and guest.sms_opt_out_at:
        return None
    if channel is None:
        channel = (
            "whatsapp" if (guest and guest.preferred_channel == "whatsapp" and settings.AT_WHATSAPP_NUMBER) else "sms"
        )
    if channel in ("sms", "whatsapp"):
        body = to_gsm(body) if channel == "sms" else body
    thread = get_thread(phone, guest)
    msg = Message.objects.create(
        thread=thread,
        phone=phone,
        booking=booking,
        direction="out",
        channel=channel,
        sender=sender,
        body=body.replace(secret, REDACTED) if secret else body,
        kind=kind[:40],
        status="queued" if channel in ("sms", "whatsapp") else "sent",
        sent_by=user,
        is_marketing=marketing,
    )
    updates = {} if secret else {"last_message_at": msg.created_at, "last_preview": body[:160]}
    if sender in ("host", "staff"):
        updates.update(needs_reply=False, waiting_since=None, unread=0)
        Message.objects.filter(thread=thread, direction="in", handled="relayed").update(handled="answered")
    if updates:
        Thread.objects.filter(pk=thread.pk).update(**updates)
    if msg.status == "queued":
        _schedule(msg.pk, sync or bool(secret), text=body if secret else None)
    return msg


def _schedule(message_id, sync=False, text=None):
    mode = "sync" if sync else settings.OUTBOX_MODE
    if mode == "sync":
        transaction.on_commit(lambda: dispatch(message_id, text), robust=True)
    elif mode == "thread":
        transaction.on_commit(lambda: _executor.submit(_dispatch_in_thread, message_id, text), robust=True)
    # mode == "queue": the scheduler picks it up


def _dispatch_in_thread(message_id, text=None):
    try:
        dispatch(message_id, text)
    except Exception:
        log.exception("dispatch failed for message %s", message_id)
    finally:
        close_old_connections()


def _suppressed(phone):
    """Seeded demo people have placeholder numbers: never send them real SMS, even with live credentials."""
    from apps.accounts.models import User

    return User.objects.filter(phone=phone, tags__contains=["seed"]).exists()


# Africa's Talking answers every recipient with a statusCode: 100 Processed, 101 Sent and 102 Queued are accepted.
SMS_ACCEPTED = (100, 101, 102)
WHATSAPP_ACCEPTED = ("SENT", "DELIVERED", "READ")
SMS_UNDELIVERABLE = {  # final: sending the same message again can't help
    402: "Sender ID not registered with this network (402 InvalidSenderId)",
    403: "Not a valid mobile number (403 InvalidPhoneNumber)",
    404: "This number can't receive SMS (404 UnsupportedNumberType)",
    406: "The guest has blocked our SMS - they can text START to opt back in (406 UserInBlacklist)",
}
SMS_NO_CREDIT = 405  # InsufficientBalance: Amina has to top up the Africa's Talking account
MAX_ATTEMPTS = 3  # sends in all; after the third the message stays failed
RETRY_BACKOFF = (timedelta(minutes=1), timedelta(minutes=5))  # 5xx, 407, network: the waits before sends 2 and 3
SENDING_LEASE = timedelta(minutes=2)  # a 'sending' row older than this lost its worker
NO_CREDIT_RETRY = timedelta(minutes=30)  # booking messages wait out a 405 (not counted as attempts)...
NO_CREDIT_GIVE_UP = timedelta(hours=24)  # ...for a day at most


def dispatch(message_id, text=None):
    """Send one queued message. text is the real wording when the stored body was redacted (send(secret=...)): such
    a message goes out once, from memory - if that fails it stays failed and the guest asks for a new code."""
    from apps.comms import at

    with transaction.atomic():
        msg = Message.objects.select_for_update(skip_locked=True).filter(pk=message_id, status="queued").first()
        if not msg:
            return
        msg.status = "sending"
        msg.attempts += 1
        msg.next_attempt_at = timezone.now() + SENDING_LEASE
        msg.save(update_fields=["status", "attempts", "next_attempt_at"])
    if _suppressed(msg.phone):
        msg.status, msg.sent_at, msg.next_attempt_at = "logged", timezone.now(), None
        msg.save(update_fields=["status", "sent_at", "next_attempt_at"])
        return msg
    if text is None and REDACTED in msg.body:  # its code was never stored: there's nothing to send again
        msg.status, msg.next_attempt_at, msg.failure_reason = "failed", None, "Login code not kept, so not re-sent"
        msg.save(update_fields=["status", "next_attempt_at", "failure_reason"])
        return msg
    msg.next_attempt_at = None
    try:
        if msg.channel == "whatsapp":
            res = at.send_whatsapp(msg.phone, text or msg.body)
            if res.get("dry_run"):
                status = "logged"
            else:
                msg.provider_id = str(res.get("messageId") or "")[:80]
                msg.provider_status = str(res.get("status") or "")[:40]
                # AT returns a messageId only for a message it took; FAILED / DELETED are failed sends
                if not (res.get("messageId") and msg.provider_status.upper() in WHATSAPP_ACCEPTED):
                    raise at.ATError(f"WhatsApp not sent ({msg.provider_status or 'no message id'})")
                status = "sent"
        else:
            res = at.send_sms(msg.phone, text or msg.body)
            if res.get("dry_run"):
                status = "logged"
            else:
                r = (res.get("recipients") or [{}])[0]
                code = _status_code(r)
                msg.provider_id = str(r.get("messageId", ""))[:80]
                msg.provider_status = str(r.get("status", ""))[:40]
                msg.cost = str(r.get("cost", ""))[:20]
                status = (
                    "sent"
                    if code in SMS_ACCEPTED
                    else _refused(msg, code, str(r.get("status") or res.get("message") or "rejected"))
                )
        msg.status = status
        if status != "queued":
            msg.sent_at = timezone.now()
        if status in ("sent", "logged"):
            msg.failure_reason = ""  # an earlier attempt's error no longer applies
    except Exception as e:  # network/HTTP error: try again after a pause
        msg.status = _retry_later(msg, str(e))
        log.warning("send failed (%s/%s) to %s: %s", msg.attempts, MAX_ATTEMPTS, msg.phone, e)
    if text is not None and msg.status == "queued":  # a retry would need the code we didn't keep
        msg.status, msg.next_attempt_at = "failed", None
    msg.save(
        update_fields=[
            "status",
            "sent_at",
            "provider_id",
            "provider_status",
            "cost",
            "failure_reason",
            "attempts",
            "next_attempt_at",
        ]
    )
    return msg


def _status_code(recipient):
    try:
        return int(recipient.get("statusCode") or 0)
    except (TypeError, ValueError):
        return 0


def _refused(msg, code, provider_status):
    """The message's next status after Africa's Talking refused it (anything but 100-102)."""
    if code in SMS_UNDELIVERABLE:
        msg.failure_reason = SMS_UNDELIVERABLE[code]
        if code == 406:
            _blocked_by_recipient(msg.phone)
        return "failed"
    if code == SMS_NO_CREDIT:
        _no_credit_alert()
        reason = "Africa's Talking balance too low (405 InsufficientBalance)"
        if msg.is_marketing:
            msg.failure_reason = f"{reason} - promotions are not retried"
            return "failed"
        if msg.created_at < timezone.now() - NO_CREDIT_GIVE_UP:
            msg.failure_reason = f"{reason} for a whole day - not sent"
            return "failed"
        msg.attempts -= 1  # waiting for a top-up doesn't use up one of its retries
        msg.failure_reason = f"{reason} - waiting for a top-up"
        msg.next_attempt_at = timezone.now() + NO_CREDIT_RETRY
        return "queued"
    if code == 407 or 500 <= code <= 599:  # CouldNotRoute, gateway errors: usually gone in minutes
        return _retry_later(msg, f"{provider_status or 'Gateway error'} ({code})")
    msg.failure_reason = provider_status[:120]
    return "failed"


def _retry_later(msg, reason):
    msg.failure_reason = reason[:120]
    if msg.attempts >= MAX_ATTEMPTS:
        msg.next_attempt_at = None
        return "failed"
    msg.next_attempt_at = timezone.now() + RETRY_BACKOFF[msg.attempts - 1]
    return "queued"


def _blocked_by_recipient(phone):
    """406 UserInBlacklist: the number opted out at the network (STOP to our sender ID). Promotions stop here too,
    and the activity feed says why; texting START opts them back in."""
    from apps.accounts.models import User
    from apps.core.activity import record

    if User.objects.filter(phone=phone, sms_opt_out_at__isnull=True).update(sms_opt_out_at=timezone.now()):
        record(
            "guest",
            f"{phone} has blocked our SMS at the network (406 UserInBlacklist) - marked as opted out",
            phone=phone,
            reason="UserInBlacklist",
        )


def _no_credit_alert():
    from apps.core.utils import today
    from apps.safety.services import raise_alert

    raise_alert(
        "sms",
        "Africa's Talking balance is too low - SMS aren't going out. Top up the account: booking messages wait "
        "and go out after the top-up, promotions are dropped.",
        source="system",
        dedupe=f"at-no-credit:{today()}",
        notify=False,  # an SMS to Amina can't go out either
    )


def dispatch_pending():
    now = timezone.now()
    ready = Q(next_attempt_at__isnull=True, created_at__lt=now - timedelta(seconds=20)) | Q(next_attempt_at__lte=now)
    ids = list(
        Message.objects.filter(ready, status="queued", attempts__lt=MAX_ATTEMPTS).values_list("id", flat=True)[:50]
    )
    for mid in ids:
        dispatch(mid)
    # a 'sending' row whose lease ran out means a worker died mid-flight
    lapsed = Q(next_attempt_at__lt=now) | Q(next_attempt_at__isnull=True, created_at__lt=now - SENDING_LEASE)
    Message.objects.filter(lapsed, status="sending", attempts__lt=MAX_ATTEMPTS).update(status="queued")
    return len(ids)


DELIVERY_MAP = {
    "Success": "delivered",
    "Failed": "failed",
    "Rejected": "failed",
    "AbsentSubscriber": "failed",
    "Expired": "failed",
}


def on_delivery_report(provider_id, status, failure_reason=""):
    msg = Message.objects.filter(provider_id=provider_id).first()
    if not msg:
        return None
    msg.provider_status = status[:40]
    new = DELIVERY_MAP.get(status)
    if new:
        msg.status = new
        if new == "delivered":
            msg.delivered_at = timezone.now()
        if failure_reason:
            msg.failure_reason = failure_reason[:120]
    msg.save(update_fields=["provider_status", "status", "delivered_at", "failure_reason"])
    return msg


# ---------- knowledge base ----------

_STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "what",
    "do",
    "you",
    "i",
    "me",
    "my",
    "to",
    "of",
    "and",
    "for",
    "in",
    "at",
    "it",
    "there",
    "can",
    "how",
    "please",
}


def _tokens(text):
    return [t for t in re.findall(r"[a-zà-ÿ0-9']+", (text or "").lower()) if t not in _STOP]


def faq_context(phone, booking=None):
    """Values FAQ answers may use. Booking-only facts (Wi-Fi, directions) exist only for a booked guest."""
    from apps.bookings.services import guest_context
    from apps.properties.services import price_list_text

    s = SiteSettings.load()
    ctx = {
        "business": s.business_name,
        "host": s.host_name,
        "prices": price_list_text(),
        "checkin_time": _t(s.default_checkin_time),
        "checkout_time": _t(s.default_checkout_time),
        "ussd_code": settings.AT_USSD_CODE,
        "sms_number": settings.AT_SMS_NUMBER,
        "website": settings.FRONTEND_URL,
        "deposit_percent": s.deposit_percent,
    }
    if booking is not None:
        ctx.update(guest_context(booking))
    return ctx


def _t(hhmm):
    from apps.core.utils import nice_time

    return nice_time(hhmm)


def _normalise(text):
    """One spelling for the words guests write every way: Wi-Fi / wi fi / WiFi, check-in / check in, check-out."""
    text = re.sub(r"\bwi[\s-]?fi\b", "wifi", text, flags=re.IGNORECASE)
    return re.sub(r"\bcheck[\s-]?(in|out)\b", r"check\1", text, flags=re.IGNORECASE)


def match_faq(text, lang="en", unit=None, ctx=None):
    """Best knowledge-base answer for a free-text question, or None if not confident.
    Answers that reference booking-only facts are skipped when the sender has no booking; on a tie, a
    personalised answer (this guest's Wi-Fi, directions…) beats a generic one."""
    text = _normalise(text or "")
    low = " " + text.lower() + " "
    toks = set(_tokens(text))
    if not toks:
        return None
    ctx = ctx or {}
    scored = []
    for faq in FAQ.objects.filter(active=True).filter(unit__isnull=True) | FAQ.objects.filter(active=True, unit=unit):
        score = 0
        for kw in {_normalise(k.strip().lower()) for k in faq.keywords.split(",") if k.strip()}:
            if not kw.replace("'", "").isalnum():  # phrases and hyphenated words ("late checkout", "how do i get")
                score += 3 if kw in low else 0
            elif kw in toks:
                score += 2
            elif len(kw) > 4 and any(t.startswith(kw[:5]) for t in toks):
                score += 1
        if faq.unit_id and unit is not None:
            score += 1
        if score < 2:
            continue
        answer = faq.answer(lang)
        fields = {f for _, f, _, _ in string.Formatter().parse(answer) if f}
        if all(ctx.get(f) not in (None, "") for f in fields):
            scored.append((score, bool(fields), -faq.sort_order, faq.pk, faq, answer))
    if not scored:
        return None
    *_, faq, answer = max(scored, key=lambda x: x[:4])
    FAQ.objects.filter(pk=faq.pk).update(hits=F("hits") + 1)
    return faq, string.Formatter().vformat(answer, (), _Safe(ctx))
    scored = []
    for faq in FAQ.objects.filter(active=True).filter(unit__isnull=True) | FAQ.objects.filter(active=True, unit=unit):
        score = 0
        for kw in (_normalise(k.strip().lower()) for k in faq.keywords.split(",") if k.strip()):
            if not kw.replace("'", "").isalnum():  # phrases and hyphenated words ("check in", "check-out")
                score += 3 if kw in low else 0
            elif kw in toks:
                score += 2
            elif len(kw) > 4 and any(t.startswith(kw[:5]) for t in toks):
                score += 1
        if faq.unit_id and unit is not None:
            score += 1
        if score >= 2:
            scored.append((score, -faq.sort_order, faq))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    ctx = ctx or {}
    for _, _, faq in scored:
        answer = faq.answer(lang)
        fields = {f for _, f, _, _ in string.Formatter().parse(answer) if f}
        if all(ctx.get(f) not in (None, "") for f in fields):
            FAQ.objects.filter(pk=faq.pk).update(hits=F("hits") + 1)
            return faq, string.Formatter().vformat(answer, (), _Safe(ctx))
    return None


# ---------- broadcasts ----------


def audience_phones(audience, unit=None):
    from apps.accounts.models import User
    from apps.bookings.models import Booking, Waitlist
    from apps.core.utils import today

    t = today()
    qs = Booking.objects.all()
    if unit is not None:
        qs = qs.filter(unit=unit)
    if audience == "in_house":
        phones = qs.filter(status="checked_in").values_list("guest__phone", flat=True)
    elif audience == "arriving":
        phones = qs.filter(
            status="confirmed", check_in__gte=t, check_in__lte=t + timezone.timedelta(days=7)
        ).values_list("guest__phone", flat=True)
    elif audience == "upcoming":
        phones = qs.filter(status__in=("confirmed", "checked_in"), check_out__gte=t).values_list(
            "guest__phone", flat=True
        )
    elif audience == "past":
        phones = (
            qs.filter(status="completed", guest__marketing_opt_in=True, guest__sms_opt_out_at__isnull=True)
            .exclude(channel__in=("airbnb", "booking_com"))  # OTA guests may not be solicited off-platform
            .values_list("guest__phone", flat=True)
        )
    elif audience == "waitlist":
        phones = Waitlist.objects.filter(status="waiting", check_out__gt=t).values_list("guest__phone", flat=True)
    elif audience == "staff":
        phones = User.objects.filter(
            role__in=("manager", "cleaner", "cook", "caretaker", "security", "driver"), is_active=True
        ).values_list("phone", flat=True)
    else:
        phones = []
    return sorted(set(phones))


def broadcast_window_ok(is_marketing):
    """Promotional SMS only inside the configured window (Kenyan operators restrict promo hours)."""
    if not is_marketing:
        return True
    s = SiteSettings.load()
    return s.promo_window_start <= timezone.localtime().hour < s.promo_window_end
