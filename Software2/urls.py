from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # Tus otras rutas aquí
    path('', include('Apps.aplicacion.urls')), # Incluye las URLs de tu aplicación 'aplicacion'
]

# ESTO SOLO DEBE ESTAR ACTIVO EN DESARROLLO (DEBUG = True)
# En producción, un servidor web (como Nginx) o un CDN se encargarán de servir los archivos estáticos.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)