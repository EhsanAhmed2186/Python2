from django.conf import settings
from django.db import models

from newsfeed.storage import PrivateMediaStorage


class Post(models.Model):
    class PostType(models.TextChoices):
        LOST = "lost", "Lost"
        FOUND = "found", "Found"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RETURNED = "returned", "Returned"
        CLOSED = "closed", "Closed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    community = models.ForeignKey(
        "accounts.Community",
        on_delete=models.CASCADE,
        related_name="posts",
    )
    type = models.CharField(max_length=10, choices=PostType.choices)
    caption = models.TextField()
    image = image = models.ImageField(
    upload_to="post_images/%Y/%m/",
    storage=PrivateMediaStorage(),
    blank=True,
    null=True,
)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_type_display()}: {self.caption[:40]}"


class Comment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.user} on post {self.post_id}"


class Report(models.Model):
    class Reason(models.TextChoices):
        SPAM = "spam", "Spam"
        SUSPICIOUS = "suspicious", "Suspicious or fake claim"
        INAPPROPRIATE = "inappropriate", "Inappropriate content"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # One report per user per post, so nobody can flood a post with reports.
            models.UniqueConstraint(fields=["user", "post"], name="unique_report_per_user_post")
        ]

    def __str__(self):
        return f"Report on post {self.post_id} ({self.reason})"
