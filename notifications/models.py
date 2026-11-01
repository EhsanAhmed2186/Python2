from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.CharField(max_length=255)
    # Where the notification leads (an internal path such as "/requests/3/").
    url = models.CharField(max_length=255, blank=True)
    is_read = models.BooleanField(default=False)
    # Reserved for the optional email feature (P2). Always False for now.
    mail_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"To {self.user}: {self.message[:40]}"
