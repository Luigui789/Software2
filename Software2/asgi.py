"""
ASGI config for Software2 project.

It exposes the ASGI callable as a module-level variable named ``application``.
Configured for Django Channels with WebSocket support.
"""

import os
from django.core.asgi import get_asgi_application

# Configuración Django primero - esencial para Render
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Software2.settings')

# Importaciones posteriores a la configuración
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import Apps.aplicacion.routing

# Aplicación ASGI principal
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(  # Seguridad para WebSockets
        AuthMiddlewareStack(
            URLRouter(
                Apps.aplicacion.routing.websocket_urlpatterns
            )
        )
    ),
})