from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Community, Membership
from newsfeed.models import Post
from notifications.models import Notification
from verification.models import ContactRequest

from .models import Message

User = get_user_model()


class MessagingTestBase(TestCase):
    def setUp(self):
        def make(name):
            return User.objects.create_user(name, f"{name}@example.com")

        self.admin = make("admin1")
        self.owner = make("owner")
        self.claimant = make("claimant")
        self.other = make("other")
        self.outsider = make("outsider")

        self.community = Community.objects.create(name="Uni", admin=self.admin)
        for user in (self.owner, self.claimant, self.other):
            Membership.objects.create(user=user, community=self.community)

        self.post = Post.objects.create(
            user=self.owner,
            community=self.community,
            type=Post.PostType.FOUND,
            caption="Found a black wallet",
        )
        self.approved = ContactRequest.objects.create(
            post=self.post,
            sender=self.claimant,
            receiver=self.owner,
            status=ContactRequest.Status.APPROVED,
        )
        self.pending = ContactRequest.objects.create(
            post=self.post, sender=self.other, receiver=self.owner
        )
        self.url = reverse("messaging:conversation", args=[self.approved.pk])


class ConversationAccessTests(MessagingTestBase):
    def test_both_participants_can_open(self):
        for user in (self.claimant, self.owner):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_non_participants_are_blocked_for_get_and_post(self):
        for user in (self.other, self.outsider, self.admin):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403, user.username)
            self.assertEqual(self.client.post(self.url, {"content": "hi"}).status_code, 403, user.username)
        self.assertEqual(Message.objects.count(), 0)

    def test_pending_request_has_no_conversation(self):
        url = reverse("messaging:conversation", args=[self.pending.pk])
        for user in (self.other, self.owner):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_login_required(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)


class SendingTests(MessagingTestBase):
    def test_send_creates_messages_with_correct_sender_and_receiver(self):
        self.client.force_login(self.claimant)
        self.client.post(self.url, {"content": "Hello, is it black leather?"})
        self.client.post(self.url, {"content": "Second message"})

        self.assertEqual(Message.objects.count(), 2)
        message = Message.objects.first()
        self.assertEqual(message.sender, self.claimant)
        self.assertEqual(message.receiver, self.owner)
        # Chat does not create notification rows; the receiver is alerted by the live popup.
        self.assertEqual(Notification.objects.filter(user=self.owner).count(), 0)

    def test_empty_message_is_rejected(self):
        self.client.force_login(self.claimant)
        self.client.post(self.url, {"content": "   "})
        self.assertEqual(Message.objects.count(), 0)

    def test_html_in_messages_is_escaped(self):
        self.client.force_login(self.claimant)
        self.client.post(self.url, {"content": "<script>alert(1)</script>"})
        response = self.client.get(self.url)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_opening_marks_incoming_messages_read(self):
        message = Message.objects.create(
            request=self.approved, sender=self.owner, receiver=self.claimant, content="Hi"
        )
        self.client.force_login(self.owner)
        self.client.get(self.url)
        message.refresh_from_db()
        self.assertFalse(message.is_read)  # the sender opening it does not read it

        self.client.force_login(self.claimant)
        self.client.get(self.url)
        message.refresh_from_db()
        self.assertTrue(message.is_read)


class InboxTests(MessagingTestBase):
    def test_inbox_lists_only_own_conversations(self):
        self.client.force_login(self.claimant)
        self.assertContains(self.client.get(reverse("messaging:inbox")), "Found a black wallet")

        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("messaging:inbox")), "Found a black wallet")

    def test_inbox_shows_last_message(self):
        Message.objects.create(
            request=self.approved, sender=self.owner, receiver=self.claimant, content="Ping"
        )
        self.client.force_login(self.claimant)
        response = self.client.get(reverse("messaging:inbox"))
        self.assertContains(response, "Ping")
