from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts import views as accounts
from apps.bookings import views as bookings
from apps.comms import views as comms
from apps.core import views as core
from apps.guide import views as guide
from apps.insights import views as insights
from apps.messaging import views as messaging
from apps.notices import views as notices
from apps.operations import views as operations
from apps.payments import views as payments
from apps.properties import views as properties
from apps.reviews import views as reviews
from apps.rewards import views as rewards
from apps.safety import views as safety
from apps.support import views as support

router = DefaultRouter(trailing_slash=False)
router.register("host/listings", properties.HostUnitViewSet, basename="host-listings")
router.register("host/price-rules", properties.PriceRuleViewSet, basename="host-price-rules")
router.register("host/blocks", properties.BlockViewSet, basename="host-blocks")
router.register("host/ical-feeds", properties.ICalFeedViewSet, basename="host-ical-feeds")
router.register("host/amenities", properties.AmenityViewSet, basename="host-amenities")
router.register("host/addons", bookings.HostAddonViewSet, basename="host-addons")
router.register("host/tasks", operations.TaskViewSet, basename="host-tasks")
router.register("host/staff", operations.StaffViewSet, basename="host-staff")
router.register("host/automations", messaging.AutomationViewSet, basename="host-automations")
router.register("host/faqs", messaging.FAQViewSet, basename="host-faqs")
router.register("host/guide/places", guide.HostPlaceViewSet, basename="host-guide-places")
router.register("host/guide/events", guide.HostEventViewSet, basename="host-guide-events")

api = [
    # public
    path("config", core.config),
    path("areas", properties.areas),
    path("amenities", properties.amenities),
    path("addons", properties.addons),
    path("faqs", messaging.public_faqs),
    path("listings", properties.listings),
    path("listings/<slug:slug>", properties.listing),
    path("listings/<slug:slug>/calendar", properties.calendar),
    path("listings/<slug:slug>/quote", properties.quote),
    path("listings/<slug:slug>/reviews", properties.listing_reviews),
    path("ical/<str:token>.ics", properties.ical_export),
    path("guide", guide.guide),
    path("guide/nearby/<slug:slug>", guide.nearby),
    path("notices", notices.unit_notices),
    # auth & account
    path("auth/csrf", accounts.csrf),
    path("auth/otp/request", accounts.otp_request),
    path("auth/otp/verify", accounts.otp_verify),
    path("auth/logout", accounts.logout_view),
    path("auth/me", accounts.me),
    path("me", accounts.me),
    path("me/identity", accounts.identity),
    path("me/export", accounts.export),
    path("me/erase", accounts.erase),
    path("me/wishlist", accounts.wishlist),
    path("me/wishlist/<slug:slug>", accounts.wishlist_remove),
    path("me/waitlist", bookings.my_waitlist),
    path("me/waitlist/<int:pk>", bookings.my_waitlist_remove),
    path("waitlist", bookings.waitlist_join),
    path("messages", messaging.my_messages),
    path("me/rewards", rewards.my_rewards),
    path("me/rewards/redeem", rewards.my_redeem),
    path("me/rewards/referral", rewards.my_referral),
    path("support/tickets", support.my_tickets),
    path("support/tickets/<int:pk>/rate", support.rate_ticket),
    # trips
    path("bookings", bookings.bookings),
    path("bookings/<str:ref>", bookings.booking_detail),
    path("bookings/<str:ref>/pay", bookings.pay),
    path("bookings/<str:ref>/cancel", bookings.cancel),
    path("bookings/<str:ref>/extras", bookings.add_extra),
    path("bookings/<str:ref>/breakfast", bookings.breakfast),
    path("bookings/<str:ref>/occupants", bookings.occupants),
    path("bookings/<str:ref>/checkout", bookings.checkout),
    path("bookings/<str:ref>/issues", bookings.report_issue),
    path("bookings/<str:ref>/sos", bookings.sos),
    path("bookings/<str:ref>/review", bookings.review),
    path("bookings/<str:ref>/change", bookings.change),
    path("bookings/<str:ref>/change/<int:pk>/pay", bookings.change_pay),
    path("bookings/<str:ref>/change/<int:pk>/cancel", bookings.change_cancel),
    path("bookings/<str:ref>/invoice", payments.invoice),
    path("bookings/<str:ref>/claim", payments.claim),
    # payments
    path("pay/card/<str:token>", payments.card_checkout),
    path("payments/at/callback", payments.at_callback),
    path("payments/at/callback/<str:secret>", payments.at_callback),
    path("payments/daraja/callback/<str:secret>", payments.daraja_callback),
    path("payments/daraja/c2b/<str:kind>/<str:secret>", payments.c2b_callback),
    path("payments/paystack/webhook", payments.paystack_webhook),
    path("payments/stripe/webhook", payments.stripe_webhook),
    # host console
    path("host/today", insights.today_view),
    path("host/insights", insights.insights),
    path("host/compliance/tra-return", insights.tra_return),
    path("host/compliance/register", safety.guest_register),
    path("host/calendar", properties.host_calendar),
    path("host/prices", properties.set_prices),
    path("host/reservations", bookings.host_reservations),
    path("host/reservations/<str:ref>", bookings.host_reservation),
    path("host/reservations/<str:ref>/<str:action>", bookings.host_action),
    path("host/requests", bookings.pending_requests),
    path("host/requests/<int:pk>/decide", bookings.decide_request),
    path("host/changes/<int:pk>/decide", bookings.decide_change),
    path("host/inbox", messaging.inbox),
    path("host/inbox/<int:pk>", messaging.inbox_thread),
    path("host/inbox/<int:pk>/reply", messaging.inbox_reply),
    path("host/inbox/<int:pk>/resolve", messaging.inbox_resolve),
    path("host/templates", messaging.templates),
    path("host/templates/<str:key>/<str:lang>", messaging.template_edit),
    path("host/automations/<int:pk>/preview", messaging.automation_preview),
    path("host/faq-test", messaging.faq_test),
    path("host/broadcasts", messaging.broadcasts),
    path("host/guests", operations.guests),
    path("host/guests/<int:pk>", operations.guest_detail),
    path("host/roles", operations.roles),
    path("host/kitchen", operations.kitchen),
    path("host/payments", payments.ledger),
    path("host/payments/unmatched/<int:pk>/match", payments.match_unmatched),
    path("host/invoices", payments.host_invoices),
    path("host/refunds/<int:pk>/sent", payments.refund_sent),
    path("host/reviews", reviews.host_reviews),
    path("host/reviews/<int:pk>/respond", reviews.respond),
    path("host/alerts", safety.alerts),
    path("host/alerts/<int:pk>/<str:action>", safety.alert_action),
    path("host/settings", core.host_settings),
    path("host/channels", core.channels),
    path("host/activity", core.activity),
    path("host/locks", core.locks),
    path("host/support/tickets", support.host_tickets),
    path("host/support/tickets/<int:pk>", support.host_ticket),
    path("host/support/tickets/<int:pk>/<str:action>", support.host_ticket_action),
    path("host/notices", notices.notices),
    path("host/notices/preview", notices.preview),
    path("host/notices/<int:pk>/<str:action>", notices.notice_action),
    path("host/rewards", rewards.host_rewards),
    path("host/rewards/program", rewards.host_program),
    path("host/rewards/payouts/<int:pk>/<str:action>", rewards.host_payout_action),
    path("host/rewards/send", rewards.host_send),
    path("", include(router.urls)),
    # demo lab (DEMO=1 only)
    path("demo/sms", comms.demo_sms),
    path("demo/phone/<str:phone>", comms.demo_phone),
    path("demo/ussd", comms.demo_ussd),
    path("demo/voice", comms.demo_voice),
    path("demo/pay/<str:ref>", core.demo_pay),
    path("demo/c2b", core.demo_c2b),
    path("demo/tick", core.demo_tick),
    path("demo/advance/<str:ref>", core.demo_advance),
    path("demo/reset", core.demo_reset),
    path("demo/outage/<str:ref>", core.demo_outage),
    path("demo/ical/<slug:slug>.ics", core.demo_ical),
    # API docs
    path("schema", SpectacularAPIView.as_view(), name="schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="schema")),
]

# Africa's Talking callbacks: /at/<secret>/… when AT_WEBHOOK_SECRET is set, /at/… otherwise
at_hooks = [
    ("sms/incoming", comms.sms_incoming),
    ("sms/delivery", comms.sms_delivery),
    ("sms/optout", comms.sms_optout),
    ("ussd", comms.ussd_callback),
    ("ussd/events", comms.ussd_events),
    ("voice", comms.voice_callback),
    ("airtime/status", comms.airtime_status),
    ("data/status", comms.data_status),
    ("insights/simswap", comms.simswap_callback),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", core.health),
    path("api/", include(api)),
    *[path(f"at/{route}", view) for route, view in at_hooks],
    *[path(f"at/<str:secret>/{route}", view) for route, view in at_hooks],
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "Amina Stays — data admin"
admin.site.site_title = "Amina Stays admin"
