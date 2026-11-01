from django import forms

from accounts.forms import BootstrapFormMixin


class QuestionForm(BootstrapFormMixin, forms.Form):
    question = forms.CharField(max_length=300, label="Question")
    expected_answer = forms.CharField(
        max_length=300,
        required=False,
        label="Expected answer (optional)",
        help_text="Saved only as a secure hash, so nobody can read it later. It is used to give you a hint, never to approve anyone automatically.",
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )


class ClaimForm(BootstrapFormMixin, forms.Form):
    """One text box per verification question, built from the post's questions."""

    def __init__(self, *args, questions=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.questions = list(questions)
        for question in self.questions:
            self.fields[f"q_{question.pk}"] = forms.CharField(
                max_length=500,
                label=question.question,
                widget=forms.TextInput(attrs={"autocomplete": "off"}),
            )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def answers(self):
        """List of (question, typed answer). Call only after is_valid()."""
        return [(q, self.cleaned_data[f"q_{q.pk}"]) for q in self.questions]
