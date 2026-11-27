from django.contrib import admin

from .models import Ticket, TicketEvent


class TicketEventInline(admin.TabularInline):
    model = TicketEvent
    extra = 0
    readonly_fields = ("kind", "text", "channel", "actor", "created_at")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "status", "priority", "phone", "subject", "channel", "created_at", "rating")
    list_filter = ("status", "category", "priority", "channel")
    search_fields = ("phone", "subject", "description")
    raw_id_fields = ("guest", "booking", "unit", "task", "assignee")
    inlines = [TicketEventInline]
