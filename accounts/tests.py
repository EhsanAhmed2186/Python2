import os
import re
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from .models import Community, Membership, PasswordResetOTP
from .otp import MAX_ATTEMPTS, request_code, verify_code

User = get_user_model()
STRONG_PASSWORD = "Str0ng-Pass-9271!"


class PublicPagesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin1", "admin1@example.com")
        self.member = User.objects.create_user("member", "member@example.com")
        self.outsider = User.objects.create_user("outsider", "outsider@example.com")
        self.community = Community.objects.create(name="Test Uni", admin=self.admin)
        Membership.objects.create(user=self.member, community=self.community)

    def test_guest_sees_landing_page_with_theme_toggle(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Browse communities")
        self.assertContains(response, 'id="themeToggle"')
        self.assertNotContains(response, "My Communities")

    def test_logged_in_user_sees_own_communities_on_home(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "My Communities")
        self.assertContains(response, "Test Uni")

    def test_guest_can_list_communities_without_private_data(self):
        response = self.client.get(reverse("community_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Uni")
        self.assertNotContains(response, self.community.join_code)
        self.assertNotContains(response, "admin1")

    def test_guest_must_register_to_join(self):
        response = self.client.get(reverse("community_list"))
        self.assertContains(response, "Register to join")
        self.assertContains(response, reverse("accounts:join_community"))

    def test_search_filters_communities(self):
        Community.objects.create(name="Other Club", admin=self.admin)
        response = self.client.get(reverse("community_list"), {"q": "Test"})
        self.assertContains(response, "Test Uni")
        self.assertNotContains(response, "Other Club")

    def test_member_sees_open_and_outsider_sees_join_with_code(self):
        detail_url = reverse("accounts:community_detail", args=[self.community.pk])

        self.client.force_login(self.member)
        self.assertContains(self.client.get(reverse("community_list")), detail_url)

        self.client.force_login(self.outsider)
        response = self.client.get(reverse("community_list"))
        self.assertContains(response, "Join with code")
        self.assertNotContains(response, detail_url)

    def test_about_page_is_public(self):
        self.assertEqual(self.client.get(reverse("about")).status_code, 200)

    def test_community_page_is_still_members_only(self):
        url = reverse("accounts:community_detail", args=[self.community.pk])
        self.assertEqual(self.client.get(url).status_code, 302)  # guest -> login
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 403)


class ProfileTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin1", "admin1@example.com")
        self.member = User.objects.create_user("member", "member@example.com")
        self.community = Community.objects.create(name="Test Uni", admin=self.admin)
        Membership.objects.create(user=self.member, community=self.community)

    def test_guest_is_sent_to_login_and_returned_afterwards(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)

    def test_profile_shows_own_data(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "member@example.com")
        self.assertContains(response, "Test Uni")
        self.assertNotContains(response, "admin1@example.com")


class RegisterNextTests(TestCase):
    def register(self, next_url):
        return self.client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "newuser@example.com",
                "password1": STRONG_PASSWORD,
                "password2": STRONG_PASSWORD,
                "next": next_url,
            },
        )

    def test_register_returns_to_join_page(self):
        response = self.register(reverse("accounts:join_community"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:join_community"))
        self.assertTrue(User.objects.filter(username="newuser").exists())

    def test_external_next_is_ignored(self):
        response = self.register("https://evil.example/")
        self.assertEqual(response.url, reverse("home"))


class PasswordResetTests(TestCase):
    OLD = "Old-Pass-5512!"
    NEW = "Brand-New-Pass-7391!"

    def setUp(self):
        self.user = User.objects.create_user("farhan", "farhan@example.com", self.OLD)
        self.request_url = reverse("accounts:password_reset_request")
        self.verify_url = reverse("accounts:password_reset_verify")
        self.new_url = reverse("accounts:password_reset_new")

    def ask_for_code(self, email="farhan@example.com"):
        return self.client.post(self.request_url, {"email": email})

    def emailed_code(self):
        return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)

    def wrong_guess(self, code):
        return "000000" if code != "000000" else "111111"

    # ---- asking for a code ----

    def test_known_email_gets_a_code_that_is_stored_hashed(self):
        response = self.ask_for_code()
        self.assertEqual(response.url, self.verify_url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["farhan@example.com"])
        otp = PasswordResetOTP.objects.get(user=self.user)
        self.assertNotEqual(otp.code_hash, self.emailed_code())

    def test_unknown_email_looks_the_same_but_sends_nothing(self):
        known = self.ask_for_code()
        unknown = self.ask_for_code("nobody@example.com")
        self.assertEqual(known.url, unknown.url)
        self.assertEqual(len(mail.outbox), 1)  # only the real account got an email

    def test_inactive_account_gets_no_code(self):
        self.user.is_active = False
        self.user.save()
        self.ask_for_code()
        self.assertEqual(len(mail.outbox), 0)

    def test_second_request_within_a_minute_sends_no_second_email(self):
        self.ask_for_code()
        self.ask_for_code()
        self.assertEqual(len(mail.outbox), 1)

    # ---- the whole journey ----

    def test_full_flow_changes_the_password(self):
        self.ask_for_code()
        response = self.client.post(self.verify_url, {"code": self.emailed_code()})
        self.assertEqual(response.url, self.new_url)

        response = self.client.post(
            self.new_url, {"new_password1": self.NEW, "new_password2": self.NEW}
        )
        self.assertEqual(response.url, reverse("accounts:login"))

        self.client.logout()
        self.assertTrue(self.client.login(username="farhan", password=self.NEW))
        self.client.logout()
        self.assertFalse(self.client.login(username="farhan", password=self.OLD))

    def test_wrong_code_is_rejected_and_new_password_page_stays_closed(self):
        self.ask_for_code()
        response = self.client.post(self.verify_url, {"code": self.wrong_guess(self.emailed_code())})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid or has expired")
        self.assertEqual(self.client.get(self.new_url).status_code, 302)

    def test_new_password_page_needs_a_verified_code(self):
        data = {"new_password1": self.NEW, "new_password2": self.NEW}
        self.assertEqual(self.client.get(self.new_url).status_code, 302)
        self.assertEqual(self.client.post(self.new_url, data).status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.OLD))

    def test_mismatched_passwords_are_rejected(self):
        self.ask_for_code()
        self.client.post(self.verify_url, {"code": self.emailed_code()})
        response = self.client.post(
            self.new_url, {"new_password1": self.NEW, "new_password2": "Something-Else-1!"}
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.OLD))

    # ---- the code rules ----

    def test_too_many_wrong_guesses_lock_the_code(self):
        code = request_code(self.user)
        for _ in range(MAX_ATTEMPTS):
            self.assertFalse(verify_code(self.user, self.wrong_guess(code)))
        self.assertFalse(verify_code(self.user, code))  # even the right code is now refused

    def test_code_expires(self):
        code = request_code(self.user)
        PasswordResetOTP.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertFalse(verify_code(self.user, code))

    def test_code_works_only_once(self):
        code = request_code(self.user)
        self.assertTrue(verify_code(self.user, code))
        self.assertFalse(verify_code(self.user, code))

    def test_a_new_code_replaces_the_old_one(self):
        first = request_code(self.user)
        PasswordResetOTP.objects.update(created_at=timezone.now() - timedelta(minutes=5))
        second = request_code(self.user)
        self.assertNotEqual(first, None)
        self.assertNotEqual(second, None)
        self.assertTrue(verify_code(self.user, second))
        self.assertFalse(verify_code(self.user, first))


def make_image(name="me.png", fmt="PNG", size=(24, 24)):
    buffer = BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, fmt)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/" + fmt.lower())


class AvatarTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_dir = tempfile.mkdtemp()  # uploads go to a throw-away folder
        cls._override = override_settings(MEDIA_ROOT=cls.media_dir)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls.media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = User.objects.create_user("farhan", "farhan@example.com")
        self.client.force_login(self.user)
        self.url = reverse("profile")

    def file_exists(self, name):
        return os.path.exists(os.path.join(self.media_dir, name))

    def test_upload_saves_the_photo_in_the_users_own_folder(self):
        response = self.client.post(self.url, {"avatar": make_image()})
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith(f"avatars/user_{self.user.pk}/"))
        self.assertTrue(self.user.avatar.name.endswith(".png"))
        self.assertNotIn("me", os.path.basename(self.user.avatar.name))  # visitor's file name not used
        self.assertTrue(self.file_exists(self.user.avatar.name))

    def test_photo_shows_on_the_profile_page_and_in_the_navbar(self):
        self.client.post(self.url, {"avatar": make_image()})
        self.user.refresh_from_db()
        for page in (reverse("profile"), reverse("about")):
            self.assertContains(self.client.get(page), self.user.avatar.url)

    def test_without_a_photo_the_initial_is_shown(self):
        response = self.client.get(reverse("about"))
        self.assertNotContains(response, "/media/avatars/")
        self.assertContains(response, ">F</span>")

    def test_a_file_that_is_not_an_image_is_rejected(self):
        fake = SimpleUploadedFile("evil.png", b"this is not an image", content_type="image/png")
        response = self.client.post(self.url, {"avatar": fake})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_an_unsupported_image_format_is_rejected(self):
        response = self.client.post(self.url, {"avatar": make_image("a.bmp", "BMP")})
        self.assertContains(response, "JPG, PNG, GIF or WEBP")
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_a_photo_over_2_mb_is_rejected(self):
        noise = Image.frombytes("RGB", (900, 900), os.urandom(900 * 900 * 3))
        buffer = BytesIO()
        noise.save(buffer, "PNG")
        self.assertGreater(len(buffer.getvalue()), 2 * 1024 * 1024)
        big = SimpleUploadedFile("big.png", buffer.getvalue(), content_type="image/png")
        response = self.client.post(self.url, {"avatar": big})
        self.assertContains(response, "2 MB or smaller")
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_replacing_the_photo_deletes_the_old_file(self):
        self.client.post(self.url, {"avatar": make_image()})
        self.user.refresh_from_db()
        old_name = self.user.avatar.name

        self.client.post(self.url, {"avatar": make_image("second.png")})
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.avatar.name, old_name)
        self.assertFalse(self.file_exists(old_name))
        self.assertTrue(self.file_exists(self.user.avatar.name))

    def test_remove_photo_clears_it_and_deletes_the_file(self):
        self.client.post(self.url, {"avatar": make_image()})
        self.user.refresh_from_db()
        name = self.user.avatar.name

        self.client.post(self.url, {"remove_avatar": "1"})
        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)
        self.assertFalse(self.file_exists(name))

    def test_guest_cannot_upload(self):
        self.client.logout()
        response = self.client.post(self.url, {"avatar": make_image()})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
