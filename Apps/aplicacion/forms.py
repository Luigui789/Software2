# en forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Persona

class PersonaCreationForm(UserCreationForm):
    class Meta:
        model = Persona
        fields = ('username', 'email', 'nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'telefono')

class PersonaChangeForm(UserChangeForm):
    class Meta:
        model = Persona
        fields = ('username', 'email', 'nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'telefono')