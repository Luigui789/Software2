"""
ASGI config for Software2 project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import django
from django.core.asgi import get_asgi_application

# Configuración Django PRIMERO
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Software2.settings')
django.setup()  # 👈 Esto debe ir ANTES de importar routers

# Importaciones POSTERIORES a la configuración
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import Apps.aplicacion.routing

# ¡¡¡ESTAS DOS LÍNEAS FALTABAN!!!
from channels.layers import get_channel_layer # <-- AÑADIR ESTA LÍNEA
# ... (asegúrate de que esta línea esté después de django.setup())
# Define la capa de canales para que el runworker la pueda encontrar
channel_layer = get_channel_layer() # <-- AÑADIR ESTA LÍNEA (después de la definición de 'application')


application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            Apps.aplicacion.routing.websocket_urlpatterns
        )
    ),
})