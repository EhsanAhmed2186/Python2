from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.access import get_membership, has_community_access
from accounts.models import Membership
from newsfeed.models import Post
from notifications.services import notify

from .forms import ClaimForm, QuestionForm
from .models import ContactRequest, VerificationAnswer, VerificationQuestion
from .utils import answer_matches, hash_answer


# ---------- permission helpers ----------

def _post_for_member(user, post_id):
    """Return (post, membership), or raise 403 if the user is not in the post's community."""
    post = get_object_or_404(Post.objects.select_related("community", "user"), pk=post_id)
    membership = get_membership(user, post.community)
    if not has_community_access(user, post.community):
        raise PermissionDenied
    return post, membership


def _can_review(user, contact):
    """
    Who may see the answers and approve or reject: the receiver, or a community
    admin/moderator. The sender can NEVER review their own request, even if they
    are an admin.
    """
    if getattr(user, "is_superadmin", False):
        return True
    if contact.sender_id == user.id:
        return False
    if contact.receiver_id == user.id:
        return True
    membership = get_membership(user, contact.post.community)
    return membership is not None and membership.role in (
        Membership.Role.ADMIN,
        Membership.Role.MODERATOR,
    )


def _get_request(pk):
    contact = get_object_or_404(
        ContactRequest.objects.select_related("post", "post__community", "sender", "receiver"),
        pk=pk,
    )
    return contact


# ---------- verification questions (post owner) ----------

@login_required
def manage_questions(request, post_id):
    post, _ = _post_for_member(request.user, post_id)
    if post.user_id != request.user.id and not request.user.is_superadmin:
        raise PermissionDenied

    # Once someone has sent a request, questions are frozen so every claimant faced the same ones.
    locked = post.contact_requests.exists()

    if request.method == "POST":
        if locked:
            messages.error(request, "Questions are locked because someone already sent a request.")
            return redirect("verification:manage_questions", post_id=post.pk)
        form = QuestionForm(request.POST)
        if form.is_valid():
            VerificationQuestion.objects.create(
                post=post,
                question=form.cleaned_data["question"],
                answer_hash=hash_answer(form.cleaned_data["expected_answer"]),
            )
            messages.success(request, "Question added.")
            return redirect("verification:manage_questions", post_id=post.pk)
    else:
        form = QuestionForm()

    context = {
        "post": post,
        "form": form,
        "questions": post.verification_questions.all(),
        "locked": locked,
    }
    return render(request, "verification/manage_questions.html", context)


@login_required
@require_POST
def delete_question(request, pk):
    question = get_object_or_404(VerificationQuestion.objects.select_related("post__community"), pk=pk)
    post = question.post
    if not has_community_access(request.user, post.community) or (
        post.user_id != request.user.id and not request.user.is_superadmin
    ):
        raise PermissionDenied

    if post.contact_requests.exists():
        messages.error(request, "Questions are locked because someone already sent a request.")
    else:
        question.delete()
        messages.success(request, "Question deleted.")
    return redirect("verification:manage_questions", post_id=post.pk)


# ---------- claiming a post (sending a contact request) ----------

@login_required
def claim(request, post_id):
    post, _ = _post_for_member(request.user, post_id)

    if post.user_id == request.user.id:
        messages.error(request, "You cannot send a request about your own post.")
        return redirect("newsfeed:post_detail", pk=post.pk)

    existing = ContactRequest.objects.filter(post=post, sender=request.user).first()
    if existing:
        messages.info(request, "You already sent a request for this post.")
        return redirect("verification:request_detail", pk=existing.pk)

    if post.status != Post.Status.ACTIVE:
        messages.error(request, "This post is no longer active.")
        return redirect("newsfeed:post_detail", pk=post.pk)

    questions = list(post.verification_questions.all())

    if request.method == "POST":
        form = ClaimForm(request.POST, questions=questions)
        if form.is_valid():
            try:
                with transaction.atomic():
                    contact = ContactRequest.objects.create(
                        post=post, sender=request.user, receiver=post.user
                    )
                    VerificationAnswer.objects.bulk_create(
                        [
                            VerificationAnswer(
                                request=contact,
                                question=question,
                                answer_text=text,
                                matches_expected=answer_matches(text, question.answer_hash),
                            )
                            for question, text in form.answers()
                        ]
                    )
            except IntegrityError:
                # Double click: the unique rule stopped a second request.
                messages.info(request, "You already sent a request for this post.")
                return redirect("verification:my_requests")

            notify(
                post.user,
                f"{request.user.username} sent a request about your post.",
                url=reverse("verification:request_detail", args=[contact.pk]),
            )
            messages.success(request, "Request sent. The owner will review it.")
            return redirect("verification:request_detail", pk=contact.pk)
    else:
        form = ClaimForm(questions=questions)

    context = {"post": post, "form": form, "has_questions": bool(questions)}
    return render(request, "verification/claim_form.html", context)


# ---------- reviewing a request ----------

@login_required
def request_detail(request, pk):
    contact = _get_request(pk)
    is_sender = contact.sender_id == request.user.id
    can_review = _can_review(request.user, contact)
    if not (is_sender or can_review):
        raise PermissionDenied

    # The claimant never sees stored answers or match flags. Only reviewers do.
    answers = list(contact.answers.select_related("question")) if can_review else []

    context = {
        "contact": contact,
        "post": contact.post,
        "answers": answers,
        "is_sender": is_sender,
        "can_review": can_review,
        "can_decide": can_review and contact.status == ContactRequest.Status.PENDING,
        "can_chat": contact.status == ContactRequest.Status.APPROVED
        and contact.is_participant(request.user),
    }
    return render(request, "verification/request_detail.html", context)


def _decide(request, pk, new_status):
    contact = _get_request(pk)
    if not _can_review(request.user, contact):
        raise PermissionDenied

    # Only a request that is still pending can change. The filter makes this safe
    # even if two reviewers click at the same moment.
    changed = ContactRequest.objects.filter(
        pk=contact.pk, status=ContactRequest.Status.PENDING
    ).update(status=new_status, updated_at=timezone.now())

    if not changed:
        messages.error(request, "This request has already been decided.")
        return redirect("verification:request_detail", pk=contact.pk)

    if new_status == ContactRequest.Status.APPROVED:
        notify(
            contact.sender,
            f"Your request was approved. You can now message {contact.receiver.username}.",
            url=reverse("messaging:conversation", args=[contact.pk]),
        )
        messages.success(request, "Request approved. Both of you can now exchange messages.")
    else:
        notify(
            contact.sender,
            "Your request was not approved.",
            url=reverse("verification:request_detail", args=[contact.pk]),
        )
        messages.success(request, "Request rejected.")
    return redirect("verification:request_detail", pk=contact.pk)


@login_required
@require_POST
def approve(request, pk):
    return _decide(request, pk, ContactRequest.Status.APPROVED)


@login_required
@require_POST
def reject(request, pk):
    return _decide(request, pk, ContactRequest.Status.REJECTED)


@login_required
def my_requests(request):
    received = (
        ContactRequest.objects.select_related("post", "sender", "receiver")
        if request.user.is_superadmin
        else request.user.received_requests.select_related("post", "sender")
    )
    context = {
        "received": received,
        "sent": request.user.sent_requests.select_related("post", "receiver"),
        "is_superadmin": request.user.is_superadmin,
    }
    return render(request, "verification/request_list.html", context)
