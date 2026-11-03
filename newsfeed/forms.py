from django import forms
from django.core.files.uploadedfile import UploadedFile

from accounts.forms import BootstrapFormMixin

from .models import Comment, Post, Report

MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB


class PostForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Post
        fields = ["type", "caption", "location", "image"]
        labels = {
            "type": "Is the item lost or found?",
            "caption": "Describe the item",
            "location": "Where was it lost or found?",
        }
        widgets = {"caption": forms.Textarea(attrs={"rows": 4})}

    def clean_image(self):
        image = self.cleaned_data.get("image")
        # Only check a freshly uploaded file, not an image that is already saved.
        if isinstance(image, UploadedFile) and image.size > MAX_IMAGE_SIZE:
            raise forms.ValidationError("Image must be 5 MB or smaller.")
        return image


class PostStatusForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ["status"]


class CommentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["content"]
        labels = {"content": "Add a comment"}
        widgets = {"content": forms.Textarea(attrs={"rows": 3})}


class ReportForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "description"]
        labels = {"description": "Details (optional)"}
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
