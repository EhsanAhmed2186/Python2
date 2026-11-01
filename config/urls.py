from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts import views as accounts_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("newsfeed.urls")),
    path("", include("verification.urls")),
    path("", include("messaging.urls")),
    path("", include("notifications.urls")),
    # Public pages (guests allowed)
    path("", accounts_views.home, name="home"),
    path("communities/", accounts_views.community_list, name="community_list"),
    path("about/", accounts_views.about, name="about"),
    # Needs login: a guest is sent to the login page and then returned here
    path("profile/", accounts_views.profile, name="profile"),
]

# Serve uploaded images during development only.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
