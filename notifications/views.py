from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import Notification


@login_required
def notification_list(request):
    # Always filtered by the logged-in user: nobody sees anyone else's notifications.
    items = Notification.objects.filter(user=request.user)[:50]
    return render(request, "notifications/notification_list.html", {"items": items})


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("notifications:list")


@login_required
def open_notification(request, pk):
    # A notification that belongs to someone else behaves like "not found".
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    target = notification.url
    safe = target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )
    return redirect(target if safe else reverse("notifications:list"))


def _to_int(value):
    """Query-string number, or 0 if it is missing or not a valid non-negative number."""
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


@login_required
@require_GET
@never_cache
def poll(request):
    """
    Called every few seconds by static/js/live.js. Returns ONLY the logged-in user's
    own new notifications and incoming messages newer than the ids the page knows.
    """
    # Imported here so the notifications app stays loosely coupled to the others.
    from messaging.models import Message
    user = request.user
    last_notification = _to_int(request.GET.get("n"))
    last_message = _to_int(request.GET.get("m"))
    open_conversation = _to_int(request.GET.get("open"))

    new_notifications = list(
        Notification.objects.filter(user=user, id__gt=last_notification).order_by("id")[:20]
    )
    new_messages = list(
        Message.objects.filter(receiver=user, id__gt=last_message)
        .select_related("sender")
        .order_by("id")[:20]
    )

    # Messages for the conversation the user is looking at right now are shown live
    # on that page, so they count as read.
    if open_conversation:
        visible = [m.pk for m in new_messages if m.request_id == open_conversation]
        if visible:
            Message.objects.filter(pk__in=visible, receiver=user).update(is_read=True)

    data = {
        "notifications": [
            {
                "id": n.pk,
                "message": n.message,
                "url": reverse("notifications:open", args=[n.pk]),
            }
            for n in new_notifications
        ],
        "messages": [
            {
                "id": m.pk,
                "request_id": m.request_id,
                "sender": m.sender.username,
                "content": m.content,
                "time": timezone.localtime(m.created_at).strftime("%b %d, %H:%M"),
                "url": reverse("messaging:conversation", args=[m.request_id]),
            }
            for m in new_messages
        ],
        "last_notification_id": new_notifications[-1].pk if new_notifications else last_notification,
        "last_message_id": new_messages[-1].pk if new_messages else last_message,
    }
    return JsonResponse(data)
