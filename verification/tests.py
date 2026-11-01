from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Community, Membership
from newsfeed.models import Post
from notifications.models import Notification

from .models import ContactRequest, VerificationAnswer, VerificationQuestion
from .utils import hash_answer

User = get_user_model()


class VerificationTestBase(TestCase):
    def setUp(self):
        def make(name):
            return User.objects.create_user(name, f"{name}@example.com")

        self.admin = make("admin1")
        self.owner = make("owner")
        self.claimant = make("claimant")
        self.other = make("other")
        self.mod = make("mod")
        self.outsider = make("outsider")

        self.community = Community.objects.create(name="Uni", admin=self.admin)
        for user in (self.owner, self.claimant, self.other):
            Membership.objects.create(user=user, community=self.community)
        Membership.objects.create(
            user=self.mod, community=self.community, role=Membership.Role.MODERATOR
        )

        self.post = Post.objects.create(
            user=self.owner,
            community=self.community,
            type=Post.PostType.FOUND,
            caption="Found a black wallet",
        )
        self.question = VerificationQuestion.objects.create(
            post=self.post,
            question="What colour is the lining?",
            answer_hash=hash_answer("Blue"),
        )
        self.claim_url = reverse("verification:claim", args=[self.post.pk])

    def make_request(self, sender=None, status=ContactRequest.Status.PENDING):
        return ContactRequest.objects.create(
            post=self.post, sender=sender or self.claimant, receiver=self.owner, status=status
        )


class QuestionTests(VerificationTestBase):
    def test_owner_adds_question_and_answer_is_stored_hashed(self):
        self.client.force_login(self.owner)
        url = reverse("verification:manage_questions", args=[self.post.pk])
        self.client.post(url, {"question": "Which brand?", "expected_answer": "Nike"})
        question = VerificationQuestion.objects.get(question="Which brand?")
        self.assertNotEqual(question.answer_hash, "")
        self.assertNotEqual(question.answer_hash, "Nike")

    def test_non_owner_cannot_manage_questions(self):
        self.client.force_login(self.claimant)
        url = reverse("verification:manage_questions", args=[self.post.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_questions_are_locked_once_a_request_exists(self):
        self.make_request()
        self.client.force_login(self.owner)
        url = reverse("verification:manage_questions", args=[self.post.pk])
        self.client.post(url, {"question": "Too late?", "expected_answer": ""})
        self.assertEqual(VerificationQuestion.objects.count(), 1)
        delete_url = reverse("verification:delete_question", args=[self.question.pk])
        self.client.post(delete_url)
        self.assertEqual(VerificationQuestion.objects.count(), 1)


class ClaimTests(VerificationTestBase):
    def test_claim_creates_request_answers_and_notifies_owner(self):
        self.client.force_login(self.claimant)
        self.client.post(self.claim_url, {f"q_{self.question.pk}": "  blue "})

        contact = ContactRequest.objects.get()
        self.assertEqual(contact.sender, self.claimant)
        self.assertEqual(contact.receiver, self.owner)
        self.assertEqual(contact.status, ContactRequest.Status.PENDING)
        answer = VerificationAnswer.objects.get()
        self.assertTrue(answer.matches_expected)
        self.assertEqual(Notification.objects.filter(user=self.owner).count(), 1)

    def test_wrong_answer_is_flagged_but_request_still_created(self):
        self.client.force_login(self.claimant)
        self.client.post(self.claim_url, {f"q_{self.question.pk}": "red"})
        self.assertFalse(VerificationAnswer.objects.get().matches_expected)
        self.assertEqual(ContactRequest.objects.count(), 1)

    def test_outsider_and_owner_cannot_claim(self):
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(self.claim_url, {}).status_code, 403)
        self.client.force_login(self.owner)
        self.client.post(self.claim_url, {f"q_{self.question.pk}": "blue"})
        self.assertEqual(ContactRequest.objects.count(), 0)

    def test_second_claim_by_same_user_creates_nothing_new(self):
        self.client.force_login(self.claimant)
        data = {f"q_{self.question.pk}": "blue"}
        self.client.post(self.claim_url, data)
        self.client.post(self.claim_url, data)
        self.assertEqual(ContactRequest.objects.count(), 1)

    def test_cannot_claim_a_closed_post(self):
        self.post.status = Post.Status.CLOSED
        self.post.save()
        self.client.force_login(self.claimant)
        self.client.post(self.claim_url, {f"q_{self.question.pk}": "blue"})
        self.assertEqual(ContactRequest.objects.count(), 0)


class DecisionTests(VerificationTestBase):
    def setUp(self):
        super().setUp()
        self.contact = self.make_request()
        self.approve_url = reverse("verification:approve", args=[self.contact.pk])
        self.reject_url = reverse("verification:reject", args=[self.contact.pk])

    def status(self):
        self.contact.refresh_from_db()
        return self.contact.status

    def test_owner_approves_and_sender_is_notified(self):
        self.client.force_login(self.owner)
        self.client.post(self.approve_url)
        self.assertEqual(self.status(), ContactRequest.Status.APPROVED)
        self.assertEqual(Notification.objects.filter(user=self.claimant).count(), 1)

    def test_owner_rejects(self):
        self.client.force_login(self.owner)
        self.client.post(self.reject_url)
        self.assertEqual(self.status(), ContactRequest.Status.REJECTED)

    def test_plain_member_cannot_decide(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.approve_url).status_code, 403)
        self.assertEqual(self.status(), ContactRequest.Status.PENDING)

    def test_sender_cannot_approve_own_request(self):
        self.client.force_login(self.claimant)
        self.assertEqual(self.client.post(self.approve_url).status_code, 403)
        self.assertEqual(self.status(), ContactRequest.Status.PENDING)

    def test_sender_who_is_a_moderator_still_cannot_approve_own_request(self):
        Membership.objects.filter(user=self.claimant).update(role=Membership.Role.MODERATOR)
        self.client.force_login(self.claimant)
        self.assertEqual(self.client.post(self.approve_url).status_code, 403)
        self.assertEqual(self.status(), ContactRequest.Status.PENDING)

    def test_moderator_can_decide(self):
        self.client.force_login(self.mod)
        self.client.post(self.approve_url)
        self.assertEqual(self.status(), ContactRequest.Status.APPROVED)

    def test_decided_request_cannot_be_changed(self):
        self.client.force_login(self.owner)
        self.client.post(self.approve_url)
        self.client.post(self.reject_url)
        self.assertEqual(self.status(), ContactRequest.Status.APPROVED)

    def test_decision_requires_post(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.approve_url).status_code, 405)


class VisibilityTests(VerificationTestBase):
    def setUp(self):
        super().setUp()
        self.contact = self.make_request()
        VerificationAnswer.objects.create(
            request=self.contact, question=self.question, answer_text="blue", matches_expected=True
        )
        self.url = reverse("verification:request_detail", args=[self.contact.pk])

    def test_owner_sees_answers(self):
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(self.url), "Answers submitted by the claimant")

    def test_sender_does_not_see_answers_or_match_flags(self):
        self.client.force_login(self.claimant)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Answers submitted by the claimant")
        self.assertNotContains(response, "Matches expected answer")

    def test_other_member_and_outsider_are_blocked(self):
        for user in (self.other, self.outsider):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 403, user.username)
