from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Message(models.Model):
    class MessageType(models.TextChoices):
        TEXT = "text", "Text"
        SYSTEM = "system", "System"

    # A message always belongs to a contact request. The conversation page only
    # opens for APPROVED requests, and only for the two participants.
    request = models.ForeignKey(
        "verification.ContactRequest",
        on_delete=models.CASCADE,
        related_name="chat_messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_messages",
    )
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    message_type = models.CharField(
        max_length=10, choices=MessageType.choices, default=MessageType.TEXT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(sender=F("receiver")), name="message_sender_is_not_receiver"
            )
        ]

    def __str__(self):
        return f"Message {self.pk} on request {self.request_id}"
