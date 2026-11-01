from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Community, Membership
from messaging.models import Message
from newsfeed.models import Post
from verification.models import ContactRequest

from .models import Notification
from .services import notify

User = get_user_model()


class NotificationTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com")
        self.bob = User.objects.create_user("bob", "bob@example.com")
        self.n_alice = Notification.objects.create(user=self.alice, message="Secret for Alice", url="/requests/")
        self.n_bob = Notification.objects.create(user=self.bob, message="Secret for Bob", url="/requests/")

    def test_list_shows_only_own_notifications(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("notifications:list"))
        self.assertContains(response, "Secret for Alice")
        self.assertNotContains(response, "Secret for Bob")

    def test_open_marks_read_and_redirects(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("notifications:open", args=[self.n_alice.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/requests/")
        self.n_alice.refresh_from_db()
        self.assertTrue(self.n_alice.is_read)

    def test_cannot_open_someone_elses_notification(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("notifications:open", args=[self.n_bob.pk]))
        self.assertEqual(response.status_code, 404)
        self.n_bob.refresh_from_db()
        self.assertFalse(self.n_bob.is_read)

    def test_external_url_is_not_followed(self):
        evil = Notification.objects.create(user=self.alice, message="x", url="https://evil.example/")
        self.client.force_login(self.alice)
        response = self.client.get(reverse("notifications:open", args=[evil.pk]))
        self.assertEqual(response.url, reverse("notifications:list"))

    def test_mark_all_read_only_affects_own(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("notifications:mark_all_read"))
        self.n_alice.refresh_from_db()
        self.n_bob.refresh_from_db()
        self.assertTrue(self.n_alice.is_read)
        self.assertFalse(self.n_bob.is_read)

    def test_mark_all_read_rejects_get(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse("notifications:mark_all_read")).status_code, 405)

    def test_notify_dedupes_unread_for_same_url(self):
        notify(self.alice, "one", url="/c/1/", dedupe_unread=True)
        notify(self.alice, "two", url="/c/1/", dedupe_unread=True)
        self.assertEqual(Notification.objects.filter(user=self.alice, url="/c/1/").count(), 1)


class PollTests(TestCase):
    """The endpoint behind the live popups."""

    def setUp(self):
        def make(name):
            return User.objects.create_user(name, f"{name}@example.com")

        self.admin = make("admin1")
        self.alice = make("alice")
        self.bob = make("bob")

        community = Community.objects.create(name="Uni", admin=self.admin)
        Membership.objects.create(user=self.alice, community=community)
        Membership.objects.create(user=self.bob, community=community)
        post = Post.objects.create(
            user=self.alice, community=community, type=Post.PostType.FOUND, caption="Found keys"
        )
        self.contact = ContactRequest.objects.create(
            post=post, sender=self.bob, receiver=self.alice, status=ContactRequest.Status.APPROVED
        )

        self.n_alice = Notification.objects.create(user=self.alice, message="For Alice", url="/requests/")
        self.n_bob = Notification.objects.create(user=self.bob, message="For Bob", url="/requests/")
        self.to_alice = Message.objects.create(
            request=self.contact, sender=self.bob, receiver=self.alice, content="Hi Alice"
        )
        self.to_bob = Message.objects.create(
            request=self.contact, sender=self.alice, receiver=self.bob, content="Hi Bob"
        )
        self.url = reverse("notifications:poll")

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_post_is_not_allowed(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_returns_only_the_users_own_items(self):
        self.client.force_login(self.alice)
        data = self.client.get(self.url, {"n": 0, "m": 0}).json()
        self.assertEqual([n["message"] for n in data["notifications"]], ["For Alice"])
        self.assertEqual([m["content"] for m in data["messages"]], ["Hi Alice"])
        self.assertEqual(data["messages"][0]["sender"], "bob")

    def test_items_already_seen_are_not_repeated(self):
        self.client.force_login(self.alice)
        data = self.client.get(
            self.url, {"n": self.n_alice.pk, "m": self.to_alice.pk}
        ).json()
        self.assertEqual(data["notifications"], [])
        self.assertEqual(data["messages"], [])
        self.assertEqual(data["last_notification_id"], self.n_alice.pk)
        self.assertEqual(data["last_message_id"], self.to_alice.pk)

    def test_counts_for_the_navbar_badges(self):
        self.client.force_login(self.alice)
        counts = self.client.get(self.url, {"n": 0, "m": 0}).json()["counts"]
        self.assertEqual(counts, {"notifications": 1, "messages": 1, "requests": 0})

    def test_open_conversation_marks_its_messages_read(self):
        self.client.force_login(self.alice)
        data = self.client.get(
            self.url, {"n": 0, "m": 0, "open": self.contact.pk}
        ).json()
        self.to_alice.refresh_from_db()
        self.assertTrue(self.to_alice.is_read)
        self.assertEqual(data["counts"]["messages"], 0)

    def test_messages_stay_unread_when_conversation_is_not_open(self):
        self.client.force_login(self.alice)
        self.client.get(self.url, {"n": 0, "m": 0})
        self.to_alice.refresh_from_db()
        self.assertFalse(self.to_alice.is_read)

    def test_invalid_numbers_are_ignored(self):
        self.client.force_login(self.alice)
        response = self.client.get(self.url, {"n": "abc", "m": "-5", "open": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["notifications"]), 1)
