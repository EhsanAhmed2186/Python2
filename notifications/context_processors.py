"""Adds the unread counters (and the 'what is already seen' markers) to every template."""
from django.db.models import Max

from .models import Notification


def unread_counts(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    # Imported here to keep the apps loosely coupled.
    from messaging.models import Message
    from verification.models import ContactRequest

    return {
        "unread_notifications": Notification.objects.filter(user=user, is_read=False).count(),
        "unread_messages": Message.objects.filter(receiver=user, is_read=False).count(),
        "pending_requests": ContactRequest.objects.filter(
            receiver=user, status=ContactRequest.Status.PENDING
        ).count(),
        # Newest ids at page load. The live script only pops up items newer than these.
        "latest_notification_id": Notification.objects.filter(user=user).aggregate(
            latest=Max("id")
        )["latest"]
        or 0,
        "latest_message_id": Message.objects.filter(receiver=user).aggregate(latest=Max("id"))[
            "latest"
        ]
        or 0,
    }
