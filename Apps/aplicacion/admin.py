from django.contrib import admin
from .models import Persona, Cliente, Servicio, Servicio_Realizado, Barbero, Empleado, Detalle_ServicioRealizado
# Register your models here.

class PersonaAdmin(admin.ModelAdmin):
    list_display = ('nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'telefono', 'username', 'email', 'is_active')
    search_fields = ('nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'telefono', 'username')
admin.site.register(Persona, PersonaAdmin)

class EmpleadoAdmin(admin.ModelAdmin):
    list_display = ('cargo', 'Salario', 'fecha_contratacion', 'persona')
    search_fields = ('cargo', 'Salario', 'fecha_contratacion', 'persona__nombre1', 'persona__apellidoP')
    list_filter = ('cargo',)
admin.site.register(Empleado, EmpleadoAdmin)

class ClienteAdmin(admin.ModelAdmin):
    list_display = ( 'nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'instagram', 'correo')
    search_fields = ('nombre1', 'nombre2', 'apellidoP', 'apellidoM', 'instagram')
admin.site.register(Cliente, ClienteAdmin)

class BarberoAdmin(admin.ModelAdmin):
    list_display = ('Direccion', 'cedula', 'Estado', 'Comisiones', 'Empleado')
    search_fields = ('Direccion', 'cedula', 'Estado', 'Comisiones', 'empleado__persona__nombre1', 'empleado__persona__apellidoP', 'empleado__cargo')
    list_filter = ('Estado',)
admin.site.register(Barbero, BarberoAdmin)

class ServicioAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo', 'descripcion', 'precio', 'estado')
    search_fields = ('nombre', 'tipo', 'descripcion', 'precio', 'estado')
admin.site.register(Servicio, ServicioAdmin)

class ServicioRealizadoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'cliente', 'barbero')
    search_fields = ('fecha', 'cliente__persona__nombre1', 'cliente__persona__apellidoP', 'barbero__persona__nombre1', 'barbero__persona__apellidoP')
    list_filter = ('fecha',)
admin.site.register(Servicio_Realizado, ServicioRealizadoAdmin)

class DetalleServicioAdmin(admin.ModelAdmin):
    list_display = ('Servicio', 'Servicio_Realizado')
    search_fields = ('servicio__nombre', 'servicio_realizado__fecha')

admin.site.register(Detalle_ServicioRealizado, DetalleServicioAdmin)
