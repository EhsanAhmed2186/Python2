"""The one place other apps use to create notifications."""
from .models import Notification


def notify(user, message, url="", dedupe_unread=False):
    """
    Create a notification for `user`.
    With dedupe_unread=True, nothing is created if the user already has an
    unread notification pointing to the same url (stops chat spam).
    """
    if dedupe_unread and Notification.objects.filter(user=user, url=url, is_read=False).exists():
        return None
    return Notification.objects.create(user=user, message=message[:255], url=url[:255])


def mark_url_read(user, url):
    """Mark this user's unread notifications for a page as read (used when they open it)."""
    Notification.objects.filter(user=user, url=url, is_read=False).update(is_read=True)
