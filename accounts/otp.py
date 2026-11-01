from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import PasswordResetOTP

MAX_ATTEMPTS = 5
CODE_LIFETIME = timedelta(minutes=10)
RESEND_WAIT = timedelta(minutes=1)


def invalidate_codes(user):
    PasswordResetOTP.objects.filter(user=user, used=False).update(used=True)


def request_code(user):
    now = timezone.now()
    recently_sent = PasswordResetOTP.objects.filter(
        user=user,
        created_at__gte=now - RESEND_WAIT,
    ).exists()
    if recently_sent:
        return None

    invalidate_codes(user)
    code = f"{secrets.randbelow(1_000_000):06d}"
    PasswordResetOTP.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=now + CODE_LIFETIME,
    )
    return code


def verify_code(user, code):
    with transaction.atomic():
        otp = (
            PasswordResetOTP.objects.select_for_update()
            .filter(user=user, used=False)
            .order_by("-created_at")
            .first()
        )
        if otp is None or otp.expires_at <= timezone.now() or otp.attempts >= MAX_ATTEMPTS:
            return False

        if not check_password(code, otp.code_hash):
            otp.attempts += 1
            if otp.attempts >= MAX_ATTEMPTS:
                otp.used = True
            otp.save(update_fields=["attempts", "used"])
            return False

        otp.used = True
        otp.save(update_fields=["used"])
        return True


def send_code_email(user, code):
    send_mail(
        "Your Haranogiyeche password reset code",
        f"Your password reset code is {code}. It expires in 10 minutes.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def send_password_changed_email(user):
    send_mail(
        "Your Haranogiyeche password was changed",
        "Your password was changed. If you did not make this change, contact support.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )