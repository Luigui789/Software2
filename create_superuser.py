import os
import django

# Configura el entorno de Django antes de acceder a los modelos
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Software2.settings')  # Reemplaza 'tu_proyecto' con el nombre de tu módulo Django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()
if not User.objects.filter(username='Luigui').exists():
    User.objects.create_superuser('Luigui', 'luisfernandojose2004@gmail.com', '123456')
    print('Superuser Luigui created successfully.')
else:
    print('Superuser Luigui already exists. Skipping creation.')