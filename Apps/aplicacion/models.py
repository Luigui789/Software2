from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password

# Create your models here.

from django.contrib.auth.hashers import make_password

class Persona(AbstractUser):
    nombre1 = models.CharField(max_length=15, blank=False)
    nombre2 = models.CharField(max_length=15, blank=True)
    apellidoP = models.CharField(max_length=15, blank=False)
    apellidoM = models.CharField(max_length=15, blank=True)
    telefono = models.CharField(max_length=15, blank=False)

    # def save(self, *args, **kwargs):
    #     # Solo hashear si no está hasheada ya
    #     if self.password and not is_password_usable(self.password):
    #         self.password = make_password(self.password)
    #     super().save(*args, **kwargs)
    
    def _str_(self):
        return f'{self.nombre1} {self.nombre2} {self.apellidoP} {self.apellidoM} {self.telefono}  {self.username} {self.is_active} {self.email}'

class Empleado(models.Model):
    cargo = models.CharField(max_length=15)
    Salario = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_contratacion = models.DateField(default=timezone.now)
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name='empleados')

    def _str_(self):
        return f'{self.cargo} {self.Salario} {self.fecha_contratacion} {self.persona}'
    
class Cliente(models.Model):
    nombre1 = models.CharField(max_length=15,blank=False)
    nombre2 = models.CharField(max_length=15, blank=True)
    apellidoP = models.CharField(max_length=15, blank=False)
    apellidoM = models.CharField(max_length=15, blank=True)
    instagram = models.CharField(max_length=15, blank=True)
    correo = models.EmailField(max_length=254, blank=True)

    def _str_(self):
        return f'{self.nombre1} {self.nombre2} {self.apellidoP} {self.apellidoM} {self.instagram} {self.correo}'

class Barbero(models.Model):
    Direccion = models.TextField()
    cedula = models.CharField(max_length=14,blank=False)
    Estado = models.BooleanField(default=True)
    Comisiones = models.DecimalField(max_digits=10, decimal_places=2)
    Empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='barberos')

    def _str_(self):
        return f'{self.Direccion} {self.cedula} {self.Estado} {self.Comisiones} {self.Empleado}'
    
class Servicio(models.Model):
    nombre = models.CharField(max_length=15)
    tipo = models.CharField(max_length=15)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.BooleanField(default=True)

    def _str_(self):
        return f'{self.nombre} {self.tipo} {self.descripcion} {self.precio} {self.estado} '
    
class Servicio_Realizado(models.Model):
    fecha = models.DateField(default=timezone.now)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='servicios_realizados')
    barbero = models.ForeignKey(Barbero, on_delete=models.CASCADE, related_name='servicios_realizados')

    def _str_(self):
        return f'{self.fecha} {self.cliente} {self.barbero} '
    
class Detalle_ServicioRealizado(models.Model):
    Servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name="detalle_ServicioRealizado")
    Servicio_Realizado = models.ForeignKey(Servicio_Realizado,on_delete=models.CASCADE, related_name="detalle")

    def _str_(self):
        return f'{self.Servicio} {self.Servicio_Realizado}'