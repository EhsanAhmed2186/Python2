from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Community

User = get_user_model()


class BootstrapFormMixin:
    """Gives every field the Bootstrap 'form-control' style."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class RegistrationForm(BootstrapFormMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def clean_email(self):
        # Emails are stored in lowercase, and "A@x.com" counts as "a@x.com".
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    pass


class CommunityForm(BootstrapFormMixin, forms.ModelForm):
    """Only the name is typed by the user. The admin is set in the view."""

    class Meta:
        model = Community
        fields = ["name"]
        labels = {"name": "Community name"}


class JoinCommunityForm(BootstrapFormMixin, forms.Form):
    join_code = forms.CharField(max_length=12, label="Community join code")

    def clean_join_code(self):
        return self.cleaned_data["join_code"].strip().upper()


MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB
ALLOWED_AVATAR_FORMATS = ("JPEG", "PNG", "GIF", "WEBP")


class AvatarForm(BootstrapFormMixin, forms.ModelForm):
    """Upload or replace the logged-in user's profile photo."""

    avatar = forms.ImageField(
        label="Choose a photo",
        widget=forms.FileInput(attrs={"accept": "image/png,image/jpeg,image/gif,image/webp"}),
    )

    class Meta:
        model = User
        fields = ["avatar"]

    def clean_avatar(self):
        image = self.cleaned_data["avatar"]
        if image.size > MAX_AVATAR_SIZE:
            raise forms.ValidationError("The photo must be 2 MB or smaller.")
        # Pillow has already opened the file, so this is the real format, not just the name.
        if getattr(getattr(image, "image", None), "format", None) not in ALLOWED_AVATAR_FORMATS:
            raise forms.ValidationError("Use a JPG, PNG, GIF or WEBP image.")
        return image
