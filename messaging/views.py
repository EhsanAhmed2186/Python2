from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from notifications.services import mark_url_read
from verification.models import ContactRequest

from .forms import MessageForm
from .models import Message


def _conversation_or_403(user, request_id):
    """
    The single gate for every private conversation: the contact request must be
    APPROVED and the user must be its sender or receiver. Anyone else gets 403.
    """
    contact = get_object_or_404(
        ContactRequest.objects.select_related("post", "sender", "receiver"), pk=request_id
    )
    if contact.status != ContactRequest.Status.APPROVED or not contact.is_participant(user):
        raise PermissionDenied
    return contact


@login_required
def inbox(request):
    user = request.user

    latest = Message.objects.filter(request=OuterRef("pk")).order_by("-created_at")
    conversations = (
        ContactRequest.objects.filter(status=ContactRequest.Status.APPROVED)
        .filter(Q(sender=user) | Q(receiver=user))
        .select_related("post", "sender", "receiver")
        .annotate(
            last_message=Subquery(latest.values("content")[:1]),
            last_message_at=Subquery(latest.values("created_at")[:1]),
        )
        .order_by(F("last_message_at").desc(nulls_last=True), "-updated_at")
    )

    unread = dict(
        Message.objects.filter(receiver=user, is_read=False)
        .order_by()
        .values("request")
        .annotate(total=Count("id"))
        .values_list("request", "total")
    )

    items = []
    for contact in conversations:
        contact.other = contact.other_party(user)
        contact.unread = unread.get(contact.pk, 0)
        items.append(contact)

    return render(request, "messaging/inbox.html", {"conversations": items})


@login_required
def conversation(request, request_id):
    contact = _conversation_or_403(request.user, request_id)
    other = contact.other_party(request.user)
    conversation_url = reverse("messaging:conversation", args=[contact.pk])

    if request.method == "POST":
        form = MessageForm(request.POST)
        if form.is_valid():
            Message.objects.create(
                request=contact,
                sender=request.user,
                receiver=other,
                content=form.cleaned_data["content"],
            )
            # No notification row for chat: the receiver gets a live popup and the Inbox badge.
            return redirect("messaging:conversation", request_id=contact.pk)
    else:
        form = MessageForm()

    # Opening the page marks the incoming messages (and their notification) as read.
    contact.chat_messages.filter(receiver=request.user, is_read=False).update(is_read=True)
    mark_url_read(request.user, conversation_url)

    context = {
        "contact": contact,
        "other": other,
        "post": contact.post,
        "chat": contact.chat_messages.select_related("sender"),
        "form": form,
    }
    return render(request, "messaging/conversation.html", context)
