"""
Small helpers that answer "what is this user allowed to do in this community?".
Other apps (newsfeed, verification, messaging) should import these instead of
re-writing the same checks, so the rules stay identical everywhere.
"""
from .models import Membership


def get_membership(user, community):
    """Return the user's Membership in this community, or None."""
    if not user.is_authenticated:
        return None
    return Membership.objects.filter(user=user, community=community).first()


def has_community_access(user, community):
    return bool(user.is_authenticated and (user.is_superadmin or get_membership(user, community)))


def is_member(user, community):
    return has_community_access(user, community)


def is_community_admin(user, community):
    if user.is_authenticated and user.is_superadmin:
        return True
    membership = get_membership(user, community)
    return membership is not None and membership.role == Membership.Role.ADMIN
