from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

RATING = [MinValueValidator(1), MaxValueValidator(5)]
CATEGORIES = ("cleanliness", "accuracy", "check_in", "communication", "location", "value")


class Review(models.Model):
    """Verified-stay reviews only (one per completed booking), with Airbnb-style category ratings."""

    booking = models.OneToOneField("bookings.Booking", on_delete=models.CASCADE, related_name="review")
    unit = models.ForeignKey("properties.Unit", on_delete=models.CASCADE, related_name="reviews")
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=RATING)
    cleanliness = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING)
    accuracy = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING)
    check_in = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING)
    communication = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING)
    location = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING)
    value = models.PositiveSmallIntegerField(null=True, blank=True, validators=RATING)
    comment = models.TextField(blank=True)
    host_response = models.TextField(blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    channel = models.CharField(max_length=6, default="sms")
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rating}★ {self.booking_id}"
