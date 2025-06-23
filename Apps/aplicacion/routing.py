from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # Define la ruta para las conexiones WebSocket.
    # (?P<barber_id>\d+) captura un número entero como 'barber_id'.
    re_path(r'ws/queue/(?P<barber_id>[a-zA-Z0-9_.-]+)/$', consumers.QueueConsumer.as_asgi()),
]