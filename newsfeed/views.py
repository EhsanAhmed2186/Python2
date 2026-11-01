from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.access import get_membership
from accounts.models import Community, Membership

from .forms import CommentForm, PostForm, PostStatusForm, ReportForm
from .models import Post, Report
import mimetypes

from django.http import FileResponse

# ---------- permission helpers (every view goes through these) ----------

def _community_for_member(user, community_id):
    """Return (community, membership) or raise 403 if the user is not a member."""
    community = get_object_or_404(Community, pk=community_id)
    membership = get_membership(user, community)
    if membership is None:
        raise PermissionDenied
    return community, membership


def _post_for_member(user, post_id):
    """Return (post, membership) or raise 403 if the user is not in the post's community."""
    post = get_object_or_404(Post.objects.select_related("community", "user"), pk=post_id)
    membership = get_membership(user, post.community)
    if membership is None:
        raise PermissionDenied
    return post, membership


def _can_manage(user, post, membership):
    """The author, or a community admin/moderator, may change a post's status."""
    return post.user_id == user.id or membership.role in (
        Membership.Role.ADMIN,
        Membership.Role.MODERATOR,
    )


# ---------- feed ----------

@login_required
def feed(request, community_id):
    community, membership = _community_for_member(request.user, community_id)

    posts = community.posts.select_related("user")

    # Filters come from the query string, so every value is checked before use.
    post_type = request.GET.get("type", "")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()

    if post_type in Post.PostType.values:
        posts = posts.filter(type=post_type)
    else:
        post_type = ""
    if status in Post.Status.values:
        posts = posts.filter(status=status)
    else:
        status = ""
    if query:
        posts = posts.filter(caption__icontains=query)

    context = {
        "community": community,
        "posts": posts,
        "post_type": post_type,
        "status": status,
        "query": query,
        "type_choices": Post.PostType.choices,
        "status_choices": Post.Status.choices,
    }
    return render(request, "newsfeed/feed.html", context)


# ---------- posts ----------

@login_required

def post_image(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if get_membership(request.user, post.community) is None:
        raise PermissionDenied
    if not post.image:
        get_object_or_404(Post, pk=-1)

    content_type = mimetypes.guess_type(post.image.name)[0] or "application/octet-stream"
    return FileResponse(post.image.open("rb"), content_type=content_type)
@login_required
def post_create(request, community_id):
    community, _ = _community_for_member(request.user, community_id)

    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.community = community
            post.save()
            messages.success(request, "Your post has been published.")
            return redirect("newsfeed:post_detail", pk=post.pk)
    else:
        form = PostForm()

    context = {"form": form, "community": community, "editing": False}
    return render(request, "newsfeed/post_form.html", context)


@login_required
def post_detail(request, pk):
    post, membership = _post_for_member(request.user, pk)
    can_manage = _can_manage(request.user, post, membership)
    is_author = post.user_id == request.user.id

    context = {
        "post": post,
        "community": post.community,
        "comments": post.comments.select_related("user"),
        "comment_form": CommentForm(),
        "status_form": PostStatusForm(instance=post) if can_manage else None,
        "is_author": is_author,
        "can_manage": can_manage,
        "can_report": not is_author,
    }
    return render(request, "newsfeed/post_detail.html", context)


@login_required
def post_edit(request, pk):
    post, _ = _post_for_member(request.user, pk)
    if post.user_id != request.user.id:
        raise PermissionDenied  # only the author edits the text and image

    if request.method == "POST":
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "Post updated.")
            return redirect("newsfeed:post_detail", pk=post.pk)
    else:
        form = PostForm(instance=post)

    context = {"form": form, "community": post.community, "editing": True, "post": post}
    return render(request, "newsfeed/post_form.html", context)


@login_required
@require_POST
def post_status(request, pk):
    post, membership = _post_for_member(request.user, pk)
    if not _can_manage(request.user, post, membership):
        raise PermissionDenied

    form = PostStatusForm(request.POST, instance=post)
    if form.is_valid():
        form.save()
        messages.success(request, f"Status changed to {post.get_status_display()}.")
    else:
        messages.error(request, "Invalid status.")
    return redirect("newsfeed:post_detail", pk=post.pk)


# ---------- comments and reports ----------

@login_required
@require_POST
def comment_create(request, pk):
    post, _ = _post_for_member(request.user, pk)

    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.user = request.user
        comment.post = post
        comment.save()
        messages.success(request, "Comment added.")
    else:
        messages.error(request, "A comment cannot be empty.")
    return redirect("newsfeed:post_detail", pk=post.pk)


@login_required
def report_create(request, pk):
    post, _ = _post_for_member(request.user, pk)

    if post.user_id == request.user.id:
        messages.error(request, "You cannot report your own post.")
        return redirect("newsfeed:post_detail", pk=post.pk)
    if Report.objects.filter(user=request.user, post=post).exists():
        messages.info(request, "You have already reported this post.")
        return redirect("newsfeed:post_detail", pk=post.pk)

    if request.method == "POST":
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.user = request.user
            report.post = post
            report.save()
            messages.success(request, "Thank you. The post has been reported.")
            return redirect("newsfeed:post_detail", pk=post.pk)
    else:
        form = ReportForm()

    return render(request, "newsfeed/report_form.html", {"form": form, "post": post})
