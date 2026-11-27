"""Booking engine: pricing, no double bookings (service + database), payments and the stay lifecycle."""

import threading

import pytest
from django.db import IntegrityError, connection, transaction

from apps.bookings import services as bookings
from apps.bookings.models import Booking
from apps.messaging.models import Message
from apps.payments import services as payments
from apps.payments.models import Payment
from apps.properties.services import quote

from .conftest import days


def test_quote_is_all_in(unit, site):
    q = quote(unit, days(10), days(13), guests=2)
    assert q["nights"] == 3
    taxable = q["accommodation"] - q["discount"] + q["cleaning_fee"] + q["addons"]
    assert q["levy"] == round(taxable * float(site.tourism_levy_percent) / 100)
    assert q["total"] == taxable + q["levy"] + q["vat"]
    assert sum(line["amount"] for line in q["lines"]) == q["total"]


def test_deposit_only_when_far_enough_ahead(unit, site):
    far = quote(unit, days(30), days(32), payment_plan="deposit")
    assert far["deposit_available"] and far["due_now"] == far["deposit"] < far["total"]
    near = quote(unit, days(1), days(2), payment_plan="deposit")
    assert not near["deposit_available"] and near["due_now"] == near["total"]


def test_breakfast_priced_per_guest_per_night(unit, breakfast):
    q = quote(unit, days(5), days(8), guests=2, addons=[{"addon": breakfast, "quantity": 2}])
    assert q["addons"] == 650 * 2 * 3


def test_overlapping_hold_is_refused(unit, guest, foreign_guest):
    bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(8), channel="ussd")
    with pytest.raises(bookings.BookingError):
        bookings.create_hold(unit=unit, guest=foreign_guest, check_in=days(7), check_out=days(9), channel="web")
    # back-to-back stays (check-out day = next check-in day) are fine
    bookings.create_hold(unit=unit, guest=foreign_guest, check_in=days(8), check_out=days(10), channel="web")


def test_database_constraint_blocks_overlap_even_without_the_service(unit, guest):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(8), channel="sms")
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.create(
            ref="AMS-0000",
            unit=unit,
            guest=guest,
            check_in=days(6),
            check_out=days(7),
            status="confirmed",
            channel="walk_in",
            total=1,
            cancellation_policy="flexible",
        )
    # cancelled/expired bookings don't block the dates
    Booking.objects.filter(pk=b.pk).update(status="cancelled")
    Booking.objects.create(
        ref="AMS-0001",
        unit=unit,
        guest=guest,
        check_in=days(6),
        check_out=days(7),
        status="confirmed",
        channel="walk_in",
        total=1,
        cancellation_policy="flexible",
    )


@pytest.mark.django_db(transaction=True)
def test_simultaneous_holds_from_two_channels_only_one_wins(unit, guest, foreign_guest):
    barrier = threading.Barrier(2)
    results = []

    def attempt(who, channel):
        try:
            barrier.wait()
            bookings.create_hold(unit=unit, guest=who, check_in=days(20), check_out=days(23), channel=channel)
            results.append("ok")
        except bookings.BookingError:
            results.append("taken")
        finally:
            connection.close()

    threads = [
        threading.Thread(target=attempt, args=(guest, "ussd")),
        threading.Thread(target=attempt, args=(foreign_guest, "web")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(15)
    assert sorted(results) == ["ok", "taken"]
    assert Booking.objects.filter(unit=unit, status="held").count() == 1


def test_expired_hold_releases_the_dates(unit, guest, foreign_guest):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(8), channel="ussd")
    Booking.objects.filter(pk=b.pk).update(hold_expires_at=b.hold_expires_at.replace(year=2000))
    again = bookings.create_hold(unit=unit, guest=foreign_guest, check_in=days(5), check_out=days(8), channel="web")
    b.refresh_from_db()
    assert b.status == "expired" and again.status == "held"


def test_payment_confirms_once_even_with_duplicate_callbacks(unit, guest):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(7), channel="sms")
    payments.start_payment(b, method="mpesa")
    p = Payment.objects.get(booking=b)
    payments.on_success(p, transaction_id="QAB123")
    payments.on_success(p, transaction_id="QAB123")
    b.refresh_from_db()
    assert b.status == "confirmed"
    assert b.amount_paid == b.total
    assert Message.objects.filter(phone=guest.phone, kind="booking_confirmed").count() == 1


def test_underpayment_is_rejected(unit, guest):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(7), channel="web")
    payments.start_payment(b, method="mpesa")
    p = Payment.objects.get(booking=b)
    payments.on_success(p, amount=p.amount - 1)
    b.refresh_from_db()
    p.refresh_from_db()
    assert p.status == "failed" and b.status == "held" and b.amount_paid == 0


def test_late_payment_after_dates_were_resold_becomes_refund_due(unit, guest, foreign_guest):
    first = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(7), channel="ussd")
    payments.start_payment(first, method="mpesa")
    late = Payment.objects.get(booking=first)
    Booking.objects.filter(pk=first.pk).update(hold_expires_at=first.hold_expires_at.replace(year=2000))
    second = bookings.create_hold(unit=unit, guest=foreign_guest, check_in=days(5), check_out=days(7), channel="web")
    payments.on_success(late, transaction_id="QLATE1")
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == "refund_due"
    assert second.status == "held"


def test_late_payment_reinstates_when_still_free(unit, guest):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=days(5), check_out=days(7), channel="ussd")
    payments.start_payment(b, method="mpesa")
    p = Payment.objects.get(booking=b)
    Booking.objects.filter(pk=b.pk).update(status="expired")
    payments.on_success(p, transaction_id="QLATE2")
    b.refresh_from_db()
    assert b.status == "confirmed"


def _confirmed(unit, guest, check_in, check_out):
    b = bookings.create_hold(unit=unit, guest=guest, check_in=check_in, check_out=check_out, channel="web")
    payments.start_payment(b, method="mpesa")
    payments.on_success(Payment.objects.get(booking=b), transaction_id=f"Q{b.pk}")
    b.refresh_from_db()
    return b


def test_door_code_waits_for_the_guest_register_then_releases(unit, guest, site):
    site.require_id_before_code = True
    site.save()
    b = _confirmed(unit, guest, days(0), days(2))
    assert bookings.release_code(b) == "waiting_id"
    guest.set_id_number("28123456")
    guest.save()
    assert bookings.release_code(b) == "released"
    b.refresh_from_db()
    assert b.status == "checked_in"
    code = b.access_codes.get(revoked_at__isnull=True).code
    assert Message.objects.filter(phone=guest.phone, kind="checkin_code", body__contains=code).exists()


def test_sim_swap_holds_the_door_code(unit, site, db):
    from apps.accounts.models import User

    swapped = User.objects.create_user("+254711000999", name="Swapped Sim")
    swapped.set_id_number("30111222")
    swapped.save()
    site.sim_swap_check = True
    site.save()
    b = _confirmed(unit, swapped, days(0), days(1))
    assert bookings.release_code(b) in ("checking_sim", "security_hold")
    assert bookings.release_code(b) == "security_hold"
    b.refresh_from_db()
    assert b.status == "confirmed"


def test_checkout_revokes_the_code(unit, guest):
    guest.set_id_number("28123456")
    guest.save()
    b = _confirmed(unit, guest, days(0), days(2))
    assert bookings.release_code(b) == "released"
    bookings.check_out(b, channel="sms")
    b.refresh_from_db()
    assert b.status == "completed"
    assert not b.access_codes.filter(revoked_at__isnull=True).exists()


def test_flexible_cancellation_refunds_in_full(unit, guest):
    b = _confirmed(unit, guest, days(10), days(12))
    result = bookings.cancel(b, by="guest")
    b.refresh_from_db()
    assert b.status == "cancelled" and result["refund"] == b.total


def test_cancelled_dates_can_be_booked_again(unit, guest, foreign_guest):
    b = _confirmed(unit, guest, days(10), days(12))
    bookings.cancel(b, by="guest")
    assert (
        bookings.create_hold(
            unit=unit, guest=foreign_guest, check_in=days(10), check_out=days(12), channel="web"
        ).status
        == "held"
    )
