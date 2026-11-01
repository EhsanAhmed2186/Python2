from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "request", "sender", "receiver", "message_type", "is_read", "created_at")
    list_filter = ("message_type", "is_read")
