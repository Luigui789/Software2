from django.contrib.auth import get_user_model

User = get_user_model()
if not User.objects.filter(username='Luigui').exists():
    User.objects.create_superuser('Luigui', 'luisfernandojose2004@gmail.com', '123456')
    print('Superuser Luigui created successfully.')
else:
    print('Superuser Luigui already exists. Skipping creation.')