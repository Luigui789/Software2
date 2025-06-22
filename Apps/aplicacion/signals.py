from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Persona, Empleado, Rol
from django.utils import timezone

default_app_config = 'Apps.aplicacion.apps.AplicacionConfig'

@receiver(post_save, sender=Persona)
def crear_empleado_automatico(sender, instance, created, **kwargs):
    if created and not instance.is_superuser:
        if instance.rol and not Empleado.objects.filter(persona=instance).exists():
            Empleado.objects.create(
                persona=instance,
                rol=instance.rol,  
                Salario=9000,      # Puedes ajustar esto según tu lógica
                fecha_contratacion=timezone.now()
            )