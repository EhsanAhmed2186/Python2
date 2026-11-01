from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .access import get_membership
from .forms import (
    AvatarForm,
    CommunityForm,
    JoinCommunityForm,
    OTPForm,
    PasswordResetRequestForm,
    RegistrationForm,
    ResetPasswordForm,
)
from .models import Community, Membership, User
from .otp import (
    invalidate_codes,
    request_code,
    send_code_email,
    send_password_changed_email,
    verify_code,
)


def _safe_next(request):
    """The page to return to after registering, but only if it is on this site."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return ""


# ---------- public pages (guests allowed) ----------

def home(request):
    """Guests see a welcome page. Logged-in users see their own communities."""
    if request.user.is_authenticated:
        memberships = (
            Membership.objects.filter(user=request.user)
            .select_related("community")
            .order_by("community__name")
        )
        return render(request, "home.html", {"memberships": memberships})

    featured = Community.objects.annotate(member_count=Count("memberships")).order_by(
        "-member_count", "name"
    )[:6]
    return render(request, "landing.html", {"featured": featured})


def community_list(request):
    """
    Public list of communities: name and member count only. Join codes, admins,
    members and posts are never shown here. Joining still needs an account AND the code.
    """
    query = request.GET.get("q", "").strip()
    communities = Community.objects.annotate(member_count=Count("memberships"))
    if query:
        communities = communities.filter(name__icontains=query)

    my_ids = set()
    if request.user.is_authenticated:
        my_ids = set(request.user.memberships.values_list("community_id", flat=True))

    items = list(communities)
    for community in items:
        community.is_member = community.pk in my_ids

    return render(request, "accounts/community_list.html", {"communities": items, "query": query})


def about(request):
    return render(request, "accounts/about.html")


# ---------- accounts ----------

def register(request):
    next_url = _safe_next(request)
    if request.user.is_authenticated:
        return redirect(next_url or "home")

    if request.method == "POST":
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Welcome to Haranogiyeche! Your account has been created.")
            return redirect(next_url or "home")
    else:
        form = RegistrationForm()

    return render(request, "accounts/register.html", {"form": form, "next": next_url})


def _delete_stored_file(field_file):
    if field_file and field_file.name:
        field_file.storage.delete(field_file.name)


@login_required
def profile(request):
    """Your own profile. You can only ever change your own photo."""
    user = request.user
    # Remember the current photo first: validating the form swaps in the new one.
    old_name = user.avatar.name if user.avatar else ""
    form = AvatarForm(instance=user)

    if request.method == "POST":
        if "remove_avatar" in request.POST:
            _delete_stored_file(user.avatar)
            user.avatar = None
            user.save(update_fields=["avatar"])
            messages.success(request, "Your profile photo was removed.")
            return redirect("profile")

        form = AvatarForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            user = form.save()
            if old_name and old_name != user.avatar.name:
                user.avatar.storage.delete(old_name)  # do not keep unused old photos
            messages.success(request, "Your profile photo was updated.")
            return redirect("profile")

    memberships = (
        Membership.objects.filter(user=request.user)
        .select_related("community")
        .order_by("community__name")
    )
    context = {
        "form": form,
        "memberships": memberships,
        "post_count": request.user.posts.count(),
    }
    return render(request, "accounts/profile.html", context)


# ---------- communities (logged-in users) ----------

@login_required
def create_community(request):
    """The logged-in user becomes the admin (never taken from the form)."""
    if request.method == "POST":
        form = CommunityForm(request.POST)
        if form.is_valid():
            community = form.save(commit=False)
            community.admin = request.user
            community.save()  # Community.save() also creates the admin Membership
            messages.success(request, f"Community “{community.name}” created.")
            return redirect("accounts:community_detail", pk=community.pk)
    else:
        form = CommunityForm()

    return render(request, "accounts/community_form.html", {"form": form})


@login_required
def join_community(request):
    """Join with a code. A wrong code or a repeat join never creates anything bad."""
    if request.method == "POST":
        form = JoinCommunityForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["join_code"]
            community = Community.objects.filter(join_code=code).first()

            if community is None:
                form.add_error("join_code", "No community found with that code.")
            else:
                _, created = Membership.objects.get_or_create(
                    user=request.user,
                    community=community,
                    defaults={"role": Membership.Role.MEMBER},
                )
                if created:
                    messages.success(request, f"You joined “{community.name}”.")
                else:
                    messages.info(request, f"You are already a member of “{community.name}”.")
                return redirect("accounts:community_detail", pk=community.pk)
    else:
        form = JoinCommunityForm()

    return render(request, "accounts/join_community.html", {"form": form})


@login_required
def community_detail(request, pk):
    """Members only."""
    community = get_object_or_404(Community, pk=pk)
    membership = get_membership(request.user, community)
    if membership is None:
        raise PermissionDenied  # shows Django's 403 page

    members = community.memberships.select_related("user").order_by("user__username")
    context = {
        "community": community,
        "membership": membership,
        "is_admin": membership.role == Membership.Role.ADMIN,
        "members": members,
    }
    return render(request, "accounts/community_detail.html", context)


# ---------- forgot password (code sent by email) ----------

RESET_EMAIL_KEY = "reset_email"
RESET_USER_KEY = "reset_user_id"
RESET_TIME_KEY = "reset_verified_at"
RESET_WINDOW_SECONDS = 10 * 60  # time allowed to choose the new password after the code is accepted


def _clear_reset_session(request):
    for key in (RESET_EMAIL_KEY, RESET_USER_KEY, RESET_TIME_KEY):
        request.session.pop(key, None)


def password_reset_request(request):
    """Step 1: ask for an email. The answer is the same whether or not the account exists."""
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            user = User.objects.filter(email__iexact=email, is_active=True).order_by("pk").first()
            if user:
                code = request_code(user)  # None when asked too often
                if code:
                    send_code_email(user, code)

            request.session[RESET_EMAIL_KEY] = email
            request.session.pop(RESET_USER_KEY, None)
            messages.info(
                request,
                "If an account exists for that email, a 6-digit code has been sent. "
                "It expires in 10 minutes.",
            )
            return redirect("accounts:password_reset_verify")
    else:
        form = PasswordResetRequestForm()

    return render(request, "accounts/password_reset_request.html", {"form": form})


def password_reset_verify(request):
    """Step 2: enter the emailed code."""
    if request.user.is_authenticated:
        return redirect("home")

    email = request.session.get(RESET_EMAIL_KEY)
    if not email:
        return redirect("accounts:password_reset_request")

    if request.method == "POST":
        form = OTPForm(request.POST)
        if form.is_valid():
            user = User.objects.filter(email__iexact=email, is_active=True).order_by("pk").first()
            if user and verify_code(user, form.cleaned_data["code"]):
                request.session.cycle_key()  # fresh session id once the code is accepted
                request.session[RESET_USER_KEY] = user.pk
                request.session[RESET_TIME_KEY] = timezone.now().timestamp()
                return redirect("accounts:password_reset_new")
            form.add_error("code", "That code is invalid or has expired.")
    else:
        form = OTPForm()

    return render(request, "accounts/password_reset_verify.html", {"form": form, "email": email})


def password_reset_new(request):
    """Step 3: choose a new password. Only reachable right after a correct code."""
    if request.user.is_authenticated:
        return redirect("home")

    user_id = request.session.get(RESET_USER_KEY)
    stamp = request.session.get(RESET_TIME_KEY)
    expired = not user_id or not stamp or timezone.now().timestamp() - stamp > RESET_WINDOW_SECONDS
    user = None if expired else User.objects.filter(pk=user_id, is_active=True).first()

    if user is None:
        _clear_reset_session(request)
        messages.error(request, "Your reset session has expired. Please start again.")
        return redirect("accounts:password_reset_request")

    if request.method == "POST":
        form = ResetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            invalidate_codes(user)
            _clear_reset_session(request)
            send_password_changed_email(user)
            messages.success(request, "Your password was changed. You can log in now.")
            return redirect("accounts:login")
    else:
        form = ResetPasswordForm(user)

    return render(request, "accounts/password_reset_new.html", {"form": form})
