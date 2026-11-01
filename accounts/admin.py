from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Community, Membership, User

admin.site.register(User, UserAdmin)


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ("name", "join_code", "admin", "created_at")
    search_fields = ("name", "join_code")
    readonly_fields = ("join_code",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "community", "role", "joined_at")
    list_filter = ("role", "community")
