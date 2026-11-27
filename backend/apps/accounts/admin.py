from django.contrib import admin

from .models import OTPCode, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("phone", "name", "role", "lang", "nationality", "is_blocked", "date_joined")
    list_filter = ("role", "lang", "is_blocked")
    search_fields = ("phone", "name", "email")
    exclude = ("password", "id_number_enc")


admin.site.register(OTPCode)
