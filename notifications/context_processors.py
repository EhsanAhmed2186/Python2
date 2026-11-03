"""Adds per-user live-update markers to authenticated pages."""
from django.db.models import Max

from .models import Notification


def unread_counts(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}

    # Imported here to keep the apps loosely coupled.
    from messaging.models import Message
    return {
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
