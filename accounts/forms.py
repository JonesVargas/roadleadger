from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    accept_terms = forms.BooleanField(label="Li e aceito os Termos de Uso e a Política de Privacidade")

    class Meta:
        model = User
        fields = ("full_name", "email", "country", "password1", "password2", "communications_opt_in")


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="E-mail")


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "country", "language", "timezone", "communications_opt_in")
