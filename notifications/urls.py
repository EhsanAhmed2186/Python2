from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.notification_list, name="list"),
    path("notifications/poll/", views.poll, name="poll"),
    path("notifications/read-all/", views.mark_all_read, name="mark_all_read"),
    path("notifications/<int:pk>/open/", views.open_notification, name="open"),
]
