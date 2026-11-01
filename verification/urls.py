from django.urls import path

from . import views

app_name = "verification"

urlpatterns = [
    path("posts/<int:post_id>/questions/", views.manage_questions, name="manage_questions"),
    path("questions/<int:pk>/delete/", views.delete_question, name="delete_question"),
    path("posts/<int:post_id>/claim/", views.claim, name="claim"),
    path("requests/", views.my_requests, name="my_requests"),
    path("requests/<int:pk>/", views.request_detail, name="request_detail"),
    path("requests/<int:pk>/approve/", views.approve, name="approve"),
    path("requests/<int:pk>/reject/", views.reject, name="reject"),
]
