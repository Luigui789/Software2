from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Persona, Rol # Asegúrate de importar también el modelo Rol

class PersonaCreationForm(UserCreationForm):
    # Por defecto, UserCreationForm solo tiene username y password.
    # Aquí estamos añadiendo los campos personalizados de Persona.
    class Meta(UserCreationForm.Meta): # Es buena práctica heredar de UserCreationForm.Meta
        model = Persona
        fields = (
            'username', 
            'email', 
            'nombre1', 
            'nombre2', 
            'apellidoP', 
            'apellidoM', 
            'telefono',
            'rol' # ¡Este es el nuevo campo a agregar!
        )

class PersonaChangeForm(UserChangeForm):
    # Este formulario es para editar usuarios existentes en el panel de administración
    # o en una vista personalizada de edición.
    class Meta(UserChangeForm.Meta): # Es buena práctica heredar de UserChangeForm.Meta
        model = Persona
        fields = (
            'username', 
            'email', 
            'nombre1', 
            'nombre2', 
            'apellidoP', 
            'apellidoM', 
            'telefono',
            'rol' # ¡Este es el nuevo campo a agregar!
        )
