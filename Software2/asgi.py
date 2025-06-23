"""
ASGI config for Software2 project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os
import django



# 🔧 Configura e inicializa Django ANTES de importar rutas
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Software2.settings')
django.setup()


import Apps.aplicacion.routing

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            Apps.aplicacion.routing.websocket_urlpatterns
        )
    ),
})
