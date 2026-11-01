from django import forms

from accounts.forms import BootstrapFormMixin


class MessageForm(BootstrapFormMixin, forms.Form):
    content = forms.CharField(
        max_length=2000,
        label="Your message",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
