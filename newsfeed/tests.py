from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Community, Membership

from .models import Comment, Post, Report

User = get_user_model()
PASSWORD = "pass12345"


class NewsfeedTestBase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "owner@example.com", PASSWORD)
        self.member = User.objects.create_user("member", "member@example.com", PASSWORD)
        self.outsider = User.objects.create_user("outsider", "outsider@example.com", PASSWORD)
        self.community = Community.objects.create(name="Test Uni", admin=self.owner)
        Membership.objects.create(user=self.member, community=self.community)
        self.post = Post.objects.create(
            user=self.owner,
            community=self.community,
            type=Post.PostType.FOUND,
            caption="Found a blue backpack",
        )

    def login(self, user):
        self.client.login(username=user.username, password=PASSWORD)


class AccessTests(NewsfeedTestBase):
    def test_login_required(self):
        response = self.client.get(reverse("newsfeed:feed", args=[self.community.pk]))
        self.assertEqual(response.status_code, 302)

    def test_non_member_is_blocked_everywhere(self):
        self.login(self.outsider)
        urls = [
            reverse("newsfeed:feed", args=[self.community.pk]),
            reverse("newsfeed:post_create", args=[self.community.pk]),
            reverse("newsfeed:post_detail", args=[self.post.pk]),
        ]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_member_sees_feed_and_filters_work(self):
        self.login(self.member)
        url = reverse("newsfeed:feed", args=[self.community.pk])
        self.assertContains(self.client.get(url), "Found a blue backpack")
        self.assertNotContains(self.client.get(url, {"type": "lost"}), "Found a blue backpack")


class PostTests(NewsfeedTestBase):
    def test_member_can_create_post(self):
        self.login(self.member)
        url = reverse("newsfeed:post_create", args=[self.community.pk])
        response = self.client.post(url, {"type": "lost", "caption": "Lost my wallet"})
        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(caption="Lost my wallet")
        self.assertEqual(post.user, self.member)
        self.assertEqual(post.community, self.community)

    def test_only_author_can_edit(self):
        url = reverse("newsfeed:post_edit", args=[self.post.pk])
        data = {"type": "found", "caption": "Updated caption"}

        self.login(self.member)
        self.assertEqual(self.client.post(url, data).status_code, 403)

        self.client.logout()
        self.login(self.owner)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.post.refresh_from_db()
        self.assertEqual(self.post.caption, "Updated caption")


class StatusTests(NewsfeedTestBase):
    def setUp(self):
        super().setUp()
        self.url = reverse("newsfeed:post_status", args=[self.post.pk])

    def test_author_can_change_status(self):
        self.login(self.owner)
        self.client.post(self.url, {"status": "returned"})
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.RETURNED)

    def test_plain_member_cannot_change_status(self):
        self.login(self.member)
        self.assertEqual(self.client.post(self.url, {"status": "closed"}).status_code, 403)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.ACTIVE)

    def test_invalid_status_is_rejected_and_get_not_allowed(self):
        self.login(self.owner)
        self.client.post(self.url, {"status": "hacked"})
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, Post.Status.ACTIVE)
        self.assertEqual(self.client.get(self.url).status_code, 405)


class CommentReportTests(NewsfeedTestBase):
    def test_member_can_comment_but_outsider_cannot(self):
        url = reverse("newsfeed:comment_create", args=[self.post.pk])

        self.login(self.member)
        self.client.post(url, {"content": "Is it still available?"})
        self.assertEqual(Comment.objects.count(), 1)

        self.client.logout()
        self.login(self.outsider)
        self.assertEqual(self.client.post(url, {"content": "Hi"}).status_code, 403)
        self.assertEqual(Comment.objects.count(), 1)

    def test_report_once_and_not_own_post(self):
        url = reverse("newsfeed:report_create", args=[self.post.pk])
        data = {"reason": "spam", "description": "Looks fake"}

        self.login(self.member)
        self.client.post(url, data)
        self.client.post(url, data)  # second attempt must not create a duplicate
        self.assertEqual(Report.objects.count(), 1)

        self.client.logout()
        self.login(self.owner)
        self.client.post(url, data)  # author reporting their own post
        self.assertEqual(Report.objects.count(), 1)
