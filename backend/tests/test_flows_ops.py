"""Host console APIs end to end: messaging (inbox, templates, automations, knowledge base, broadcasts), operations
(tasks, staff, roles, kitchen, guest CRM), safety (alerts, guest register), core (config, health, settings,
channels, activity, locks) and who may call them."""

import csv
import io
from datetime import timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.bookings import services as bookings
from apps.bookings.models import AccessCode, BookingAddon
from apps.core.models import Activity, JobRun, SiteSettings
from apps.messaging.models import FAQ, Automation, Broadcast, Message, Template, Thread
from apps.operations.models import Task
from apps.safety.services import escalate, raise_alert

from .conftest import days
from .flowkit import KE_GUEST, bodies, build_catalogue, frozen, kenya, last_id, make_user, sms, stay, with_id

HOST = "+254700000001"


@pytest.fixture
def homes(db):
    return build_catalogue()[1]


@pytest.fixture
def wanjiru(db):
    return with_id(make_user(KE_GUEST, name="Wanjiru Kamau"))


@pytest.fixture
def team(db):
    return {
        role: make_user(phone, name=name, role=role, lang="sw")
        for name, phone, role in (
            ("Fatuma Ali", "+254700000011", "cleaner"),
            ("Juma Mwinyi", "+254700000012", "caretaker"),
            ("Mama Zawadi", "+254700000013", "cook"),
            ("Hassan Omar", "+254700000014", "security"),
        )
    }


@pytest.fixture
def in_house(homes, wanjiru):
    return stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(3), adults=2, checked_in=True)


def as_user(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


# ---------- permissions ----------

HOST_GETS = [
    "/api/host/inbox",
    "/api/host/templates",
    "/api/host/automations",
    "/api/host/faqs",
    "/api/host/broadcasts",
    "/api/host/tasks",
    "/api/host/staff",
    "/api/host/roles",
    "/api/host/kitchen",
    "/api/host/guests",
    "/api/host/alerts",
    "/api/host/compliance/register",
    "/api/host/settings",
    "/api/host/channels",
    "/api/host/activity",
    "/api/host/locks",
]


@pytest.mark.django_db
def test_only_amina_and_her_co_host_reach_the_console(api, guest_api, host_api, team):
    manager = as_user(make_user("+254700000020", name="Rehema", role="manager"))
    cleaner = as_user(team["cleaner"])
    for url in HOST_GETS:
        assert api.get(url).status_code == 403, url
        assert guest_api.get(url).status_code == 403, url
        assert cleaner.get(url).status_code == 403, url
        assert host_api.get(url).status_code == 200, url
        assert manager.get(url).status_code == 200, url
    for url, body in (
        ("/api/host/broadcasts", {"audience": "staff", "body": "x"}),
        ("/api/host/faq-test", {"text": "wifi"}),
    ):
        assert guest_api.post(url, body, format="json").status_code == 403
        assert cleaner.post(url, body, format="json").status_code == 403
    assert not Broadcast.objects.exists()


@pytest.mark.django_db
def test_public_config_and_health(api, settings):
    settings.AT_USSD_CODE, settings.AT_SMS_NUMBER = "*384*1234#", "22384"
    make_user("+254700000011", name="Fatuma", role="cleaner", tags=["seed"])
    make_user("+254700000077", name="Real Cleaner", role="cleaner")
    c = api.get("/api/config").json()
    assert c["business"]["name"] == "Amina Stays" and c["business"]["checkin_time"] == "14:00"
    assert c["channels"]["ussd_code"] == "*384*1234#" and c["channels"]["sms_number"] == "22384"
    assert c["payments"]["simulated"] is True and c["deposit_percent"] == 30 and c["demo"] is True
    assert [s["name"] for s in c["demo_lab"]["staff"]] == ["Fatuma"]  # seeded demo people only, never real staff
    assert c["demo_lab"]["host_phone"] == HOST
    h = api.get("/health").json()
    assert h["status"] == "ok" and h["db"] == "ok"


# ---------- inbox ----------


@pytest.mark.django_db
def test_inbox_lists_filters_opens_replies_and_resolves(homes, host_api, host, team, in_house):
    sms("Can my cousin visit us one evening?")
    other = make_user("+254799000555", name="Baraka")
    sms("Do you know a good tailor in town?", phone=other.phone)
    sms("PRICES", phone="+254799000666")  # answered by the bot: not waiting
    sms("Running late", phone=team["cleaner"].phone)

    rows = host_api.get("/api/host/inbox").json()
    assert {r["phone"] for r in rows} == {
        KE_GUEST,
        other.phone,
        "+254799000666",
    }  # guests only; Amina's own and staff threads hidden
    assert [r["needs_reply"] for r in rows] == [True, True, False]
    mine = next(r for r in rows if r["phone"] == KE_GUEST)
    assert mine["guest"]["name"] == "Wanjiru Kamau" and mine["booking"]["ref"] == in_house.ref and mine["unread"] == 1
    assert {r["phone"] for r in host_api.get("/api/host/inbox?filter=needs_reply").json()} == {KE_GUEST, other.phone}
    assert [r["phone"] for r in host_api.get("/api/host/inbox?filter=staff").json()] == [team["cleaner"].phone]
    assert [r["phone"] for r in host_api.get("/api/host/inbox?q=baraka").json()] == [other.phone]
    assert [r["phone"] for r in host_api.get("/api/host/inbox?q=555").json()] == [other.phone]
    assert [r["phone"] for r in host_api.get("/api/host/inbox?q=Wanjiru").json()] == [KE_GUEST]

    tid = mine["id"]
    detail = host_api.get(f"/api/host/inbox/{tid}").json()
    assert detail["thread"]["unread"] == 0 and detail["bookings"][0]["ref"] == in_house.ref
    assert detail["messages"][-1]["kind"] == "relay_ack"
    assert any("BlueReef / reef-sunrise-2026" in q for q in detail["quick_replies"])

    before = last_id()
    r = host_api.post(f"/api/host/inbox/{tid}/reply", {"text": "Of course - karibu!", "channel": "sms"}, format="json")
    assert r.status_code == 200 and r.json()["thread"]["needs_reply"] is False
    [sent] = Message.objects.filter(phone=KE_GUEST, id__gt=before)
    assert (sent.body, sent.channel, sent.sender, sent.sent_by, sent.kind) == (
        "Amina: Of course - karibu!",
        "sms",
        "host",
        host,
        "host_reply",
    )
    assert not Message.objects.filter(thread_id=tid, direction="in", handled="relayed").exists()
    assert host_api.post(f"/api/host/inbox/{tid}/reply", {"text": " "}, format="json").status_code == 400

    baraka = Thread.objects.get(phone=other.phone)
    r = host_api.post(f"/api/host/inbox/{baraka.pk}/resolve")
    assert r.json()["status"] == "resolved" and r.json()["needs_reply"] is False
    assert Message.objects.get(thread=baraka, direction="in").handled == "answered"
    assert [r["phone"] for r in host_api.get("/api/host/inbox?filter=needs_reply").json()] == []
    assert host_api.get("/api/host/inbox/999999").status_code == 404
    assert Activity.objects.filter(kind="message", title__startswith="Reply to Wanjiru").exists()


@pytest.mark.django_db
def test_a_web_chat_reply_stays_in_the_web_chat(homes, host_api, wanjiru):
    as_user(wanjiru).post("/api/messages", {"body": "Can we check in at 1pm?"}, format="json")
    tid = Thread.objects.get(phone=KE_GUEST).pk
    host_api.post(f"/api/host/inbox/{tid}/reply", {"text": "Yes, from 1pm is fine", "channel": "web"}, format="json")
    reply = Message.objects.filter(phone=KE_GUEST, sender="host").get()
    assert reply.channel == "web" and reply.status == "sent"  # shown in the guest's chat, not texted
    chat = as_user(wanjiru).get("/api/messages").json()["messages"]
    assert chat[-1]["body"] == "Amina: Yes, from 1pm is fine"
    r = host_api.post(f"/api/host/inbox/{tid}/reply", {"text": "hi", "channel": "pigeon"}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_whatsapp_replies_fall_back_to_sms_when_whatsapp_is_not_set_up(homes, host_api, wanjiru, settings):
    sms("Is the pool heated?")
    tid = Thread.objects.get(phone=KE_GUEST).pk
    host_api.post(f"/api/host/inbox/{tid}/reply", {"text": "It's solar heated", "channel": "whatsapp"}, format="json")
    assert Message.objects.get(phone=KE_GUEST, sender="host").channel == "sms"
    settings.AT_WHATSAPP_NUMBER = "+254711000222"
    host_api.post(f"/api/host/inbox/{tid}/reply", {"text": "And open 7-7", "channel": "whatsapp"}, format="json")
    assert Message.objects.filter(phone=KE_GUEST, sender="host").latest("id").channel == "whatsapp"


# ---------- templates ----------


@pytest.mark.django_db
def test_templates_list_override_per_language_and_reset(homes, host_api, in_house, wanjiru):
    data = host_api.get("/api/host/templates").json()
    welcome = next(t for t in data["templates"] if t["key"] == "welcome_check")
    assert set(welcome["langs"]) == {"en", "sw", "it", "de", "fr"} and welcome["langs"]["sw"]["custom"] is False
    assert welcome["description"] == "Arrival evening: 'settled in?'" and "first_name" in data["placeholders"]

    r = host_api.put(
        "/api/host/templates/welcome_check/sw", {"body": "Habari {first_name}! Umefika salama {unit}?"}, format="json"
    )
    assert r.status_code == 200 and r.json()["segments"] == 1
    assert host_api.put("/api/host/templates/welcome_check/sw", {"body": " "}, format="json").status_code == 400
    wanjiru.lang = "sw"
    wanjiru.save()
    in_house.lang = "sw"
    in_house.save()
    bookings.send_guest(in_house, "welcome_check")
    assert bodies(KE_GUEST, kind="welcome_check")[-1] == "Habari Wanjiru! Umefika salama Blue Reef Apartment?"
    listed = next(t for t in host_api.get("/api/host/templates").json()["templates"] if t["key"] == "welcome_check")
    assert listed["langs"]["sw"]["custom"] is True and listed["langs"]["en"]["custom"] is False

    bad = host_api.put("/api/host/templates/booking_confirmed/en", {"body": "Booked {unit! Ref {ref}"}, format="json")
    assert bad.status_code == 400 and bad.json()["error"].startswith("Check the {placeholders}")
    assert not Template.objects.filter(key="booking_confirmed").exists()  # confirmations keep working

    assert host_api.delete("/api/host/templates/welcome_check/sw").json() == {"reset": True}
    assert not Template.objects.exists()
    bookings.send_guest(in_house, "welcome_check")
    assert bodies(KE_GUEST, kind="welcome_check")[-1].startswith("Umetulia Blue Reef Apartment, Wanjiru?")


# ---------- automations ----------


@pytest.mark.django_db
def test_automations_list_edit_and_preview_with_real_data(homes, host_api, in_house):
    autos = host_api.get("/api/host/automations").json()
    assert [a["key"] for a in autos] == [
        "pre_arrival",
        "id_request",
        "balance_due",
        "directions",
        "welcome_check",
        "mid_stay",
        "checkout_reminder",
        "rebook_offer",
    ]
    mid = next(a for a in autos if a["key"] == "mid_stay")
    r = host_api.patch(
        f"/api/host/automations/{mid['id']}", {"enabled": False, "send_time": "11:30", "key": "hacked"}, format="json"
    )
    assert r.status_code == 200 and r.json()["enabled"] is False and r.json()["send_time"] == "11:30"
    assert Automation.objects.get(pk=mid["id"]).key == "mid_stay"  # the key is fixed
    for bad in ("7pm", "25:00", "9:5"):
        assert (
            host_api.patch(f"/api/host/automations/{mid['id']}", {"send_time": bad}, format="json").status_code == 400
        )
    assert host_api.patch(f"/api/host/automations/{mid['id']}", {"send_time": ""}, format="json").status_code == 200
    host_api.patch(f"/api/host/automations/{mid['id']}", {"send_time": "11:30"}, format="json")
    assert host_api.post("/api/host/automations", {"key": "new"}, format="json").status_code == 405
    assert host_api.delete(f"/api/host/automations/{mid['id']}").status_code == 405

    preview = host_api.post(
        f"/api/host/automations/{mid['id']}/preview", {"ref": in_house.ref.lower()}, format="json"
    ).json()
    assert preview["ref"] == in_house.ref and preview["segments"] >= 1
    assert (
        preview["text"]
        == "Hope you're enjoying Nyali! Fancy a mid-stay clean with fresh towels (KES 1,500)? Reply CLEAN. Anything else, just reply."
    )
    rebook = Automation.objects.get(key="rebook_offer")
    text = host_api.post(f"/api/host/automations/{rebook.pk}/preview", {}, format="json").json()["text"]
    assert "/stays/blue-reef-apartment" in text and "KARIBU10" in text
    checkout = Automation.objects.get(key="checkout_reminder")
    text = host_api.post(f"/api/host/automations/{checkout.pk}/preview", {}, format="json").json()["text"]
    assert text.startswith("Checkout is tomorrow by 11am.")
    later = stay(homes["Diani Palm Suite"], make_user("+254799000999", name="Later Guest"), days(10), days(12))
    directions = Automation.objects.get(key="directions")
    text = host_api.post(f"/api/host/automations/{directions.pk}/preview", {"ref": later.ref}, format="json").json()
    assert "Wi-Fi: DianiPalm" in text["text"] and "shared 2 days" not in text["text"]  # Amina sees the real message


@pytest.mark.django_db
def test_automation_preview_without_any_booking(host_api):
    pre = host_api.get("/api/host/automations").json()[0]
    assert host_api.post(f"/api/host/automations/{pre['id']}/preview", {}, format="json").json() == {
        "text": "Make a booking first to preview with real data."
    }


# ---------- knowledge base ----------


@pytest.mark.django_db
def test_faq_crud_and_the_test_box(host_api, homes):
    created = host_api.post(
        "/api/host/faqs",
        {
            "category": "amenities",
            "question": "Is there a pool?",
            "keywords": "pool,swim,bwawa",
            "answer_en": "Yes - Bamburi has a private pool.",
            "answer_sw": "Ndiyo - Bamburi ina bwawa.",
        },
        format="json",
    )
    assert created.status_code == 201
    fid = created.json()["id"]
    hit = host_api.post("/api/host/faq-test", {"text": "can we swim?"}, format="json").json()
    assert hit == {"matched": True, "question": "Is there a pool?", "answer": "Yes - Bamburi has a private pool."}
    assert (
        host_api.post("/api/host/faq-test", {"text": "bwawa?", "lang": "sw"}, format="json").json()["answer"]
        == "Ndiyo - Bamburi ina bwawa."
    )
    assert FAQ.objects.get(pk=fid).hits == 2
    assert host_api.patch(f"/api/host/faqs/{fid}", {"active": False, "hits": 99}, format="json").json()["hits"] == 2
    assert host_api.post("/api/host/faq-test", {"text": "can we swim?"}, format="json").json()["matched"] is False
    wifi = host_api.post("/api/host/faq-test", {"text": "wifi password"}, format="json").json()
    assert wifi["question"] == "Is there Wi-Fi?"  # tested as a stranger: the booked-guest answer is never shown
    assert host_api.post("/api/host/faq-test", {"text": "zzz qqq"}, format="json").json()["matched"] is False
    broken = host_api.patch(f"/api/host/faqs/{fid}", {"answer_en": "Swim from {pool_hours"}, format="json")
    assert broken.status_code == 400 and "placeholders" in broken.json()["error"]
    assert APIClient().get("/api/faqs").status_code == 200  # the help centre keeps working
    assert host_api.delete(f"/api/host/faqs/{fid}").status_code == 204
    assert not FAQ.objects.filter(pk=fid).exists()
    public = APIClient().get("/api/faqs").json()
    assert (
        public
        and all("{" not in f["answer"] for f in public)
        and "What is the Wi-Fi password?" not in [f["question"] for f in public]
    )


# ---------- broadcasts ----------


@pytest.fixture
def audiences(homes, wanjiru):
    """One in-house guest, one arriving in 5 days, two past guests (one opted in, one opted out)."""
    stay(homes["Blue Reef Apartment"], wanjiru, days(0), days(2), checked_in=True)
    arriving = make_user("+254733100001", name="Arriving")
    stay(homes["Old Town Loft"], arriving, days(5), days(6))
    fans = []
    for phone, opted_out, home in (
        ("+254733100002", False, "Nyali Breeze Studio"),
        ("+254733100003", True, "Bamburi Family House"),
    ):
        g = make_user(phone, name=phone[-4:], marketing_opt_in=True)
        b = stay(homes[home], g, days(0), days(2), checked_in=True)
        bookings.check_out(b)
        if opted_out:
            sms("STOP", phone=phone)
        fans.append(g)
    return {"arriving": arriving, "fan": fans[0], "stopped": fans[1]}


@pytest.mark.django_db
def test_broadcast_preview_and_operational_send(host_api, host, audiences, team):
    assert host_api.post("/api/host/broadcasts", {"audience": "upcoming", "preview": True}, format="json").json() == {
        "recipients": 2
    }
    assert host_api.post("/api/host/broadcasts", {"audience": "staff", "preview": True}, format="json").json() == {
        "recipients": 4
    }
    assert host_api.post("/api/host/broadcasts", {"audience": "in_house"}, format="json").status_code == 400  # no text
    with frozen(kenya(days(0), "20:30")):  # operational news may go out any time
        r = host_api.post(
            "/api/host/broadcasts", {"audience": "in_house", "body": "Water off 10-12 tomorrow"}, format="json"
        )
    assert r.status_code == 201 and r.json()["recipients"] == 1
    assert bodies(KE_GUEST, kind="broadcast") == ["Water off 10-12 tomorrow"]
    bc = Broadcast.objects.get()
    assert bc.is_marketing is False and bc.created_by == host and bc.audience == "in_house"
    listed = host_api.get("/api/host/broadcasts").json()
    assert listed[0]["audience_label"] == "Guests staying now" and listed[0]["recipients"] == 1


@pytest.mark.django_db
def test_promotions_respect_the_promo_window_and_stop(host_api, audiences):
    offer = {"audience": "past", "body": "Come back to the coast: 10% off in December!"}
    with frozen(kenya(days(0), "19:15")):
        r = host_api.post("/api/host/broadcasts", offer, format="json")
    assert r.status_code == 400 and r.json()["error"] == "Promotional SMS can only go out between 8:00 and 18:00."
    with frozen(kenya(days(0), "07:59")):
        assert host_api.post("/api/host/broadcasts", offer, format="json").status_code == 400
    with frozen(kenya(days(0), "10:00")):
        r = host_api.post("/api/host/broadcasts", offer, format="json")
    assert r.status_code == 201 and r.json()["recipients"] == 1
    fan, stopped = audiences["fan"], audiences["stopped"]
    assert bodies(fan.phone, kind="broadcast") == [
        "Come back to the coast: 10% off in December! Reply STOP to opt out."
    ]
    assert not bodies(stopped.phone, kind="broadcast")
    assert Message.objects.get(phone=fan.phone, kind="broadcast").is_marketing
    with frozen(kenya(days(0), "11:00")):  # a marketing flag on another audience still skips opted-out guests
        host_api.post(
            "/api/host/broadcasts",
            {"audience": "staff", "body": "Staff party! Reply STOP to opt out", "is_marketing": True},
            format="json",
        )
    assert Broadcast.objects.latest("id").body.endswith("Reply STOP to opt out")  # not appended twice


@pytest.mark.django_db
def test_unknown_broadcast_audience_is_refused(host_api, audiences):
    r = host_api.post("/api/host/broadcasts", {"audience": "everyone", "body": "hello"}, format="json")
    assert r.status_code == 400 and not Broadcast.objects.exists()


# ---------- tasks ----------


@pytest.mark.django_db
def test_tasks_create_assign_start_complete_reopen_and_delete(homes, host_api, host, team, in_house):
    cleaner, caretaker = team["cleaner"], team["caretaker"]
    before = last_id()
    r = host_api.post(
        "/api/host/tasks",
        {
            "type": "turnover",
            "title": "Deep clean - Blue Reef",
            "unit": in_house.unit_id,
            "priority": "high",
            "assignee": cleaner.pk,
            "source": "guest",
        },
        format="json",
    )
    assert r.status_code == 201, r.json()
    t = r.json()
    assert (
        t["source"] == "host"
        and t["created_by"] == host.pk
        and t["assignee_name"] == "Fatuma Ali"
        and t["unit_name"] == "Blue Reef Apartment"
    )
    assert len(t["checklist"]) == 7 and t["type_label"] == "Turnover clean"
    assert bodies(cleaner.phone, before, kind="staff_task") == [
        f"Kazi mpya #{t['id']}: Deep clean - Blue Reef at Blue Reef Apartment, kabla ya today. Jibu DONE {t['id']} ukimaliza."
    ]

    before = last_id()
    r = host_api.patch(f"/api/host/tasks/{t['id']}", {"assignee": caretaker.pk, "priority": "urgent"}, format="json")
    assert r.json()["assignee_name"] == "Juma Mwinyi" and r.json()["priority"] == "urgent"
    assert bodies(caretaker.phone, before, kind="staff_task")
    host_api.patch(f"/api/host/tasks/{t['id']}", {"priority": "normal"}, format="json")
    assert len(bodies(caretaker.phone, before, kind="staff_task")) == 1  # same assignee: not texted again

    assert [x["id"] for x in host_api.get("/api/host/tasks?status=open").json()] == [t["id"]]
    assert host_api.post(f"/api/host/tasks/{t['id']}/start").json()["status"] == "in_progress"
    from apps.properties.models import Unit

    assert Unit.objects.get(pk=in_house.unit_id).housekeeping == "cleaning"
    done = host_api.post(f"/api/host/tasks/{t['id']}/complete", {"note": "Spotless"}, format="json").json()
    assert (
        done["status"] == "done" and done["completion_note"] == "Spotless" and all(c["done"] for c in done["checklist"])
    )
    assert Unit.objects.get(pk=in_house.unit_id).housekeeping == "clean"
    assert host_api.get("/api/host/tasks?status=open").json() == []
    assert [x["id"] for x in host_api.get("/api/host/tasks?status=done").json()] == [t["id"]]
    assert host_api.patch(f"/api/host/tasks/{t['id']}", {"status": "open"}, format="json").json()["status"] == "open"
    assert host_api.delete(f"/api/host/tasks/{t['id']}").status_code == 204
    assert not Task.objects.exists()


@pytest.mark.django_db
def test_completing_a_guest_reported_task_tells_the_guest(homes, host_api, team, in_house):
    sms("PROBLEM the AC is not working")
    task = Task.objects.get()
    before = last_id()
    host_api.post(f"/api/host/tasks/{task.pk}/complete", {}, format="json")
    assert bodies(KE_GUEST, before) == [f"Update on #{task.pk}: Ac has been fixed. Thanks for your patience!"]


# ---------- staff & roles ----------


@pytest.mark.django_db
def test_staff_add_edit_remove_and_re_add(homes, host_api, host):
    roles = host_api.get("/api/host/roles").json()
    assert {r["value"] for r in roles} == {"owner", "manager", "cleaner", "cook", "caretaker", "security", "driver"}
    unit = homes["Old Town Loft"]
    r = host_api.post(
        "/api/host/staff",
        {"phone": "0700 000 031", "name": "Zuhura", "role": "cleaner", "lang": "sw", "unit_ids": [unit.pk]},
        format="json",
    )
    assert r.status_code == 201, r.json()
    sid = r.json()["id"]
    assert r.json()["phone"] == "+254700000031" and r.json()["unit_ids"] == [unit.pk] and r.json()["open_tasks"] == 0
    assert (
        host_api.post("/api/host/staff", {"phone": "12", "name": "X", "role": "cleaner"}, format="json").status_code
        == 400
    )
    assert (
        host_api.post(
            "/api/host/staff", {"phone": "0700000032", "name": "X", "role": "guest"}, format="json"
        ).status_code
        == 400
    )
    assert host_api.patch(f"/api/host/staff/{sid}", {"role": "cook"}, format="json").json()["role"] == "cook"
    assert host_api.patch(f"/api/host/staff/{sid}", {"phone": HOST}, format="json").status_code == 400  # Amina's number

    assert host_api.delete(f"/api/host/staff/{sid}").status_code == 204
    gone = User.objects.get(pk=sid)
    assert gone.role == "guest" and not gone.assigned_units.exists()
    assert sid not in [s["id"] for s in host_api.get("/api/host/staff").json()]
    back = host_api.post(
        "/api/host/staff", {"phone": "+254700000031", "name": "Zuhura", "role": "cleaner"}, format="json"
    )
    assert back.status_code == 201, back.json()  # she's re-hired: same person, same account
    assert back.json()["id"] == sid and User.objects.get(pk=sid).role == "cleaner"
    assert host_api.delete(f"/api/host/staff/{host.pk}").json() == {"error": "You can't remove yourself."}
    demote = host_api.post("/api/host/staff", {"phone": HOST, "name": "Amina", "role": "cleaner"}, format="json")
    assert demote.status_code == 400 and User.objects.get(pk=host.pk).role == "owner"


@pytest.mark.django_db
def test_a_former_guest_can_join_the_team(homes, host_api, wanjiru):
    r = host_api.post("/api/host/staff", {"phone": KE_GUEST, "name": "Wanjiru Kamau", "role": "cook"}, format="json")
    assert r.status_code == 201 and r.json()["id"] == wanjiru.pk
    assert sms("BREAKFAST") == ["No breakfasts booked for tomorrow."]  # her texts are now staff commands


# ---------- kitchen ----------


@pytest.mark.django_db
def test_kitchen_sheet_shows_and_texts_tomorrows_breakfasts(homes, host_api, team, in_house):
    sms("BREAKFAST")
    sms("1 halal")
    tomorrow = days(1)
    k = host_api.get(f"/api/host/kitchen?date={tomorrow}").json()
    assert k["people"] == 2 and k["rows"][0]["style_label"].startswith("Swahili") and k["rows"][0]["dietary"] == "HALAL"
    assert (
        k["text"]
        == f"Breakfasts for {tomorrow:%a} {tomorrow.day} {tomorrow:%b}: 08:00 Blue Reef Apartment: 2x Swahili (HALAL)"
    )
    assert host_api.get(f"/api/host/kitchen?date={days(0)}").json()["rows"] == []  # nobody slept there last night
    before = last_id()
    assert host_api.post("/api/host/kitchen", {"date": str(tomorrow)}, format="json").json() == {
        "sent_to": ["Mama Zawadi"]
    }
    assert bodies(team["cook"].phone, before, kind="kitchen_sheet") == [k["text"]]
    assert host_api.post("/api/host/kitchen", {"date": str(days(9))}, format="json").status_code == 400


# ---------- guest CRM ----------


@pytest.mark.django_db
def test_guest_list_detail_notes_tags_and_do_not_host(homes, host_api, wanjiru, in_house):
    once = make_user("+254799000777", name="One Timer")
    rows = host_api.get("/api/host/guests").json()
    me = next(r for r in rows if r["phone"] == KE_GUEST)
    assert me["stays"] == 1 and me["spend"] == in_house.amount_paid and me["id_registered"] is True
    assert [r["phone"] for r in host_api.get("/api/host/guests?q=wanj").json()] == [KE_GUEST]
    assert host_api.get("/api/host/guests?filter=returning").json() == []

    d = host_api.get(f"/api/host/guests/{wanjiru.pk}").json()
    assert d["bookings"][0]["ref"] == in_house.ref and d["identity"]["last4"].endswith("5678")
    r = host_api.patch(
        f"/api/host/guests/{wanjiru.pk}",
        {"host_notes": "Loves the sea view", "tags": ["VIP", "returning"], "lang": "sw"},
        format="json",
    )
    assert (
        r.json()["notes"] == "Loves the sea view"
        and r.json()["tags"] == ["VIP", "returning"]
        and r.json()["lang"] == "sw"
    )

    host_api.patch(f"/api/host/guests/{once.pk}", {"is_blocked": True, "block_reason": "Party"}, format="json")
    assert [r["phone"] for r in host_api.get("/api/host/guests?filter=blocked").json()] == [once.phone]
    with pytest.raises(bookings.BookingError, match="unable to accept"):
        bookings.create_hold(
            unit=homes["Old Town Loft"],
            guest=User.objects.get(pk=once.pk),
            check_in=days(3),
            check_out=days(4),
            channel="sms",
        )
    assert Activity.objects.filter(kind="guest", title__contains="do-not-host").exists()
    assert host_api.get("/api/host/guests/999999").status_code == 404


# ---------- safety ----------


@pytest.mark.django_db
def test_alerts_list_acknowledge_and_resolve(homes, host_api, host, in_house):
    sos = escalate(KE_GUEST, "web", text="smoke in the kitchen")
    low = raise_alert("low_review", "Low review (2/5)", severity="medium", booking=in_house, notify=False)
    rows = host_api.get("/api/host/alerts").json()
    assert [a["id"] for a in rows] == [low.pk, sos.pk]
    assert (
        rows[1]["kind_label"] == "Guest SOS"
        and rows[1]["booking"] == in_house.ref
        and rows[1]["details"] == "smoke in the kitchen"
    )
    acked = host_api.post(f"/api/host/alerts/{sos.pk}/ack").json()
    assert acked["status"] == "acknowledged" and acked["acknowledged_at"]
    resolved = host_api.post(
        f"/api/host/alerts/{sos.pk}/resolve", {"note": "Toast burnt - all fine"}, format="json"
    ).json()
    assert (
        resolved["status"] == "resolved"
        and resolved["resolved_by"] == "Amina"
        and resolved["resolution_note"] == "Toast burnt - all fine"
    )
    assert [a["id"] for a in host_api.get("/api/host/alerts").json()] == [low.pk]
    assert [a["id"] for a in host_api.get("/api/host/alerts?status=resolved").json()] == [sos.pk]
    assert len(host_api.get("/api/host/alerts?status=all").json()) == 2
    host_api.post(f"/api/host/alerts/{low.pk}/resolve", {}, format="json")
    low.refresh_from_db()
    assert low.status == "resolved" and low.acknowledged_at  # resolving also counts as seen
    assert host_api.post(f"/api/host/alerts/{low.pk}/shout").status_code == 400
    assert host_api.post("/api/host/alerts/999999/ack").status_code == 404


@pytest.mark.django_db
def test_guest_register_json_and_csv(homes, host_api, wanjiru, in_house):
    foreign = make_user("+447700900101", name="Sarah Thompson", nationality="GB")
    stay(homes["Old Town Loft"], foreign, days(1), days(2))
    reg = host_api.get(f"/api/host/compliance/register?from={days(0)}&to={days(5)}").json()
    assert {r["ref"] for r in reg["rows"]} == {in_house.ref, foreign.bookings.get().ref}
    assert reg["missing_id"] == 1  # Sarah hasn't registered her passport yet
    lead = next(r for r in reg["rows"] if r["ref"] == in_house.ref)
    assert lead["phone"] == KE_GUEST and lead["lead_guest"] is True and lead["id_last4"].endswith("5678")
    r = host_api.get(f"/api/host/compliance/register?from={days(0)}&to={days(5)}&export=csv")
    assert r["Content-Type"].startswith("text/csv") and "guest-register-" in r["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode())))
    assert rows[0][:4] == ["Ref", "Home", "Address", "Name"] and len(rows) == 3
    assert host_api.get(f"/api/host/compliance/register?from={days(30)}&to={days(40)}").json()["rows"] == []


# ---------- settings, channels, activity, locks ----------


@pytest.mark.django_db
def test_settings_read_and_change_and_the_new_host_number_takes_over(homes, host_api, wanjiru):
    s = host_api.get("/api/host/settings").json()
    assert s["host_phone"] == HOST and s["deposit_percent"] == 30 and "id" not in s
    r = host_api.patch(
        "/api/host/settings",
        {"deposit_percent": 50, "host_phone": "+254700000002", "promo_window_end": 17},
        format="json",
    )
    assert r.status_code == 200 and r.json()["deposit_percent"] == 50
    assert SiteSettings.load().host_contact == "+254700000002"
    assert host_api.patch("/api/host/settings", {"quiet_hours_start": "late"}, format="json").status_code == 400
    sms("Is the gate locked at midnight?")
    assert bodies("+254700000002", kind="relay") and not bodies(HOST, kind="relay")
    assert sms("Sure", phone="+254700000002") == []  # the new number is treated as Amina
    assert bodies(KE_GUEST)[-1] == "Amina: Sure"
    assert Activity.objects.filter(kind="system", title="Settings updated").exists()


@pytest.mark.django_db
def test_the_numbers_alerts_ring_are_checked_and_kept_in_international_format(host_api):
    r = host_api.patch(
        "/api/host/settings", {"host_phone": "0712 345 678", "backup_phone": "254 733 000 111"}, format="json"
    )
    assert r.status_code == 200 and (r.json()["host_phone"], r.json()["backup_phone"]) == (
        "+254712345678",
        "+254733000111",
    )
    r = host_api.patch("/api/host/settings", {"backup_phone": "call Juma"}, format="json")
    assert r.status_code == 400 and r.json()["error"] == "Backup phone: Enter a valid phone number, e.g. +254712345678."
    assert SiteSettings.load().backup_phone == "+254733000111"
    assert host_api.patch("/api/host/settings", {"backup_phone": ""}, format="json").json()["backup_phone"] == ""


@pytest.mark.django_db
def test_channels_page_shows_callbacks_and_jobs(host_api, settings):
    settings.PUBLIC_URL = "https://amina.example"
    JobRun.objects.create(key="outbox", run_count=3)
    c = host_api.get("/api/host/channels").json()
    sms_product = next(p for p in c["products"] if p["key"] == "sms")
    assert sms_product["callbacks"]["Incoming messages"] == "https://amina.example/at/sms/incoming"
    assert c["configured"] is False and c["balance"] is None and c["webhook_secret"] is False
    assert c["jobs"] == [{"key": "outbox", "last_run_at": None, "ok": True, "runs": 3}]
    settings.AT_WEBHOOK_SECRET = "s3cret"
    ussd = next(p for p in host_api.get("/api/host/channels?balance=1").json()["products"] if p["key"] == "ussd")
    assert ussd["callbacks"]["Callback URL"] == "https://amina.example/at/s3cret/ussd"


@pytest.mark.django_db
def test_activity_feed_filters_and_pages(homes, host_api, wanjiru):
    sms("PRICES")
    from apps.comms.views import process_ussd

    process_ussd(KE_GUEST, "", "s1")
    feed = host_api.get("/api/host/activity").json()
    assert feed[0]["kind"] == "ussd" and any(a["kind"] == "sms" for a in feed)
    assert {a["kind"] for a in host_api.get("/api/host/activity?kind=sms").json()} == {"sms"}
    newest = feed[0]["id"]
    assert host_api.get(f"/api/host/activity?after={newest}").json() == []
    assert len(host_api.get("/api/host/activity?limit=1").json()) == 1


@pytest.mark.django_db
def test_lock_panel_shows_occupancy_and_tests_codes(homes, host_api, in_house, wanjiru):
    code = AccessCode.objects.get(booking=in_house, revoked_at__isnull=True)
    rows = host_api.get("/api/host/locks").json()
    blue = next(r for r in rows if r["unit"]["name"] == "Blue Reef Apartment")
    assert (
        blue["state"] == "occupied"
        and blue["active"]["code"] == code.code
        and blue["active"]["guest"] == "Wanjiru Kamau"
    )
    assert next(r for r in rows if r["unit"]["name"] == "Old Town Loft")["state"] == "vacant"
    upcoming = stay(homes["Old Town Loft"], make_user("+254799000888", name="Next"), days(4), days(5))
    assert (
        next(r for r in host_api.get("/api/host/locks").json() if r["unit"]["name"] == "Old Town Loft")["next"]["ref"]
        == upcoming.ref
    )

    unit = in_house.unit_id
    with frozen(kenya(days(1), "10:00")):
        assert host_api.post("/api/host/locks", {"unit": unit, "code": code.code}, format="json").json() == {
            "unlocked": True,
            "ref": in_house.ref,
        }
        assert (
            host_api.post("/api/host/locks", {"unit": unit, "code": "000000"}, format="json").json()["unlocked"]
            is False
        )
    with frozen(kenya(days(0), "08:00")):  # before check-in time: not yet
        assert (
            host_api.post("/api/host/locks", {"unit": unit, "code": code.code}, format="json").json()["unlocked"]
            is False
        )
    code.refresh_from_db()
    assert code.last_used_at
    bookings.check_out(in_house)
    with frozen(kenya(days(1), "10:00")):
        assert (
            host_api.post("/api/host/locks", {"unit": unit, "code": code.code}, format="json").json()["unlocked"]
            is False
        )
    assert host_api.post("/api/host/locks", {"code": "1"}, format="json").status_code == 404
    assert BookingAddon.objects.count() == 0
    assert timedelta(0) <= code.valid_until - code.valid_from
