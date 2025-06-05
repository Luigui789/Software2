from django.contrib import admin
from .models import Persona, Cliente, Servicio, Servicio_Realizado, Barbero, Empleado, Detalle_ServicioRealizado, Rol
from .forms import PersonaCreationForm, PersonaChangeForm
from django.contrib.auth.admin import UserAdmin
from axes.models import AccessAttempt, AccessLog


# Register your models here.
class PersonaAdmin(UserAdmin):
    add_form = PersonaCreationForm
    form = PersonaChangeForm
    model = Persona

    list_display = ('username', 'email', 'nombre1', 'apellidoP', 'rol' , 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Información personal', {'fields': ('nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'telefono', 'rol' , 'email')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas importantes', {'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'email', 'nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'telefono', 'is_active', 'is_staff')}
        ),
    )

    search_fields = ('username','rol' , 'email')
    ordering = ('username',)

admin.site.register(Persona, PersonaAdmin)

class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ('Salario', 'fecha_contratacion', 'persona')
    search_fields = ( 'Salario', 'fecha_contratacion', 'persona_nombre1', 'persona_apellidoP')
admin.site.register(Empleado, EmpleadoAdmin)

class ClienteAdmin(admin.ModelAdmin):
    list_display = ( 'nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'instagram', 'correo')
    search_fields = ('nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'instagram')
admin.site.register(Cliente, ClienteAdmin)

class BarberoAdmin(admin.ModelAdmin):
    list_display = ('Direccion', 'cedula', 'Estado', 'Comisiones', 'Empleado')
    search_fields = ('Direccion', 'cedula', 'Estado', 'Comisiones', 'empleado_personanombre1', 'empleadopersonaapellidoP', 'empleado_cargo')
    list_filter = ('Estado',)
admin.site.register(Barbero, BarberoAdmin)

class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'descripcion', 'precio', 'estado')
    search_fields = ('nombre', 'tipo', 'descripcion', 'precio', 'estado')
admin.site.register(Servicio, ServicioAdmin)

class ServicioRealizadoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'cliente', 'barbero')
    search_fields = ('fecha', 'cliente_personanombre1', 'clientepersonaapellidoP', 'barberopersonanombre1', 'barberopersona_apellidoP')
    list_filter = ('fecha',)
admin.site.register(Servicio_Realizado, ServicioRealizadoAdmin)

class DetalleServicioAdmin(admin.ModelAdmin):
    list_display = ('Servicio', 'Servicio_Realizado')
    search_fields = ('servicio_nombre', 'servicio_realizado_fecha')


admin.site.register(Detalle_ServicioRealizado, DetalleServicioAdmin)

class RolAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)
    ordering = ('nombre',)

admin.site.register(Rol, RolAdmin)