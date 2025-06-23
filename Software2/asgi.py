"""
ASGI config for Software2 project.

It exposes the ASGI callable as a module-level variable named ``application``.
"""

import os
from django.core.asgi import get_asgi_application

# Configura Django primero
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Software2.settings')
django_asgi_app = get_asgi_application()

# Importaciones de Channels DESPUÉS de configurar Django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator

# Importa tus rutas WebSocket aquí (no al inicio del archivo)
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                # Importa las rutas aquí mismo para evitar problemas
                __import__('Apps.aplicacion.routing').aplicacion.routing.websocket_urlpatterns
            )
        )
    ),
})