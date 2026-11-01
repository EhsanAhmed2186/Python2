from django.urls import path

from . import views

app_name = "newsfeed"

urlpatterns = [
    path("communities/<int:community_id>/posts/", views.feed, name="feed"),
    path("communities/<int:community_id>/posts/new/", views.post_create, name="post_create"),
    path("posts/<int:pk>/", views.post_detail, name="post_detail"),
    path("posts/<int:pk>/edit/", views.post_edit, name="post_edit"),
    path("posts/<int:pk>/status/", views.post_status, name="post_status"),
    path("posts/<int:pk>/comments/new/", views.comment_create, name="comment_create"),
    path("posts/<int:pk>/report/", views.report_create, name="report_create"),
    path("posts/<int:pk>/image/", views.post_image, name="post_image"),
]
