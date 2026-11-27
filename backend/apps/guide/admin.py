from django.contrib import admin

from .models import Event, Place


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "area", "featured", "active", "hits")
    list_filter = ("category", "area", "featured", "active")
    search_fields = ("name", "summary")


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "weekday", "starts_on", "yearly", "active")
    list_filter = ("active", "yearly")
    search_fields = ("title",)
