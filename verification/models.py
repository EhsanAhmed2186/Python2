from django.conf import settings
from django.db import models
from django.db.models import F, Q


class VerificationQuestion(models.Model):
    post = models.ForeignKey(
        "newsfeed.Post",
        on_delete=models.CASCADE,
        related_name="verification_questions",
    )
    question = models.CharField(max_length=300)
    # The owner's expected answer is NEVER stored as readable text, only as a salted hash.
    answer_hash = models.CharField(max_length=255, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.question[:60]

    @property
    def has_expected_answer(self):
        return bool(self.answer_hash)


class ContactRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    post = models.ForeignKey(
        "newsfeed.Post",
        on_delete=models.CASCADE,
        related_name="contact_requests",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sent_requests",
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_requests",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # One request per person per post.
            models.UniqueConstraint(fields=["post", "sender"], name="unique_request_per_sender_post"),
            # Nobody can send a request to themselves.
            models.CheckConstraint(
                condition=~Q(sender=F("receiver")), name="request_sender_is_not_receiver"
            ),
        ]

    def __str__(self):
        return f"Request {self.pk}: {self.sender} -> {self.receiver} ({self.status})"

    def is_participant(self, user):
        return user.id in (self.sender_id, self.receiver_id)

    def other_party(self, user):
        return self.receiver if user.id == self.sender_id else self.sender


class VerificationAnswer(models.Model):
    """
    What the claimant typed for each question. Only the post owner and community
    moderators can see it. matches_expected is None when the owner set no expected answer.
    """

    request = models.ForeignKey(ContactRequest, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(VerificationQuestion, on_delete=models.CASCADE, related_name="answers")
    answer_text = models.CharField(max_length=500)
    matches_expected = models.BooleanField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["request", "question"], name="unique_answer_per_question")
        ]

    def __str__(self):
        return f"Answer to question {self.question_id} on request {self.request_id}"
