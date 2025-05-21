from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login, name='login'),
    path('Equipo/', views.equipo, name='Equipo'),
    path('Quienes_Somos/', views.quienes, name='Quienes_Somos'),
    path('Contactanos/', views.contacto, name='Contactanos'),
]