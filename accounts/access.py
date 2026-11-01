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


def is_member(user, community):
    return get_membership(user, community) is not None


def is_community_admin(user, community):
    membership = get_membership(user, community)
    return membership is not None and membership.role == Membership.Role.ADMIN
