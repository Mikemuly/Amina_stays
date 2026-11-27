from django.contrib import admin

from .models import Delivery, Notice


class DeliveryInline(admin.TabularInline):
    model = Delivery
    extra = 0
    readonly_fields = ("phone", "booking", "kind", "created_at")


@admin.register(Notice)
class NoticeAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "service", "kind", "status", "starts_at", "expected_end", "notified")
    list_filter = ("status", "kind", "service")
    search_fields = ("title", "message")
    filter_horizontal = ("units",)
    inlines = [DeliveryInline]
