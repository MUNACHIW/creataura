from django import forms

from .models import SupportMessage


class SupportMessageForm(forms.ModelForm):
    class Meta:
        model = SupportMessage
        fields = ("subject", "message")
        widgets = {
            "subject": forms.TextInput(
                attrs={"id": "subject", "maxlength": 200, "required": True}
            ),
            "message": forms.Textarea(
                attrs={"id": "message", "rows": 5, "required": True}
            ),
        }
