from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("inbox/", views.inbox, name="inbox"),
    path("conversations/<int:request_id>/", views.conversation, name="conversation"),
]
