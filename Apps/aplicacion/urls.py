from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('Equipo/', views.equipo, name='Equipo'),
    path('Quienes_Somos/', views.quienes, name='Quienes_Somos'),
    path('Contactanos/', views.contacto, name='Contactanos'),
    path('administracion/', views.administracion, name='administracion'),


    path('AdBarbero/', views.AdminBarbero, name='AdBarbero'),
    path('editar_barbero/<int:barbero_id>/', views.EditarBarbero, name='editar_barbero'),
    path('remover_barbero/<int:barbero_id>/', views.Removerbarbero, name='remover_barbero'),

    path('AdCliente/', views.AdminCliente, name='AdCliente'),
    path('editar_cliente/<int:cliente_id>/', views.EditarCliente, name='editar_cliente'),

    path('AdServicio/', views.AdminServicio, name='AdServicio'),
    path('editar_servicio/<int:servicio_id>/', views.EditarServicio, name='editar_servicio'),
    path('remover_servicio/<int:servicio_id>/', views.Removerservicio, name='remover_servicio'),

    path('AdServicioRealizado/', views.AdminServicioRealizado, name='AdServicioRealizado'),
    path('editar_servicioRealizado/<int:servicio_realizado_id>/', views.EditarServicioRealizado, name='editar_servicioRealizado'),

    path('reporte-servicios/', views.reporte_servicios, name='reporte_servicios'),
    path('reporte-servicios/pdf/', views.descargar_reporte_pdf, name='descargar_reporte_pdf'),
    path('reporte-servicios/excel/', views.descargar_reporte_excel, name='descargar_reporte_excel'),
    path('reporte-graficas/', views.reporte_grafica, name='reporte_graficas'),

    path('login/', views.login, name='login'),
    path('logout/', views.logout_view, name='logout'),

]