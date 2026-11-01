from django.contrib import admin

from .models import Comment, Post, Report


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "status", "user", "community", "created_at")
    list_filter = ("type", "status", "community")
    search_fields = ("caption",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "created_at")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "user", "reason", "created_at")
    list_filter = ("reason",)
