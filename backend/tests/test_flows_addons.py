"""The Africa's Talking challenge add-ons, end to end on every channel: the support desk (Voice + SMS), service alerts
(SMS), the local guide (USSD + SMS + voice), rewards in airtime and mobile data, and the outage data bundle."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.bookings.models import Booking
from apps.comms.models import VoiceSession
from apps.comms.views import process_voice
from apps.guide import services as guide
from apps.guide.models import Event, Place
from apps.guide.seed import seed as seed_guide
from apps.messaging.models import Conversation
from apps.notices import services as notices
from apps.notices.models import Notice
from apps.operations.models import Task
from apps.operations.services import complete_task, report_issue, start_task
from apps.reviews.services import record_rating
from apps.rewards import services as rewards
from apps.rewards.models import Member, Payout, PointsEntry, Program
from apps.support import services as support
from apps.support.models import Ticket

from .conftest import days
from .flowkit import (
    KE_GUEST,
    bodies,
    build_catalogue,
    frozen,
    last_id,
    make_user,
    sms,
    spoken,
    stay,
    ussd,
    voice,
    with_id,
)

HOST = "+254700000001"
FRIEND = "+254799000222"


@pytest.fixture
def homes(db):
    return build_catalogue()[1]


@pytest.fixture
def team(db):
    return {
        role: make_user(phone, name=name, role=role, lang="sw")
        for name, phone, role in (
            ("Fatuma Ali", "+254700000011", "cleaner"),
            ("Juma Mwinyi", "+254700000012", "caretaker"),
            ("Hassan Omar", "+254700000014", "security"),
        )
    }


@pytest.fixture
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


@pytest.fixture
def in_house(homes, wanjiru):
    return stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(3), adults=2, checked_in=True)


def ticket():
    return Ticket.objects.order_by("-id").first()


# ---------- 1. Support desk: Voice + SMS ----------


@pytest.mark.django_db
def test_an_sms_complaint_gets_a_reference_a_reply_a_resolution_and_a_rating(homes, host, in_house):
    before = last_id()
    [ack] = sms("COMPLAIN the neighbours played loud music until 2am")
    t = ticket()
    assert (t.category, t.priority, t.channel, t.booking) == ("complaint", "high", "sms", in_house)
    assert abs(t.first_response_due - t.created_at - timedelta(minutes=30)) < timedelta(seconds=2)
    assert ack.startswith(f"We've logged your request {t.ref}:") and "within 30 minutes" in ack
    [told] = bodies(HOST, before)
    assert told.startswith(f"{t.ref}: Wanjiru Kamau ({in_house.ref} Blue Reef Apartment) - complaint:")
    assert f"Reply {t.ref} <text> to answer, CALL {t.ref}" in told

    assert sms(f"{t.ref} So sorry - Juma is on his way to speak to them", phone=HOST) == [
        f"Sent to Wanjiru Kamau ({t.ref})."
    ]
    assert bodies(KE_GUEST, before)[-1] == f"Amina ({t.ref}): So sorry - Juma is on his way to speak to them"
    t.refresh_from_db()
    assert t.status == "in_progress" and t.first_response_at

    assert sms(t.ref, phone=HOST)[0].startswith(
        f"{t.ref} Complaint from Wanjiru Kamau {KE_GUEST} (Blue Reef Apartment), in progress:"
    )
    assert sms(f"RESOLVE {t.ref} they've agreed to stop at 10pm", phone=HOST) == [
        f"{t.ref} resolved - the guest has been told."
    ]
    assert bodies(KE_GUEST)[-1] == (
        f"Your request {t.ref} is resolved. they've agreed to stop at 10pm How did we do? Reply 1-5 (5 = excellent)."
    )
    assert sms("5") == ["Thank you for rating us 5/5 - karibu tena!"]
    t.refresh_from_db()
    assert (t.status, t.rating) == ("resolved", 5)
    assert [e.kind for e in t.events.all()] == ["created", "reply", "status", "rating"]


@pytest.mark.django_db
def test_a_bare_complain_asks_for_details_and_a_low_rating_alerts_amina(homes, host, in_house):
    [ask] = sms("MALALAMIKO")
    assert ask.startswith("Sorry to hear that. Tell us what went wrong")
    sms("The towels were dirty")
    t = ticket()
    assert t.description == "The towels were dirty" and t.category == "complaint"
    support.resolve(t, note="Fresh towels delivered.")
    before = last_id()
    assert sms("1") == ["Thank you for telling us (1/5). We're sorry - Amina will call you to put it right."]
    assert bodies(HOST, before) == [f"{t.ref} was rated 1/5 by Wanjiru Kamau. Worth a call: CALL {t.ref}."]


@pytest.mark.django_db
def test_guests_track_their_requests_by_sms_and_ussd(homes, host, in_house):
    assert sms("TICKETS")[0].startswith("You have no open requests.")
    assert ussd("6") == "CON Talk to Amina\n1. Call me back\n2. Ask a question\n3. Make a complaint\n4. My requests"
    assert ussd("6*3") == (
        "CON What's it about?\n1. Noise/neighbours\n2. Cleanliness\n3. Staff/service\n4. Billing/payment\n"
        "5. My booking\n6. Something else"
    )
    assert ussd("6*3*2") == "CON Tell us briefly what happened:"
    out = ussd("6*3*2*sand in the beds")
    t = ticket()
    assert out == f"END Logged {t.ref}. Amina will reply by SMS within 30 minutes. Text {t.ref} any time for updates."
    assert (t.channel, t.subject) == ("ussd", "Cleanliness: sand in the beds")
    assert ussd("6*4") == f"END {t.ref} Complaint: Open"
    assert sms("TICKETS") == [
        f"Your requests: {t.ref} Complaint - Open. Reply the reference (e.g. {t.ref}) for details."
    ]
    support.reply(t, "Fatuma will change them at 2pm.")
    assert sms(t.ref.lower()) == [
        f"{t.ref} Complaint: Cleanliness: sand in the beds - In progress. Latest: Fatuma will change them at 2pm."
    ]
    assert sms("T99999") == ["We couldn't find request T99999 for this number. Reply TICKETS to see yours."]


@pytest.mark.django_db
def test_a_complaint_left_by_phone_becomes_a_ticket_with_the_recording(homes, host, in_house):
    voice("", session="v-c")
    voice("1", session="v-c")
    root = voice("5", session="v-c")
    assert root.find("Record") is not None
    assert "tell us what went wrong after the beep" in spoken(root)
    before = last_id()
    voice("", session="v-c", recordingUrl="https://voice.at/rec/complaint1.mp3")
    voice("", session="v-c", recordingUrl="https://voice.at/rec/complaint1.mp3")  # AT repeats the callback
    t = Ticket.objects.get()
    assert (t.channel, t.category, t.recording_url) == ("voice", "complaint", "https://voice.at/rec/complaint1.mp3")
    assert bodies(KE_GUEST, before)[0].startswith(f"We've logged your request {t.ref}")


@pytest.mark.django_db
def test_click_to_call_rings_amina_then_bridges_the_guest(homes, host, in_house, settings, host_api):
    t = support.request_callback(KE_GUEST, channel="sms")
    r = host_api.post(f"/api/host/support/tickets/{t.pk}/call")
    assert r.status_code == 200 and r.data["dry_run"] and not r.data["placed"]  # no voice number: simulated

    queued = {"entries": [{"phoneNumber": HOST, "status": "Queued", "sessionId": "ATVId_bridge"}]}
    with mock.patch("apps.comms.at.voice_call", return_value=queued) as call:
        r = host_api.post(f"/api/host/support/tickets/{t.pk}/call")
    assert r.data["placed"] and call.call_args.kwargs["client_request_id"] == f"bridge-{t.pk}"
    assert VoiceSession.objects.get(session_id="ATVId_bridge").state["purpose"] == "bridge"
    xml = process_voice({"sessionId": "ATVId_bridge", "isActive": "1", "direction": "Outbound", "callerNumber": HOST})
    assert f"call-back for ticket T {t.pk}, Wanjiru Kamau" in xml and f'phoneNumbers="{KE_GUEST}"' in xml
    process_voice(
        {
            "sessionId": "ATVId_bridge",
            "isActive": "0",
            "direction": "Outbound",
            "callerNumber": HOST,
            "dialDurationInSeconds": "95",
        }
    )
    t.refresh_from_db()
    assert t.status == "in_progress" and t.first_response_at
    assert t.events.filter(kind="call", text="Talked to the guest for 1 min 35 s").exists()


@pytest.mark.django_db
def test_unanswered_tickets_escalate_by_sms_then_a_voice_call(homes, host, in_house, site):
    site.backup_phone = "+254700000099"
    site.save()
    with frozen(timezone.localtime().replace(hour=11, minute=0)):
        t = support.open_ticket(KE_GUEST, category="complaint", subject="AC is broken", channel="sms")
        feedback = support.open_ticket(KE_GUEST, category="feedback", subject="Loved the breakfast", channel="sms")
    before = last_id()
    with frozen(t.created_at + timedelta(minutes=20)):
        assert support.escalate_overdue() == 0
    with frozen(t.created_at + timedelta(minutes=31)):
        assert support.escalate_overdue() == 1
        assert support.escalate_overdue() == 0  # once per level
    [reminder] = bodies(HOST, before)
    assert reminder.startswith(
        f"Waiting 31 min: {t.ref} complaint from Wanjiru Kamau (Blue Reef Apartment): AC is broken."
    )
    assert bodies("+254700000099", before) == [reminder]
    queued = {"entries": [{"phoneNumber": HOST, "status": "Queued", "sessionId": "ATVId_esc"}]}
    with frozen(t.created_at + timedelta(minutes=61)), mock.patch("apps.comms.at.voice_call", return_value=queued):
        assert support.escalate_overdue() == 1
    t.refresh_from_db()
    assert t.escalation_level == 2
    ask = process_voice({"sessionId": "ATVId_esc", "isActive": "1", "direction": "Outbound", "callerNumber": HOST})
    assert "has waited" in ask and f"ticket T {t.pk}: AC is broken. Press 1 to call them now." in ask
    dial = process_voice(
        {"sessionId": "ATVId_esc", "isActive": "1", "direction": "Outbound", "callerNumber": HOST, "dtmfDigits": "1"}
    )
    assert f'phoneNumbers="{KE_GUEST}"' in dial
    feedback.refresh_from_db()
    assert feedback.escalation_level == 0  # low priority waits 8 hours


@pytest.mark.django_db
def test_a_problem_in_the_home_is_a_ticket_that_follows_its_work_order(homes, team, in_house):
    before = last_id()
    task = report_issue(in_house, "The fridge stopped working", channel="sms")
    t = task.tickets.get()
    assert (t.category, t.channel, t.subject) == ("issue", "sms", task.title)
    assert [m for m in bodies(KE_GUEST, before) if "logged your request" in m] == []  # 'issue logged' is enough
    start_task(task, team["caretaker"])
    t.refresh_from_db()
    assert t.status == "in_progress" and t.first_response_at
    complete_task(task, team["caretaker"], note="New thermostat fitted")
    t.refresh_from_db()
    assert (t.status, t.resolution) == ("resolved", "New thermostat fitted")
    assert not bodies(KE_GUEST, before, kind="ticket_resolved")


@pytest.mark.django_db
def test_support_api_for_guests_and_the_host(homes, host, in_house, wanjiru, api, guest_api, host_api):
    from rest_framework.test import APIClient

    me = APIClient()
    me.force_authenticate(wanjiru)
    r = me.post(
        "/api/support/tickets",
        {"category": "billing", "description": "Was my deposit received?", "booking": in_house.ref},
        format="json",
    )
    assert r.status_code == 201 and r.data["ref"].startswith("T") and r.data["booking"] == in_house.ref
    assert me.post("/api/support/tickets", {"category": "billing", "description": ""}, format="json").status_code == 400
    assert me.post("/api/support/tickets", {"callback": True}, format="json").data["category"] == "callback"
    assert guest_api.get("/api/support/tickets").data == []  # another guest sees nothing of Wanjiru's
    assert guest_api.get("/api/host/support/tickets").status_code == 403

    listing = host_api.get("/api/host/support/tickets").data
    assert listing["counts"]["open"] == 2 and len(listing["tickets"]) == 2
    pk = r.data["id"]
    assert host_api.post(f"/api/host/support/tickets/{pk}/reply", {"text": ""}, format="json").status_code == 400
    d = host_api.post(f"/api/host/support/tickets/{pk}/reply", {"text": "Yes, it's in."}, format="json").data
    assert d["status"] == "in_progress" and d["events"][-1]["text"] == "Yes, it's in."
    d = host_api.post(f"/api/host/support/tickets/{pk}/resolve", {"note": "Deposit confirmed"}, format="json").data
    assert d["status"] == "resolved"
    rated = me.post(f"/api/support/tickets/{pk}/rate", {"rating": 4}, format="json")
    assert rated.status_code == 200 and rated.data["rating"] == 4 and not rated.data["can_rate"]
    d = host_api.post(f"/api/host/support/tickets/{pk}/reopen").data
    assert d["status"] == "in_progress"
    walk_in = host_api.post(
        "/api/host/support/tickets",
        {"phone": "0711 222 333", "category": "complaint", "subject": "Gate guard was rude"},
        format="json",
    )
    assert walk_in.status_code == 201 and walk_in.data["channel"] == "host" and walk_in.data["phone"] == "+254711222333"


# ---------- 3. Service alerts: SMS (and the outage data bundle: Mobile Data) ----------


@pytest.mark.django_db
def test_an_outage_texts_the_guests_staying_with_a_data_bundle_and_says_when_its_fixed(homes, host, team, in_house):
    elsewhere = stay(
        homes["Old Town Loft"], make_user("+254733111222", name="Otieno"), days(0), days(2), checked_in=True
    )
    before = last_id()
    n = notices.create(
        kind="outage",
        service="wifi",
        message="The fibre provider is fixing a fault.",
        units=[in_house.unit],
        expected_end=timezone.now() + timedelta(hours=2),
        actor=host,
    )
    assert (n.status, n.title, n.data_mb, n.notified) == ("active", "Wi-Fi down", 100, 1)
    [alert] = bodies(KE_GUEST, before)
    assert alert.startswith("Service alert at Blue Reef Apartment: Wi-Fi down. Expected back by")
    assert "We've sent you 100 MB of mobile data so you stay connected." in alert
    assert not bodies(elsewhere.guest.phone, before)  # a different home
    assert bodies(team["caretaker"].phone, before)[0].startswith(
        f"Service alert #{n.pk}: Wi-Fi down at Blue Reef Apartment."
    )
    p = Payout.objects.get(reason="outage")
    assert (p.kind, p.amount, p.status, p.phone) == ("data", 100, "simulated", KE_GUEST)  # no API key: a dry run

    assert sms("ALERTS")[0].startswith("Service status at Blue Reef Apartment: Wi-Fi down (since")
    assert sms("DATA") == [
        "You've already had your data bundle for this outage - we'll text you as soon as it's fixed."
    ]
    tasks = Task.objects.count()
    [known] = sms("no wifi")  # what the alert already covers: no password, no new work order
    assert known.startswith("We know - Wi-Fi down at Blue Reef Apartment since") and Task.objects.count() == tasks
    assert notices.run() == 0  # nobody new to tell

    assert notices.resolve(n, note="Line repaired.") == 1
    assert bodies(KE_GUEST)[-1] == (
        "Good news: Wi-Fi down at Blue Reef Apartment is over and everything is working again. Line repaired. "
        "Asante for your patience!"
    )
    assert sms("ALERTS") == ["All services are running normally at Blue Reef Apartment."]


@pytest.mark.django_db
def test_guests_who_arrive_mid_outage_are_told_and_reports_of_it_dont_open_work_orders(homes, host, team, wanjiru):
    n = notices.create(kind="outage", service="water", units=[homes["Blue Reef Apartment"]], actor=host)
    assert n.notified == 0
    b = stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), checked_in=True)
    before = last_id()
    assert notices.run() == 1
    assert bodies(KE_GUEST, before)[0].startswith("Service alert at Blue Reef Apartment: No water supply.")
    assert "mobile data" not in bodies(KE_GUEST, before)[0]  # water: no data bundle
    tasks = Task.objects.count()
    [known] = sms("There is no water in the shower")
    assert (
        known.startswith("We know - No water supply at Blue Reef Apartment since") and "No need to report it" in known
    )
    assert ussd("5*1").startswith("END We know - No water supply")
    r = sms("DATA")
    assert r == [
        "The Wi-Fi at your home is working normally, so there's no outage data to send. You can swap points for data any time: reply POINTS."
    ]
    assert Task.objects.count() == tasks
    assert b.unit.notices.filter(status="active").exists()


@pytest.mark.django_db
def test_a_guest_on_checkout_morning_still_hears_about_an_outage(homes, host):
    leaving = stay(
        homes["Old Town Loft"], make_user("+254733222111", name="Leaving Today"), days(0), days(1), checked_in=True
    )
    Booking.objects.filter(pk=leaving.pk).update(check_in=days(-2), check_out=days(0))  # leaves at 11am today
    n = notices.create(kind="outage", service="power", units=[leaving.unit], actor=host)
    assert n.notified == 1 and bodies("+254733222111")[-1].startswith("Service alert at Old Town Loft: Power outage.")


@pytest.mark.django_db
def test_planned_maintenance_warns_a_day_ahead_starts_quietly_and_reports_back(homes, host, in_house):
    start = timezone.now() + timedelta(hours=30)
    n = notices.create(
        kind="maintenance",
        service="power",
        units=[in_house.unit],
        starts_at=start,
        expected_end=start + timedelta(hours=2),
        message="Kenya Power is upgrading the line.",
        actor=host,
    )
    assert n.status == "scheduled" and n.notified == 0  # more than a day away
    before = last_id()
    with frozen(start - timedelta(hours=23)):
        assert notices.run() == 1
    [heads_up] = bodies(KE_GUEST, before)
    assert heads_up.startswith("Heads-up from Amina Stays: Planned maintenance: Power at Blue Reef Apartment on")
    with frozen(start + timedelta(minutes=1)):
        assert notices.run() == 0
    n.refresh_from_db()
    assert n.status == "active" and len(bodies(KE_GUEST, before)) == 1  # warned already: no second text
    with frozen(start + timedelta(hours=2, minutes=31)):
        notices.run()
        notices.run()
    assert len([m for m in bodies(HOST, before) if f"Service alert #{n.pk}" in m and "Still on?" in m]) == 1
    assert notices.resolve(n) == 1
    assert bodies(KE_GUEST)[-1].startswith("Good news: Planned maintenance: Power at Blue Reef Apartment is over")


@pytest.mark.django_db
def test_staff_and_amina_post_and_close_outages_by_sms(homes, host, team, in_house):
    caretaker = team["caretaker"]
    assert sms("OUTAGE POWER", phone=caretaker.phone) == ["Which home? Text OUTAGE POWER <home name|ALL> <message>."]
    assert sms("OUTAGE LAVA ALL", phone=caretaker.phone)[0].startswith("Which service?")
    before = last_id()
    [done] = sms("OUTAGE STIMA ALL generator is running", phone=caretaker.phone)
    n = Notice.objects.get()
    assert (
        done == f"Alert #{n.pk} sent: Power outage at all homes. 1 guest(s) told. Text RESTORED {n.pk} when it's fixed."
    )
    assert (n.service, n.message, n.source, n.created_by) == ("power", "generator is running", "sms", caretaker)
    assert "Power outage. Generator is running. " in bodies(KE_GUEST, before)[-1]
    assert any(m.startswith(f"Juma Mwinyi reported service alert #{n.pk}") for m in bodies(HOST, before))
    assert sms("ALERTS", phone=HOST)[0].startswith(f"#{n.pk} Power outage (since")
    assert sms(f"RESTORED {n.pk} all good", phone=HOST) == [
        f"Alert #{n.pk} closed: Power outage. 1 guest(s) told it's fixed."
    ]
    assert sms(f"RESTORED {n.pk}", phone=HOST) == [f"No open service alert #{n.pk}."]
    blue = sms("OUTAGE WATER Blue Reef pump repair", phone=HOST)[0]
    assert "No water supply at Blue Reef Apartment" in blue
    assert list(Notice.objects.order_by("-id").first().units.all()) == [in_house.unit]


@pytest.mark.django_db
def test_notice_api_previews_creates_updates_and_cancels(homes, host_api, in_house):
    unit = in_house.unit
    body = {"kind": "outage", "service": "power", "unit_ids": [unit.pk], "message": "Generator on."}
    p = host_api.post("/api/host/notices/preview", body, format="json").data
    assert (
        p["guests"] == 1
        and p["sms"].startswith("Service alert at Blue Reef Apartment: Power outage.")
        and p["segments"] >= 1
    )
    assert host_api.post("/api/host/notices", {**body, "service": "lava"}, format="json").status_code == 400
    assert host_api.post("/api/host/notices", {**body, "message": "{oops"}, format="json").status_code == 400
    created = host_api.post("/api/host/notices", body, format="json")
    assert (
        created.status_code == 201
        and created.data["notified"] == 1
        and created.data["units"] == [{"id": unit.pk, "name": unit.name}]
    )
    pk = created.data["id"]
    end = (timezone.now() + timedelta(hours=3)).isoformat()
    upd = host_api.post(
        f"/api/host/notices/{pk}/update", {"expected_end": end, "message": "Engineers on site."}, format="json"
    )
    assert upd.status_code == 200 and upd.data["message"] == "Engineers on site."
    assert bodies(KE_GUEST)[-1].startswith(
        "Update - Power outage at Blue Reef Apartment: Engineers on site. Expected back by"
    )
    assert host_api.post(f"/api/host/notices/{pk}/cancel").status_code == 400  # it's running: resolve it instead
    assert host_api.post(f"/api/host/notices/{pk}/resolve", {"note": ""}, format="json").data["status"] == "resolved"
    later = (timezone.now() + timedelta(days=3)).isoformat()
    plan = host_api.post(
        "/api/host/notices",
        {"kind": "maintenance", "service": "pool", "unit_ids": [], "starts_at": later},
        format="json",
    ).data
    assert plan["status"] == "scheduled" and plan["all_homes"]
    assert host_api.post(f"/api/host/notices/{plan['id']}/cancel").data["status"] == "cancelled"
    current = host_api.get("/api/host/notices").data["notices"]
    assert current == []
    assert [n["id"] for n in host_api.get("/api/host/notices?status=all").data["notices"]] == [plan["id"], pk]
    public = host_api.get(f"/api/notices?unit={unit.slug}").data
    assert public == []


# ---------- 2. Local guide: USSD + SMS + voice + web ----------


@pytest.fixture
def places(homes):
    seed_guide()
    return {p.name: p for p in Place.objects.all()}


@pytest.mark.django_db
def test_the_guide_api_filters_and_sorts_places_by_distance_from_a_home(places, homes, api):
    diani = homes["Diani Palm Suite"]
    diani.latitude, diani.longitude = -4.3170, 39.5813
    diani.save()
    data = api.get("/api/guide").data
    assert {c["key"] for c in data["categories"]} >= {"sights", "beaches", "food", "transport"}
    assert len(data["places"]) == Place.objects.count() and data["events"]
    fort = next(p for p in data["places"] if p["name"] == "Fort Jesus")
    assert (
        fort["area"] == {"slug": "old-town", "name": "Old Town"}
        and "query=Fort+Jesus%2C+Old+Town%2C+Kenya" in fort["map_url"]
    )
    beaches = api.get("/api/guide?category=beaches").data["places"]
    assert beaches and {p["category"] for p in beaches} == {"beaches"}
    near = api.get(f"/api/guide/nearby/{diani.slug}?limit=3").data
    assert [p["name"] for p in near] == ["Diani Beach", "Colobus Conservation", "Shimba Hills National Reserve"]
    assert near[0]["distance_km"] < 1
    assert [p["distance_km"] for p in near] == sorted(p["distance_km"] for p in near)
    assert api.get("/api/guide/nearby/nowhere").status_code == 404


@pytest.mark.django_db
def test_explore_on_ussd_sends_the_details_and_a_map_by_sms(places, in_house):
    more = ussd("8")
    assert more == "CON More\n1. Explore the area\n2. Service status\n3. Rewards\n4. Language"
    menu = ussd("8*1")
    assert menu.startswith("CON Explore the coast\n1. Top picks\n2. Sights & history\n3. Beaches & sea")
    top = ussd("8*1*1")
    assert top.startswith("CON Top picks\n1. ")  # the guest's own area first: Blue Reef is in Nyali
    before = last_id()
    out = ussd("8*1*1*1")
    assert out.startswith("END ") and out.endswith("Hours, prices and a map sent by SMS.")
    [details] = bodies(KE_GUEST, before)
    assert "Map: https://www.google.com/maps/search/?api=1&query=" in details
    assert ussd("8*1*98").endswith("11. What's on")
    events = ussd("8*1*11")  # what's on: the next few events, the full list by SMS
    assert events.startswith("END ") and events.endswith("Sent to you by SMS.")
    assert ussd("8*2") == "END All services are running normally at Blue Reef Apartment."


@pytest.mark.django_db
def test_explore_by_sms_is_a_two_step_conversation(places, in_house):
    [menu] = sms("EXPLORE")
    assert menu.startswith("Explore the coast - reply with a number: 1 Top picks, 2 Sights & history")
    [listing] = sms("3")
    assert listing.startswith("Beaches & sea: 1) ") and listing.endswith("Reply a number for hours, prices and a map.")
    [one] = sms("1")
    assert "Map: https://www.google.com/maps/search/" in one
    [two] = sms("2")  # the list stays open for another pick
    assert two != one and "Map: " in two
    assert sms("EXPLORE FOOD")[0].startswith("Food & drink: 1) Mama Ngina Waterfront")
    assert sms("EVENTS")[0].startswith("What's on: ")
    assert Conversation.objects.get(phone=KE_GUEST).state == "idle"
    assert Place.objects.filter(hits__gt=0).count() == 2


@pytest.mark.django_db
def test_explore_by_sms_takes_over_a_pending_booking_offer(places, in_house):
    sms("Nataka nyumba 12 Dec siku 3 watu 2")
    assert Conversation.objects.get(phone=KE_GUEST).state not in guide.STATES  # an offer waiting for a reply
    assert sms("EXPLORE")[0].startswith("Explore the coast - reply with a number")
    assert sms("3")[0].startswith("Beaches & sea: 1) ")
    assert "Map: " in sms("1")[0]  # the place's details, not the offer's first home
    assert not Booking.objects.filter(status="held").exists()


@pytest.mark.django_db
def test_press_6_on_a_call_reads_three_favourites_and_texts_the_list(places, in_house):
    voice("", session="v-g")
    voice("1", session="v-g")
    before = last_id()
    root = voice("6", session="v-g")
    said = spoken(root)
    assert said.startswith("Here are some favourites near you. Fort Jesus: 16th-century Portuguese fort")
    assert "We have sent these and more to you by text message. Press 0 for the main menu." in said
    [listing] = bodies(KE_GUEST, before)
    assert listing.startswith("Top picks: 1) ")
    assert sms("1")[0].endswith(guide.top_picks(guide.origin_of(in_house.unit), limit=6)[0].map_url)


@pytest.mark.django_db
def test_event_dates_repeat_weekly_and_yearly(db):
    weekly = Event(title="Market", weekday=5)
    assert weekly.next_on(days(0)).weekday() == 5 and 0 <= (weekly.next_on(days(0)) - days(0)).days <= 6
    t = days(0)
    over_new_year = Event(
        title="Festive",
        starts_on=t.replace(month=12, day=30),
        ends_on=t.replace(year=t.year + 1, month=1, day=2),
        yearly=True,
    )
    assert over_new_year.next_on(t.replace(month=1, day=1)) == t.replace(month=1, day=1)
    assert over_new_year.next_on(t.replace(month=6, day=1)) == t.replace(month=12, day=30)
    one_off = Event(title="Gone", starts_on=days(-5), ends_on=days(-4))
    assert one_off.next_on(days(0)) is None and Event(title="Soon", starts_on=days(3)).next_on(days(0)) == days(3)


@pytest.mark.django_db
def test_amina_edits_the_guide_from_the_console(homes, host_api, guest_api):
    body = {"name": "Nyali Golf Club", "category": "nature", "area": "nyali", "summary": "18 holes by the sea."}
    assert guest_api.post("/api/host/guide/places", body, format="json").status_code == 403
    r = host_api.post("/api/host/guide/places", {**body, "latitude": -4.04}, format="json")
    assert r.status_code == 400 and "latitude and a longitude" in r.data["error"]
    r = host_api.post("/api/host/guide/places", {**body, "latitude": -4.04, "longitude": 39.72}, format="json")
    assert r.status_code == 201 and r.data["slug"] == "nyali-golf-club" and r.data["area"] == "nyali"
    bad = host_api.post(
        "/api/host/guide/events", {"title": "Golf day", "weekday": 2, "starts_on": str(days(3))}, format="json"
    )
    assert bad.status_code == 400
    ok = host_api.post(
        "/api/host/guide/events", {"title": "Golf day", "weekday": 2, "place": r.data["id"]}, format="json"
    )
    assert ok.status_code == 201 and ok.data["next_on"]


# ---------- 4. Rewards: Airtime (and data) ----------


@pytest.fixture
def program(db):
    p = Program.load()
    p.started_at = timezone.now() - timedelta(days=60)
    p.save()
    return p


def checked_out(b):
    from apps.bookings import services as bookings

    bookings.check_out(b, channel="sms")
    b.refresh_from_db()
    return b


@pytest.mark.django_db
def test_stays_and_feedback_earn_points_once_and_ota_stays_none(homes, program, in_house):
    paid = in_house.amount_paid
    b = checked_out(in_house)
    before = last_id()
    assert rewards.run() == 1
    assert rewards.run() == 0  # idempotent
    assert rewards.balance(b.guest) == paid // 100
    [earned] = bodies(KE_GUEST, before)
    assert earned.startswith(f"Asante for staying with us! You earned {paid // 100} Amina Rewards points")
    record_rating(b, 5, channel="sms")
    rewards.run()
    assert rewards.balance(b.guest) == paid // 100 + program.review_points
    ota = stay(
        homes["Old Town Loft"],
        make_user("+254733444555", name="Airbnb Guest"),
        days(0),
        days(1),
        channel="airbnb",
        checked_in=True,
    )
    checked_out(ota)
    rewards.run()
    assert rewards.balance(ota.guest) == 0


@pytest.mark.django_db
def test_redeeming_points_for_airtime_by_sms_with_delivery_reports(homes, program, wanjiru, settings, client):
    rewards.award(wanjiru, 250, "bonus")
    assert sms("POINTS")[0].startswith("Amina Rewards: 250 points. Reply REDEEM AIRTIME for KES 100 airtime")
    settings.AT_API_KEY = "live-key"
    answer = {
        "numSent": 1,
        "responses": [{"phoneNumber": KE_GUEST, "status": "Sent", "requestId": "ATQid_1", "errorMessage": "None"}],
    }
    with mock.patch("apps.comms.at._post", return_value=answer) as post:
        [done] = sms("REDEEM AIRTIME")
    assert done == f"Done! KES 100 is on its way to {KE_GUEST}. You have 150 points left."
    assert post.call_args.kwargs["headers"]["Idempotency-Key"].startswith(f"redeem-{wanjiru.pk}-")
    p = Payout.objects.get()
    assert (p.status, p.provider_ref) == ("sent", "ATQid_1")
    client.post("/at/airtime/status", {"requestId": "ATQid_1", "status": "Failed", "phoneNumber": KE_GUEST})
    p.refresh_from_db()
    assert p.status == "failed" and rewards.balance(wanjiru) == 250  # the points come back
    client.post("/at/airtime/status", {"requestId": "ATQid_1", "status": "Failed"})  # repeated: no double refund
    assert rewards.balance(wanjiru) == 250
    assert sms("REDEEM DATA") == [  # live keys but no Mobile Data product: no pretend bundles
        "Data rewards aren't available right now - reply REDEEM AIRTIME to swap your points for airtime instead."
    ]
    settings.AT_DATA_PRODUCT = "AminaData"
    with mock.patch("apps.comms.at._post", side_effect=Exception("network down")):
        assert sms("REDEEM DATA")[0].startswith(
            "Sorry - we couldn't send your 250 MB just now, so your points are back (250)"
        )
    PointsEntry.objects.create(user=wanjiru, points=-200, reason="adjust")
    assert sms("REDEEM AIRTIME") == [
        "You have 50 points - 50 more to redeem a reward. You earn points with every stay and for sharing feedback."
    ]


@pytest.mark.django_db
def test_a_friends_code_pays_airtime_to_both_after_the_first_stay(homes, program, wanjiru):
    code = rewards.member(wanjiru).code
    assert code.startswith("WANJIRU")
    assert (
        sms(f"REF {code}")[0] == "Sorry, that code didn't work: that's your own code - share it with friends instead."
    )
    friend = make_user(FRIEND, name="Baraka Otieno")
    [ok] = sms(f"REF {code}", phone=FRIEND)
    assert (
        ok == f"Code {code} saved - thanks to Wanjiru! After your first stay you'll both get airtime (KES 100 for you)."
    )
    assert sms(f"REF {code}", phone=FRIEND)[0].endswith("you've already used a friend's code.")
    assert sms("REF NOPE12", phone=FRIEND)[0].endswith("we don't have that code - check the spelling.")
    b = checked_out(stay(homes["Old Town Loft"], with_id(friend), days(0), days(1), checked_in=True))
    before = last_id()
    rewards.run()
    rewards.run()
    paid = Payout.objects.filter(reason__in=("referral", "referee")).order_by("reason")
    assert [(p.reason, p.phone, p.amount) for p in paid] == [("referee", FRIEND, 100), ("referral", KE_GUEST, 100)]
    assert bodies(KE_GUEST, before) == [
        "Your friend Baraka just finished their first stay with us - KES 100 airtime is on its way to you. Asante for spreading the word!"
    ]
    assert any(m.startswith("Karibu to Amina Rewards!") for m in bodies(FRIEND, before))
    assert Member.objects.get(user=friend).referral_booking == b
    stayed = with_id(make_user("+254799000333", name="Repeat Guest"))
    checked_out(stay(homes["Old Town Loft"], stayed, days(0), days(1), checked_in=True))
    assert rewards.apply_referral(stayed, code) == (
        False,
        "Sorry, that code didn't work: invite codes are for guests before their first stay.",
    )


@pytest.mark.django_db
def test_the_monthly_budget_holds_airtime_for_amina_to_approve(homes, program, wanjiru, host_api):
    program.monthly_airtime_budget = 150
    program.save()
    rewards.award(wanjiru, 300, "bonus")
    rewards.redeem(wanjiru, "airtime")
    before = last_id()
    p, text = rewards.redeem(wanjiru, "airtime")
    assert p.status == "held" and text.startswith("Thanks! Your KES 100 reward is waiting for Amina's OK")
    assert bodies(HOST, before)[0].startswith("Rewards: this month's airtime budget is used up")
    stats = host_api.get("/api/host/rewards").data
    assert stats["stats"]["payouts_held"] == 1 and stats["stats"]["airtime_month"] == 100
    assert host_api.post(f"/api/host/rewards/payouts/{p.pk}/approve").data["status"] == "simulated"
    _, _ = rewards.redeem(wanjiru, "airtime")
    held = Payout.objects.filter(status="held").get()
    assert host_api.post(f"/api/host/rewards/payouts/{held.pk}/reject").data["status"] == "rejected"
    assert rewards.balance(wanjiru) == 100  # the rejected reward's points came back


@pytest.mark.django_db
def test_rewards_on_ussd_and_the_web(homes, program, wanjiru, host_api):
    from rest_framework.test import APIClient

    rewards.award(wanjiru, 120, "bonus")
    code = rewards.member(wanjiru).code
    screen = ussd("8*3")
    assert (
        screen
        == f"CON 120 points. Your code {code}\n1. KES 100 airtime\n2. 250MB data\n3. Enter a friend's code\n4. How it works (SMS)"
    )
    before = last_id()
    assert (
        ussd("8*3*2")
        == f"END Sending 250 MB to {KE_GUEST} now - we'll text you when it's done. You have 20 points left."
    )
    assert bodies(KE_GUEST, before, kind="rewards_redeem") == [
        f"Done! 250 MB is on its way to {KE_GUEST}. You have 20 points left."
    ]
    assert ussd("8*3*4") == "END Sent to you by SMS."
    me = APIClient()
    me.force_authenticate(wanjiru)
    d = me.get("/api/me/rewards").data
    assert d["points"] == 20 and d["code"] == code and not d["redeem"]["can_airtime"] and d["can_enter_code"]
    assert me.post("/api/me/rewards/redeem", {"kind": "airtime"}, format="json").status_code == 400
    assert me.post("/api/me/rewards/referral", {"code": code}, format="json").status_code == 400
    abroad = make_user("+447700900123", name="Emma")
    them = APIClient()
    them.force_authenticate(abroad)
    assert them.get("/api/me/rewards").data["redeem"]["why_not"].startswith("Airtime and data rewards need a Kenyan")
    assert (
        host_api.post(
            "/api/host/rewards/send", {"phone": "+447700900123", "kind": "airtime", "amount": 50}, format="json"
        ).status_code
        == 400
    )
    gift = host_api.post(
        "/api/host/rewards/send",
        {"phone": KE_GUEST, "kind": "airtime", "amount": 50, "note": "sorry about the noise"},
        format="json",
    )
    assert gift.status_code == 201 and gift.data["reason"] == "manual" and gift.data["amount_text"] == "KES 50"
    assert bodies(KE_GUEST)[-1] == "Amina from Amina Stays has sent you KES 50 - sorry about the noise. Asante!"
    program_now = host_api.get("/api/host/rewards").data["program"]
    assert (
        host_api.put("/api/host/rewards/program", {**program_now, "redeem_points": 0}, format="json").status_code == 400
    )
    assert (
        host_api.put("/api/host/rewards/program", {**program_now, "redeem_points": 200}, format="json").data[
            "redeem_points"
        ]
        == 200
    )


@pytest.mark.django_db
def test_demo_lab_outage_and_answering_a_call_back(homes, host, in_house, api, settings):
    r = api.post(f"/api/demo/outage/{in_house.ref}", {"service": "power"}, format="json")
    assert r.status_code == 200 and r.data["told"] == 1 and r.data["data_mb"] == 100
    assert api.post(f"/api/demo/outage/{in_house.ref}", {"service": "power"}, format="json").status_code == 400
    assert api.post(f"/api/demo/outage/{in_house.ref}", {"restore": True}, format="json").data["status"] == "resolved"
    t = support.request_callback(KE_GUEST, channel="sms")
    support.call_guest(t)
    out = api.post(
        "/api/demo/voice",
        {"phone": HOST, "session": "demo-b1", "direction": "Outbound", "clientRequestId": "bridge-latest"},
        format="json",
    )
    assert f"ticket T {t.pk}" in out.json()["xml"] and f'phoneNumbers="{KE_GUEST}"' in out.json()["xml"]
    settings.DEMO = False
    assert api.post(f"/api/demo/outage/{in_house.ref}", {}, format="json").status_code == 404
