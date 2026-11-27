from django.contrib import admin

from .models import Activity, JobRun, OnceMarker, SiteSettings

admin.site.register(SiteSettings)
admin.site.register(Activity)
admin.site.register(OnceMarker)
admin.site.register(JobRun)
