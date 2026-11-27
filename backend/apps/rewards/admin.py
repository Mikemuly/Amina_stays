from django.contrib import admin

from .models import Member, Payout, PointsEntry, Program


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("__str__", "enabled", "points_per_100", "redeem_points", "redeem_airtime", "monthly_airtime_budget")


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ("code", "user", "referred_by", "referral_status", "created_at")
    list_filter = ("referral_status",)
    search_fields = ("code", "user__phone", "user__name")
    raw_id_fields = ("user", "referred_by", "referral_booking")


@admin.register(PointsEntry)
class PointsEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "points", "reason", "booking", "created_at")
    list_filter = ("reason",)
    raw_id_fields = ("user", "booking", "payout")


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "phone", "kind", "amount", "reason", "status", "created_at")
    list_filter = ("kind", "reason", "status")
    search_fields = ("phone", "provider_ref", "idempotency_key")
    raw_id_fields = ("user", "booking", "created_by")
