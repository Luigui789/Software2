from django.shortcuts import render,redirect
from django.contrib.auth import authenticate, login as auth_login
from django.utils import timezone
from datetime import timedelta

# Create your views here.

def index(request):
    return render(request, 'index.html')

# Vista para manejar el inicio de sesión

def login(request):
    # Inicializa los contadores en la sesión si no existen
    if 'login_attempts' not in request.session:
        request.session['login_attempts'] = 0
    if 'block_until' not in request.session:
        request.session['block_until'] = None

    # Si está bloqueado, verifica el tiempo
    if request.session['block_until']:
        block_until = timezone.datetime.fromisoformat(request.session['block_until'])
        if timezone.now() < block_until:
            remaining = int((block_until - timezone.now()).total_seconds())
            return render(request, 'login.html', {'error': f'Has excedido los intentos. Intenta de nuevo en {remaining} segundos.'})
        else:
            # Desbloquea
            request.session['login_attempts'] = 0
            request.session['block_until'] = None

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            request.session['login_attempts'] = 0  # Reinicia los intentos al entrar
            return redirect('index')
        else:
            request.session['login_attempts'] += 1
            if request.session['login_attempts'] >= 3:
                # Bloquea por 30 segundos
                block_until = timezone.now() + timedelta(seconds=30)
                request.session['block_until'] = block_until.isoformat()
                return render(request, 'login.html', {'error': 'Has excedido los intentos. Intenta de nuevo en 30 segundos.'})
            else:
                return render(request, 'login.html', {'error': 'Usuario o contraseña incorrectos'})
    return render(request, 'login.html')

def equipo(request):
    return render(request, 'Conoce_al_equipo.html')

def quienes(request):
    return render(request, 'Quienes_somos.html')

def contacto(request):
    return render(request, 'Contactanos.html')