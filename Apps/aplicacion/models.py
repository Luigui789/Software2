from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password

# Create your models here.

class Rol(models.Model):
    nombre = models.CharField(max_length=30, unique=True)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return self.nombre

class Persona(AbstractUser):
    nombre1 = models.CharField(max_length=15, blank=False)
    nombre2 = models.CharField(max_length=15, blank=True)
    apellidoP = models.CharField(max_length=15, blank=False)
    apellidoM = models.CharField(max_length=15, blank=True)
    telefono = models.CharField(max_length=15, blank=False)
    rol = models.ForeignKey(Rol, on_delete=models.SET_NULL, null=True, blank=True)

    # def save(self, *args, **kwargs):
    #     # Solo hashear si no está hasheada ya
    #     if self.password and not is_password_usable(self.password):
    #         self.password = make_password(self.password)
    #     super().save(*args, **kwargs)
    
    def __str__(self):
        return f'{self.nombre1} {self.nombre2} {self.apellidoP} {self.apellidoM} {self.telefono} {self.rol}  {self.username} {self.is_active} {self.email}'


class Empleado(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name='empleados')
    Salario = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_contratacion = models.DateField(default=timezone.now)


    def __str__(self):
        return f'{self.rol} {self.Salario} {self.fecha_contratacion} {self.persona}'
    
class Cliente(models.Model):
    nombre1 = models.CharField(max_length=15,blank=False)
    nombre2 = models.CharField(max_length=15, blank=True)
    apellidoP = models.CharField(max_length=15, blank=False)
    apellidoM = models.CharField(max_length=15, blank=True)
    instagram = models.CharField(max_length=15, blank=True)
    correo = models.EmailField(max_length=254, blank=True)

    def __str__(self):
        return f'{self.nombre1} {self.nombre2} {self.apellidoP} {self.apellidoM} {self.instagram} {self.correo}'

class Barbero(models.Model):
    Direccion = models.TextField()
    cedula = models.CharField(max_length=14,blank=False)
    Estado = models.BooleanField(default=True)
    Comisiones = models.DecimalField(max_digits=10, decimal_places=2)
    Empleado = models.ForeignKey(Empleado, on_delete=models.CASCADE, related_name='barberos')

    def __str__(self):
        return f'{self.Direccion} {self.cedula} {self.Estado} {self.Comisiones} {self.Empleado}'
    
class Servicio(models.Model):
    nombre = models.CharField(max_length=15)
    tipo = models.CharField(max_length=15)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    estado = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.nombre} {self.tipo} {self.descripcion} {self.precio} {self.estado} '
    
class Servicio_Realizado(models.Model):
    fecha = models.DateField(default=timezone.now)
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='servicios_realizados')
    barbero = models.ForeignKey(Barbero, on_delete=models.CASCADE, related_name='servicios_realizados')

    def __str__(self):
        return f'{self.fecha} {self.cliente} {self.barbero} '
    
class Detalle_ServicioRealizado(models.Model):
    Servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name="detalle_ServicioRealizado")
    Servicio_Realizado = models.ForeignKey(Servicio_Realizado,on_delete=models.CASCADE, related_name="detalle")

    def __str__(self):
        return f'{self.Servicio} {self.Servicio_Realizado}'
    
# --- NUEVO MODELO PARA EL SISTEMA DE COLAS ---
class BarberQueue(models.Model):
    barbero = models.OneToOneField(Barbero, on_delete=models.CASCADE, unique=True, related_name='queue', verbose_name="Barbero Asociado")
    current_number = models.IntegerField(default=0, verbose_name="Número Actual Siendo Atendido")
    # Nuevo campo: El último número (ticket) que se le ha dado a un cliente
    last_issued_number = models.IntegerField(default=0, verbose_name="Último Número de Ticket Emitido")

    def __str__(self):
        # Mejora la representación para que sea más clara en el admin
        return f"Cola para {self.barbero.empleado.persona.nombre1} {self.barbero.empleado.persona.apellidoP} - Atendiendo: {self.current_number}, Último Ticket: {self.last_issued_number}"

    @classmethod
    def get_or_create_queue_for_barber(cls, barbero_obj):
        """
        Obtiene o crea una instancia de BarberQueue para un barbero dado.
        """
        obj, created = cls.objects.get_or_create(
            barbero=barbero_obj,
            defaults={'current_number': 0, 'last_issued_number': 0} # Inicializa ambos campos
        )
        return obj

    def increment_served_number(self):
        """
        Incrementa el número que el barbero está atendiendo,
        pero no más allá del último número emitido.
        """
        # Solo incrementa si el número actual es menor que el último emitido
        # o si ambos son 0 (para permitir el primer avance si la cola está vacía)
        if self.current_number < self.last_issued_number or \
            (self.current_number == 0 and self.last_issued_number == 0):
            self.current_number += 1
            self.save()
        # Si current_number ya es igual o mayor que last_issued_number, no hacemos nada
        # esto evita que el barbero "llame" números que no han sido emitidos.
        return self.current_number

    def issue_new_ticket(self):
        """
        Emite un nuevo número de ticket para un cliente que selecciona un barbero.
        """
        self.last_issued_number += 1
        self.save()
        return self.last_issued_number

    def reset_queue(self): # Renombrado para mayor claridad
        """
        Resetea ambos contadores a 0.
        """
        self.current_number = 0
        self.last_issued_number = 0
        self.save()
        return 0 # Retorna 0 como el nuevo estado
    
    