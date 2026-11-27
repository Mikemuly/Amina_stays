from django.db import models


class VoiceSession(models.Model):
    """IVR state per Africa's Talking call session (in the DB so any worker can answer the next callback)."""

    session_id = models.CharField(max_length=120, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    direction = models.CharField(max_length=10, default="inbound")
    state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    hangup_cause = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.session_id


class SimSwapCheck(models.Model):
    """Africa's Talking Insights SIM-swap lookups (fraud check before door codes / host logins)."""

    phone = models.CharField(max_length=20, db_index=True)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    request_id = models.CharField(max_length=80, blank=True, db_index=True)
    status = models.CharField(max_length=24, default="Queued")
    last_swap_date = models.DateTimeField(null=True, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
