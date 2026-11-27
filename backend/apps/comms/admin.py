from django.contrib import admin

from .models import SimSwapCheck, VoiceSession

admin.site.register(VoiceSession)
admin.site.register(SimSwapCheck)
