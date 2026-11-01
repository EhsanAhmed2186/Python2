from django.contrib import admin

from .models import ContactRequest, VerificationAnswer, VerificationQuestion


@admin.register(VerificationQuestion)
class VerificationQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "question", "created_at")


@admin.register(ContactRequest)
class ContactRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "sender", "receiver", "status", "created_at")
    list_filter = ("status",)


@admin.register(VerificationAnswer)
class VerificationAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "request", "question", "matches_expected")
