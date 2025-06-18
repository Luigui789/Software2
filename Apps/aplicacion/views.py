import json
import openpyxl
import os

from django.conf import settings
from django.shortcuts import render,redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from datetime import timedelta, date, datetime
from .models import Persona, Empleado, Barbero
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Persona, Empleado, Barbero, Cliente, Servicio, Servicio_Realizado, Detalle_ServicioRealizado,Rol
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from decimal import Decimal
from functools import wraps
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa
from openpyxl.utils import get_column_letter
from django.db.models import Count
from twilio.rest import Client
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive



# Create your views here.

def rol_requerido(roles_permitidos):
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # Permitir acceso a superusuarios
            persona = Persona.objects.filter(id=request.user.pk).first()
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            if persona:
                rol_usuario = persona.rol.nombre.lower()
                if rol_usuario in [r.lower() for r in roles_permitidos]:
                    return view_func(request, *args, **kwargs)
            return redirect('login')  # O a donde prefieras
        return _wrapped_view
    return decorator

def index(request):
    return render(request, 'index.html')

# Vista para manejar el inicio de sesión

def login(request):
    # Inicializa los contadores en la sesión si no existen
    if 'login_attempts' not in request.session:
        request.session['login_attempts'] = 0
    if 'block_until' not in request.session:
        request.session['block_until'] = None
    if 'permanent_block' not in request.session:
        request.session['permanent_block'] = False

    # Si está bloqueado permanentemente
    if request.session['permanent_block']:
        return render(request, 'login.html', {'error': 'Has superado el número máximo de intentos. Contacta al administrador para desbloquear la cuenta.'})

    # Si está bloqueado temporalmente, verifica el tiempo
    if request.session['block_until']:
        block_until = timezone.datetime.fromisoformat(request.session['block_until'])
        if timezone.now() < block_until:
            remaining = int((block_until - timezone.now()).total_seconds())
            return render(request, 'login.html', {'error': f'Has excedido los intentos. Intenta de nuevo en {remaining} segundos.'})
        else:
            # Desbloquea el bloqueo temporal
            request.session['block_until'] = None

    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            # Reinicia los intentos y bloqueos al entrar
            request.session['login_attempts'] = 0
            request.session['block_until'] = None
            request.session['permanent_block'] = False
            return redirect('index')
        else:
            request.session['login_attempts'] += 1

            if request.session['login_attempts'] >= 5:
                # Bloqueo permanente
                request.session['permanent_block'] = True
                return render(request, 'login.html', {'error': 'Has superado el número máximo de intentos. Contacta al administrador para desbloquear la cuenta.'})
            elif request.session['login_attempts'] >= 3:
                # Bloqueo temporal de 30 segundos
                block_until = timezone.now() + timedelta(seconds=30)
                request.session['block_until'] = block_until.isoformat()
                return render(request, 'login.html', {'error': 'Has excedido los intentos. Intenta de nuevo en 30 segundos.'})
            else:
                return render(request, 'login.html', {'error': 'Usuario o contraseña incorrectos'})

    return render(request, 'login.html')

def logout_view(request):
    auth_logout(request)
    return redirect('login')

@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador', 'Barbero', 'Aprendiz'])
def administracion(request):
    ultimos_servicios = Servicio_Realizado.objects.order_by('-id')[:5]
    # Calcula el precio total para cada servicio realizado
    for realizado in ultimos_servicios:
        total = sum(detalle.Servicio.precio for detalle in realizado.detalle.all())
        realizado.precio_total = total
    return render(request, 'Administracion.html', {
        'ultimos_servicios': ultimos_servicios,
    })

def equipo(request):
    return render(request, 'Conoce_al_equipo.html')

def servicios(request):
    servicios = Servicio.objects.filter(estado=True)
    return render(request, 'Servicios.html', {'servicios': servicios})

def quienes(request):
    return render(request, 'Quienes_somos.html')

def contacto(request):
    return render(request, 'Contactanos.html')

@rol_requerido(['Administrador'])
def AdminBarbero(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        errores = []

        # Validaciones
        if len(data['primer_nombre']) > 15:
            errores.append("El primer nombre no puede tener más de 15 caracteres.")
        if len(data['segundo_nombre']) > 15:
            errores.append("El segundo nombre no puede tener más de 15 caracteres.")
        if len(data['primer_Apellido']) > 15:
            errores.append("El primer apellido no puede tener más de 15 caracteres.")
        if len(data['segundo_Apellido']) > 15:
            errores.append("El segundo apellido no puede tener más de 15 caracteres.")
        if len(data['telefono']) > 8:
            errores.append("El teléfono no puede tener más de 8 caracteres.")
        if len(data['usuario']) > 15:   
            errores.append("El usuario no puede tener más de 15 caracteres.")
        if len(data['Salario']) > 10:
            errores.append("El salario no puede tener más de 10 caracteres.")
        if len(data['Direccion']) > 50:
            errores.append("La dirección no puede tener más de 50 caracteres.")

        cedula = data['Cedula']
        if len(cedula) != 14:
            errores.append("La cédula debe tener exactamente 14 caracteres (13 números y 1 letra).")
        elif sum(c.isdigit() for c in cedula) != 13 or sum(c.isalpha() for c in cedula) != 1:
            errores.append("La cédula debe contener exactamente 13 números y 1 letra.")

        if not data['primer_nombre'].isalpha():
            errores.append("El primer nombre es obligatorio y solo debe contener letras.")
        if data['segundo_nombre'] and not data['segundo_nombre'].isalpha():
            errores.append("El segundo nombre solo debe contener letras.")
        if not data['primer_Apellido'].isalpha():
            errores.append("El primer apellido es obligatorio y solo debe contener letras.")
        if data['segundo_Apellido'] and not data['segundo_Apellido'].isalpha():
            errores.append("El segundo apellido solo debe contener letras.")
        if not data['telefono'].isdigit():
            errores.append("El teléfono es obligatorio y solo debe contener números.")
        if not data['usuario']:
            errores.append("El usuario es obligatorio.")
        if not data['password'] or len(data['password']) < 8:
            errores.append("La contraseña es obligatoria y debe tener al menos 8 caracteres.")
        if not data['Rol']:
            errores.append("El Rol es obligatorio.")
        if not data['Salario'] or not str(data['Salario']).replace('.', '', 1).isdigit():
            errores.append("El salario es obligatorio y debe ser un número.")
        if not data['Direccion']:
            errores.append("La dirección es obligatoria.")
        if data['email'] and '@' not in data['email']:
            errores.append("El correo electrónico no es válido.")

        if errores:
            return JsonResponse({'status': 'error', 'errores': errores})
        
        try:
            rol_obj = Rol.objects.get(nombre=data['Rol'])
        except Rol.DoesNotExist:
            return JsonResponse({'status': 'error', 'errores': ['El rol seleccionado no existe.']})

        rol_obj = Rol.objects.get(nombre=data['Rol'])

        # Inserción en las tablas
        persona = Persona.objects.create(
            nombre1=data['primer_nombre'],
            nombre2=data['segundo_nombre'],
            apellidoP=data['primer_Apellido'],
            apellidoM=data['segundo_Apellido'],
            telefono=data['telefono'],
            rol=rol_obj,  # Asignar el rol al crear la persona
            email=data['email'],
            username=data['usuario'],
            password=make_password(data['password']),
            is_active=True,
            is_staff=True,  # Asumiendo que los barberos son parte del staff
        )
        empleado = Empleado.objects.create(
            persona=persona,
            Salario=data['Salario'],
            fecha_contratacion=timezone.now()
        )
        barbero = Barbero.objects.create(
            Empleado=empleado,
            Direccion=data['Direccion'],
            cedula=data['Cedula'],
            Estado=True,
            Comisiones=0
        )
        return JsonResponse({'status': 'ok'})

    # Mostrar todos los ultimos 10 registros de barberos activos 
    barberos = Barbero.objects.select_related('Empleado__persona').filter(Estado=True).order_by('-id')[:10]
    roles = Rol.objects.all()
    return render(request, 'admin_barbero.html', {
        'barberos': barberos,
        'roles': roles,
        # ...otros contextos...
    })



def Removerbarbero(request, barbero_id):
    if request.method == 'POST':
        barbero = get_object_or_404(Barbero, id=barbero_id)
        barbero.Estado = False
        barbero.save()
        # Opcional: también puedes desactivar el usuario si quieres
        barbero.Empleado.persona.is_active = False
        barbero.Empleado.persona.save()
    return redirect('AdBarbero')  # O el nombre de tu vista de barberos

def EditarBarbero(request, barbero_id):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            errores = []

            # Validaciones de longitud
            if len(data['primer_nombre']) > 15:
                errores.append("El primer nombre no puede tener más de 15 caracteres.")
            if len(data['segundo_nombre']) > 15:
                errores.append("El segundo nombre no puede tener más de 15 caracteres.")
            if len(data['primer_Apellido']) > 15:
                errores.append("El primer apellido no puede tener más de 15 caracteres.")
            if len(data['segundo_Apellido']) > 15:
                errores.append("El segundo apellido no puede tener más de 15 caracteres.")
            if len(data['telefono']) > 8:
                errores.append("El teléfono no puede tener más de 8 caracteres.")
            if len(data['usuario']) > 15:   
                errores.append("El usuario no puede tener más de 15 caracteres.")
            if len(data['Salario']) > 10:
                errores.append("El salario no puede tener más de 10 caracteres.")
            if len(data['Direccion']) > 50:
                errores.append("La dirección no puede tener más de 50 caracteres.")

            # Validación de cédula
            cedula = data['Cedula']
            if len(cedula) != 14:
                errores.append("La cédula debe tener exactamente 14 caracteres (13 números y 1 letra).")
            elif sum(c.isdigit() for c in cedula) != 13 or sum(c.isalpha() for c in cedula) != 1:
                errores.append("La cédula debe contener exactamente 13 números y 1 letra.")

            # Validaciones de contenido
            if not data['primer_nombre'].isalpha():
                errores.append("El primer nombre es obligatorio y solo debe contener letras.")
            if data['segundo_nombre'] and not data['segundo_nombre'].isalpha():
                errores.append("El segundo nombre solo debe contener letras.")
            if not data['primer_Apellido'].isalpha():
                errores.append("El primer apellido es obligatorio y solo debe contener letras.")
            if data['segundo_Apellido'] and not data['segundo_Apellido'].isalpha():
                errores.append("El segundo apellido solo debe contener letras.")
            if not data['telefono'].isdigit():
                errores.append("El teléfono es obligatorio y solo debe contener números.")
            if not data['usuario']:
                errores.append("El usuario es obligatorio.")
            if not data['password'] or len(data['password']) < 8:
                errores.append("La contraseña es obligatoria y debe tener al menos 8 caracteres.")
            if not data['Salario'] or not str(data['Salario']).replace('.', '', 1).isdigit():
                errores.append("El salario es obligatorio y debe ser un número.")
            if not data['Direccion']:
                errores.append("La dirección es obligatoria.")
            if data['email'] and '@' not in data['email']:
                errores.append("El correo electrónico no es válido.")
            

            if errores:
                return JsonResponse({'status': 'error', 'errores': errores})

            # Actualiza los datos del barbero
            barbero = get_object_or_404(Barbero, id=barbero_id)
            persona = barbero.Empleado.persona

            persona.nombre1 = data['primer_nombre']
            persona.nombre2 = data['segundo_nombre']
            persona.apellidoP = data['primer_Apellido']
            persona.apellidoM = data['segundo_Apellido']
            persona.telefono = data['telefono']
            
            persona.email = data['email']
            persona.username = data['usuario']
            # Solo encripta si la contraseña cambió
            persona.password = data['password']

            persona.save()

            empleado = barbero.Empleado
            empleado.Salario = data['Salario']

            empleado.save()

            barbero.Direccion = data['Direccion']
            barbero.cedula = data['Cedula']
            barbero.save()

            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)})
    barbero = get_object_or_404(Barbero, id=barbero_id)
    roles = Rol.objects.all()
    return render(request, 'Editbarbero.html', {'barbero': barbero, 'roles': roles})

@rol_requerido(['Administrador', 'Barbero'])
def AdminCliente(request):
    errores = []
    if request.method == 'POST':
        nombre1 = request.POST.get('primer_nombre', '').strip()
        nombre2 = request.POST.get('segundo_nombre', '').strip()
        apellidoP = request.POST.get('primer_Apellido', '').strip()
        apellidoM = request.POST.get('segundo_Apellido', '').strip()
        instagram = request.POST.get('instagram', '').strip()
        correo = request.POST.get('email', '').strip()

        # Validaciones de longitud
        if len(nombre1) > 15:
            errores.append("El primer nombre no puede tener más de 30 caracteres.")
        if len(nombre2) > 15:
            errores.append("El segundo nombre no puede tener más de 30 caracteres.")
        if len(apellidoP) > 15:
            errores.append("El primer apellido no puede tener más de 30 caracteres.")
        if len(apellidoM) > 30:
            errores.append("El segundo apellido no puede tener más de 30 caracteres.")
        if len(instagram) > 15:
            errores.append("El usuario de Instagram no puede tener más de 50 caracteres.")
        if len(correo) > 50:
            errores.append("El correo electrónico no puede tener más de 50 caracteres.")

        # Validaciones de contenido y/o caracteres
        if not nombre1.isalpha():
            errores.append("El primer nombre es obligatorio y solo debe contener letras.")
        if nombre2 and not nombre2.isalpha():
            errores.append("El segundo nombre solo debe contener letras.")
        if not apellidoP.isalpha():
            errores.append("El primer apellido es obligatorio y solo debe contener letras.")
        if apellidoM and not apellidoM.isalpha():
            errores.append("El segundo apellido solo debe contener letras.")
        if correo and '@' not in correo:
            errores.append("El correo electrónico no es válido.")

        # Si hay errores, vuelve a mostrar el formulario con los errores
        if errores:
            clientes = Cliente.objects.all()
            return render(request, 'Admin_Cliente.html', {
                'clientes': clientes,
                'errores': errores,
                'datos': request.POST
            })

        # Si todo está bien, guarda el cliente
        Cliente.objects.create(
            nombre1=nombre1,
            nombre2=nombre2,
            apellidoP=apellidoP,
            apellidoM=apellidoM,
            instagram=instagram,
            correo=correo
        )
        return redirect('AdCliente')

    # En AdminCliente solo aparecen los ultimos 10 registros
    clientes = Cliente.objects.all().order_by('-id')[:10]
    return render(request, 'Admin_Cliente.html', {'clientes': clientes})

def EditarCliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    errores = []
    if request.method == 'POST':
        nombre1 = request.POST.get('primer_nombre', '').strip()
        nombre2 = request.POST.get('segundo_nombre', '').strip()
        apellidoP = request.POST.get('primer_Apellido', '').strip()
        apellidoM = request.POST.get('segundo_Apellido', '').strip()
        instagram = request.POST.get('instagram', '').strip()
        correo = request.POST.get('email', '').strip()

        # Validaciones de longitud
        if len(nombre1) > 15:
            errores.append("El primer nombre no puede tener más de 15 caracteres.")
        if len(nombre2) > 15:
            errores.append("El segundo nombre no puede tener más de 15 caracteres.")
        if len(apellidoP) > 15:
            errores.append("El primer apellido no puede tener más de 15 caracteres.")
        if len(apellidoM) > 15:
            errores.append("El segundo apellido no puede tener más de 30 caracteres.")
        if len(instagram) > 15:
            errores.append("El usuario de Instagram no puede tener más de 15 caracteres.")
        if len(correo) > 50:
            errores.append("El correo electrónico no puede tener más de 50 caracteres.")

        # Validaciones de contenido y/o caracteres
        if not nombre1.isalpha():
            errores.append("El primer nombre es obligatorio y solo debe contener letras.")
        if nombre2 and not nombre2.isalpha():
            errores.append("El segundo nombre solo debe contener letras.")
        if not apellidoP.isalpha():
            errores.append("El primer apellido es obligatorio y solo debe contener letras.")
        if apellidoM and not apellidoM.isalpha():
            errores.append("El segundo apellido solo debe contener letras.")
        if correo and '@' not in correo:
            errores.append("El correo electrónico no es válido.")

        if errores:
            return render(request, 'EditCliente.html', {
                'cliente': cliente,
                'errores': errores,
                'datos': request.POST
            })

        # Si todo está bien, guarda el cliente
        cliente.nombre1 = nombre1
        cliente.nombre2 = nombre2
        cliente.apellidoP = apellidoP
        cliente.apellidoM = apellidoM
        cliente.instagram = instagram
        cliente.correo = correo
        cliente.save()
        return redirect('AdCliente')
    return render(request, 'EditCliente.html', {'cliente': cliente})

@rol_requerido(['Administrador'])
def AdminServicio(request):
    errores = []
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        tipo_servicio = request.POST.get('tipo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        precio = request.POST.get('precio', '').strip()

        # Validaciones de longitud
        if len(nombre) > 50:
            errores.append("El nombre del servicio no puede tener más de 50 caracteres.")
        if len(tipo_servicio) > 30:
            errores.append("El tipo de servicio no puede tener más de 30 caracteres.")
        if len(descripcion) > 100:
            errores.append("La descripción no puede tener más de 100 caracteres.")

        # Validaciones de contenido
        if not nombre:
            errores.append("El nombre del servicio es obligatorio.")
        if not tipo_servicio:
            errores.append("El tipo de servicio es obligatorio.")
        if not descripcion:
            errores.append("La descripción es obligatoria.")
        if not precio or not precio.replace('.', '', 1).isdigit():
            errores.append("El precio es obligatorio y debe ser un número.")

        try:
            precio = float(precio)
            if precio <= 0:
                errores.append("El precio debe ser mayor a cero.")
        except ValueError:
            errores.append("El precio debe ser un número válido.")

        # Validación de nombre duplicado
        if Servicio.objects.filter(nombre__iexact=nombre).exists():
            errores.append("Ya existe un servicio con este nombre.")

        if errores:
            servicios = Servicio.objects.filter(estado=True)
            return render(request, 'admin_servicios.html', {
                'servicios': servicios,
                'errores': errores,
                'datos': request.POST
            })

        Servicio.objects.create(
            nombre=nombre,
            tipo=tipo_servicio,
            descripcion=descripcion,
            precio=precio,
            estado=True
        )
        return redirect('AdServicio')
    servicios = Servicio.objects.filter(estado=True)
    return render(request, 'admin_servicios.html', {'servicios': servicios})


def EditarServicio(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    errores = []
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        tipo_servicio = request.POST.get('tipo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        precio = request.POST.get('precio', '').strip()
        estado = request.POST.get('estado', 'True')

        # Validaciones de longitud
        if len(nombre) > 50:
            errores.append("El nombre del servicio no puede tener más de 50 caracteres.")
        if len(tipo_servicio) > 30:
            errores.append("El tipo de servicio no puede tener más de 30 caracteres.")
        if len(descripcion) > 100:
            errores.append("La descripción no puede tener más de 100 caracteres.")

        # Validaciones de contenido
        if not nombre:
            errores.append("El nombre del servicio es obligatorio.")
        if not tipo_servicio:
            errores.append("El tipo de servicio es obligatorio.")
        if not descripcion:
            errores.append("La descripción es obligatoria.")
        if not precio or not precio.replace('.', '', 1).isdigit():
            errores.append("El precio es obligatorio y debe ser un número.")

        if errores:
            return render(request, 'EditServicio.html', {
                'servicio': servicio,
                'errores': errores,
                'datos': request.POST
            })

        servicio.nombre = nombre
        servicio.tipo = tipo_servicio
        servicio.descripcion = descripcion
        servicio.precio = precio
        servicio.estado = estado.lower() == 'true'
        servicio.save()
        return redirect('AdServicio')
    return render(request, 'EditServicio.html', {'servicio': servicio})

def Removerservicio(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id)
    if request.method == 'POST':
        servicio.estado = False  # O el valor que uses para "inactivo"
        servicio.save()
    return redirect('AdServicio')

@rol_requerido(['Administrador', 'Barbero'])
def AdminServicioRealizado(request):
    clientes = Cliente.objects.all()
    barberos = Barbero.objects.filter(Estado=True)
    servicios = Servicio.objects.filter(estado=True)
    servicios_seleccionados = request.POST.getlist('Servicio') if request.method == 'POST' else []
    errores = []

    # Consulta todos los servicios realizados
    servicios_realizados = Servicio_Realizado.objects.all().order_by('-fecha')

    if request.method == 'POST':
        fecha = request.POST.get('Fecha')
        cliente_id = request.POST.get('Cliente')
        barbero_id = request.POST.get('Barbero')
        servicios_ids = request.POST.getlist('Servicio')

        # Validaciones
        if not fecha:
            errores.append("La fecha es obligatoria.")
        if not cliente_id or not Cliente.objects.filter(id=cliente_id).exists():
            errores.append("Debe seleccionar un cliente válido.")
        if not barbero_id or not Barbero.objects.filter(id=barbero_id, Estado=True).exists():
            errores.append("Debe seleccionar un barbero válido.")
        if not servicios_ids or not all(Servicio.objects.filter(id=sid, estado=True).exists() for sid in servicios_ids):
            errores.append("Debe seleccionar al menos un servicio válido.")

        if errores:
            return render(request, 'admin_ServicioRealizado.html', {
                'clientes': clientes,
                'barberos': barberos,
                'servicios': servicios,
                'errores': errores,
                'datos': request.POST,
                'servicios_seleccionados': servicios_seleccionados,
                'servicios_realizados': servicios_realizados,
            })

        # Crea el Servicio Realizado
        servicio_realizado = Servicio_Realizado.objects.create(
            fecha=fecha,
            cliente_id=cliente_id,
            barbero_id=barbero_id
        )
        # Crea el Detalle para cada servicio seleccionado
            
        for sid in servicios_ids:
            servicio = Servicio.objects.get(id=sid)
            Detalle_ServicioRealizado.objects.create(
                Servicio_id=sid,
                Servicio_Realizado=servicio_realizado
            )
            # Suma comisión al barbero
            comision = servicio.precio * Decimal('0.2')
            barbero = servicio_realizado.barbero
            barbero.Comisiones += comision
            barbero.save()

        return redirect('AdServicioRealizado')
    return render(request, 'admin_ServicioRealizado.html', {
        'clientes': clientes,
        'barberos': barberos,
        'servicios': servicios,
        'servicios_seleccionados': servicios_seleccionados,
        'servicios_realizados': servicios_realizados,
    })

def EditarServicioRealizado(request, servicio_realizado_id):
    servicio_realizado = get_object_or_404(Servicio_Realizado, id=servicio_realizado_id)
    clientes = Cliente.objects.all()
    barberos = Barbero.objects.filter(Estado=True)
    servicios = Servicio.objects.filter(estado=True)

    if request.method == 'GET':
        servicios_seleccionados = list(servicio_realizado.detalle.values_list('Servicio_id', flat=True))
        return render(request, 'EditServRealizado.html', {
            'servicio_realizado': servicio_realizado,
            'clientes': clientes,
            'barberos': barberos,
            'servicios': servicios,
            'servicios_seleccionados': servicios_seleccionados,
        })

    # Si es POST, actualiza sin validar
    fecha = request.POST.get('Fecha')
    cliente_id = request.POST.get('Cliente')
    barbero_id = request.POST.get('Barbero')
    nuevos_servicios = request.POST.getlist('Servicio')

    servicio_realizado.fecha = fecha
    servicio_realizado.cliente_id = cliente_id
    servicio_realizado.barbero_id = barbero_id
    servicio_realizado.save()

    servicio_realizado.detalle.all().delete()
    for sid in nuevos_servicios:
        Detalle_ServicioRealizado.objects.create(
            Servicio_id=sid,
            Servicio_Realizado=servicio_realizado
        )
    return redirect('AdServicioRealizado')

def filtrar_servicios_por_fecha(request):
    filtro = request.GET.get('filtro')
    hoy = date.today()
    inicio = request.GET.get('inicio')
    fin = request.GET.get('fin')

    servicios = Servicio_Realizado.objects.select_related(
        'cliente',
        'barbero__Empleado__persona'
    ).prefetch_related('detalle__Servicio')

    if filtro == 'hoy':
        servicios = servicios.filter(fecha=hoy)

    elif filtro == 'semana':
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        fin_semana = inicio_semana + timedelta(days=6)
        servicios = servicios.filter(fecha__date__range=(inicio_semana, fin_semana))

    elif filtro == 'mes':
        servicios = servicios.filter(fecha__year=hoy.year, fecha__month=hoy.month)

    elif filtro == 'rango' and inicio and fin:
        try:
            inicio_date = datetime.strptime(inicio, "%Y-%m-%d").date()
            fin_date = datetime.strptime(fin, "%Y-%m-%d").date()

            if inicio_date > fin_date:
                # No se hace render aquí. Se retorna queryset vacío y la vista principal decide.
                messages.error(request, "La fecha de inicio no puede ser mayor que la fecha final.")
                return Servicio_Realizado.objects.none()

            servicios = servicios.filter(fecha__date__range=(inicio_date, fin_date))
        except ValueError:
            messages.error(request, "Formato de fecha inválido.")
            return Servicio_Realizado.objects.none()

    return servicios

def reporte_servicios(request):
    filtro = request.GET.get('filtro')
    servicios = Servicio_Realizado.objects.select_related(
        'cliente',
        'barbero__Empleado__persona'
    ).prefetch_related('detalle__Servicio')

    hoy = timezone.now().date()

    if filtro == 'hoy':
        servicios = servicios.filter(fecha=hoy)

    elif filtro == 'semana':
        inicio = hoy - timezone.timedelta(days=hoy.weekday())
        fin = inicio + timezone.timedelta(days=6)
        servicios = servicios.filter(fecha__range=(inicio, fin))

    elif filtro == 'mes':
        servicios = servicios.filter(fecha__year=hoy.year, fecha__month=hoy.month)

    elif filtro == 'rango':
        inicio = request.GET.get('inicio')
        fin = request.GET.get('fin')
        if inicio and fin:
            try:
                inicio_date = datetime.strptime(inicio, "%Y-%m-%d").date()
                fin_date = datetime.strptime(fin, "%Y-%m-%d").date()

                if inicio_date > fin_date:
                    messages.error(request, "La fecha de inicio no puede ser mayor que la fecha final.")
                    servicios = Servicio_Realizado.objects.none()
                    context = {
                        'servicios': servicios,
                        'filtro': filtro,
                        'inicio': '',  # 👈 Limpiar campos
                        'fin': ''
                    }
                    return render(request, 'reporte_servicios.html', context)

                servicios = servicios.filter(fecha__range=(inicio_date, fin_date))

            except ValueError:
                messages.error(request, "Formato de fecha inválido.")
                servicios = Servicio_Realizado.objects.none()
                context = {
                    'servicios': servicios,
                    'filtro': filtro,
                    'inicio': '',  # 👈 Limpiar campos también aquí
                    'fin': ''
                }
                return render(request, 'reporte_servicios.html', context)

    # Calcular total por servicio
    for realizado in servicios:
        total = sum(detalle.Servicio.precio for detalle in realizado.detalle.all())
        realizado.precio_total = total

    context = {
        'servicios': servicios,
        'filtro': filtro,
        'inicio': request.GET.get('inicio', ''),
        'fin': request.GET.get('fin', ''),
    }
    return render(request, 'reporte_servicios.html', context)


def descargar_reporte_pdf(request):
    filtro = request.GET.get('filtro')
    servicios = Servicio_Realizado.objects.select_related(
        'cliente',
        'barbero__Empleado__persona'
    ).prefetch_related('detalle__Servicio')

    hoy = timezone.now().date()

    if filtro == 'hoy':
        servicios = servicios.filter(fecha=hoy)
    elif filtro == 'semana':
        inicio = hoy - timezone.timedelta(days=hoy.weekday())
        fin = inicio + timezone.timedelta(days=6)
        servicios = servicios.filter(fecha__range=(inicio, fin))
    elif filtro == 'mes':
        servicios = servicios.filter(fecha__year=hoy.year, fecha__month=hoy.month)
    elif filtro == 'rango':
        inicio = request.GET.get('inicio')
        fin = request.GET.get('fin')
        if inicio and fin:
            servicios = servicios.filter(fecha__range=(inicio, fin))

    gran_total = 0
    for realizado in servicios:
        total = sum(detalle.Servicio.precio for detalle in realizado.detalle.all())
        realizado.precio_total = total
        gran_total += total

    template = get_template('reporte_servicios_pdf.html')
    context = {'servicios': servicios, 'gran_total': gran_total}
    html = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_servicios.pdf"'
    pisa.CreatePDF(html, dest=response)
    return response

def descargar_reporte_excel(request):
    servicios = filtrar_servicios_por_fecha(request)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Servicios Realizados"

    headers = ["ID", "Fecha", "Cliente", "Barbero", "Servicios", "Total"]
    ws.append(headers)

    gran_total = 0
    for realizado in servicios:
        cliente = f"{realizado.cliente.nombre1} {realizado.cliente.apellidoP}"
        barbero = f"{realizado.barbero.Empleado.persona.nombre1} {realizado.barbero.Empleado.persona.apellidoP}"
        servicios_txt = ", ".join([detalle.Servicio.nombre for detalle in realizado.detalle.all()])
        total = float(sum(detalle.Servicio.precio for detalle in realizado.detalle.all()))
        gran_total += total
        ws.append([
            realizado.id,
            realizado.fecha.strftime('%Y-%m-%d'),  # Solo fecha sin hora
            cliente,
            barbero,
            servicios_txt,
            total
        ])

    ws.append(['', '', '', '', 'Gran Total', gran_total])

    for col in ws.columns:
        max_length = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = max_length + 2

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="reporte_servicios.xlsx"'
    wb.save(response)
    return response

def reporte_grafica(request):
    filtro = request.GET.get('filtro')
    servicios = Servicio_Realizado.objects.prefetch_related('detalle__Servicio', 'barbero__Empleado__persona')

    hoy = timezone.now().date()

    if filtro == 'hoy':
        servicios = servicios.filter(fecha=hoy)

    elif filtro == 'semana':
        inicio = hoy - timezone.timedelta(days=hoy.weekday())
        fin = inicio + timezone.timedelta(days=6)
        servicios = servicios.filter(fecha__range=(inicio, fin))

    elif filtro == 'mes':
        servicios = servicios.filter(fecha__year=hoy.year, fecha__month=hoy.month)

    elif filtro == 'rango':
        inicio = request.GET.get('inicio')
        fin = request.GET.get('fin')
        if inicio and fin:
            try:
                inicio_date = datetime.strptime(inicio, "%Y-%m-%d").date()
                fin_date = datetime.strptime(fin, "%Y-%m-%d").date()

                if inicio_date > fin_date:
                    messages.error(request, "La fecha de inicio no puede ser mayor que la fecha final.")
                    context = {
                        'labels': [],
                        'data': [],
                        'corte_labels': [],
                        'corte_data': [],
                        'filtro': filtro,
                        'inicio': '',
                        'fin': ''
                    }
                    return render(request, 'reporte_grafica.html', context)

                servicios = servicios.filter(fecha__range=(inicio_date, fin_date))

            except ValueError:
                messages.error(request, "Formato de fecha inválido.")
                context = {
                    'labels': [],
                    'data': [],
                    'corte_labels': [],
                    'corte_data': [],
                    'filtro': filtro,
                    'inicio': '',
                    'fin': ''
                }
                return render(request, 'reporte_grafica.html', context)

    # Primera gráfica: cortes por barbero
    barberos = {}
    for servicio in servicios:
        nombre = f"{servicio.barbero.Empleado.persona.nombre1}"
        barberos[nombre] = barberos.get(nombre, 0) + 1
    labels = list(barberos.keys())
    data = list(barberos.values())

    # Segunda gráfica: corte más realizado
    servicio_realizado_ids = servicios.values_list('id', flat=True)
    cortes = Detalle_ServicioRealizado.objects.filter(Servicio_Realizado_id__in=servicio_realizado_ids)
    cortes_count = cortes.values('Servicio__nombre').annotate(cantidad=Count('id')).order_by('-cantidad')

    corte_labels = [item['Servicio__nombre'] for item in cortes_count]
    corte_data = [item['cantidad'] for item in cortes_count]

    context = {
        'labels': labels,
        'data': data,
        'corte_labels': corte_labels,
        'corte_data': corte_data,
        'filtro': filtro,
        'inicio': request.GET.get('inicio', ''),
        'fin': request.GET.get('fin', ''),
    }
    return render(request, 'reporte_grafica.html', context)

#===========================================================================================================================
def generar_reporte_excel_y_guardar(servicios, filename):
    """
    Genera un archivo Excel con los servicios realizados y lo guarda localmente.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Servicios Realizados"

    headers = ["ID", "Fecha", "Cliente", "Barbero", "Servicios", "Total"]
    ws.append(headers)

    gran_total = 0
    for realizado in servicios:
        try:
            cliente = f"{realizado.cliente.nombre1} {realizado.cliente.apellidoP}"
            barbero = f"{realizado.barbero.Empleado.persona.nombre1} {realizado.barbero.Empleado.persona.apellidoP}"
        except AttributeError as e:
            print(f"Advertencia: Error al acceder a datos de cliente/barbero para ID {realizado.id}: {e}")
            cliente = "N/A"
            barbero = "N/A"
            
        servicios_list = []
        total_servicio_actual = 0
        for detalle in realizado.detalle.all():
            try:
                servicios_list.append(detalle.Servicio.nombre)
                total_servicio_actual += float(detalle.Servicio.precio)
            except AttributeError as e:
                print(f"Advertencia: Error al acceder a detalle de servicio para ID {realizado.id}: {e}")
                
        servicios_txt = ", ".join(servicios_list)
        gran_total += total_servicio_actual

        ws.append([
            realizado.id,
            realizado.fecha.strftime('%Y-%m-%d'),
            cliente,
            barbero,
            servicios_txt,
            total_servicio_actual
        ])

    ws.append(['', '', '', '', 'Gran Total', gran_total])

    ruta_reportes = os.path.join(settings.MEDIA_ROOT, 'reportes')
    os.makedirs(ruta_reportes, exist_ok=True) 

    file_path = os.path.join(ruta_reportes, filename)
    wb.save(file_path) 

    print(f"Archivo Excel '{filename}' generado y guardado en: {file_path}")
    return file_path


def subir_a_drive_y_obtener_url(path, nombre):
    """
    Sube un archivo a Google Drive, asegura el Content-Type para Twilio
    y obtiene su URL de descarga pública.
    """
    print("\n--- INICIO: Función subir_a_drive_y_obtener_url ---") 
    
    client_secrets_file_path = settings.BASE_DIR / 'Apps' / 'aplicacion' / 'client_secrets.json'
    creds_file_path = settings.BASE_DIR / 'mycreds.txt' 

    print(f"Ruta esperada de client_secrets.json: {client_secrets_file_path}") 
    print(f"Ruta esperada de mycreds.txt: {creds_file_path}") 

    gauth = GoogleAuth()
    gauth.settings['client_config_file'] = str(client_secrets_file_path)
    gauth.settings['save_credentials_file'] = str(creds_file_path)

    try:
        gauth.LoadCredentials() 
        print("Credenciales de Google Drive cargadas desde 'mycreds.txt'.")
    except Exception as e:
        print(f"No se pudieron cargar las credenciales guardadas (quizás no existen o están corruptas): {e}")
        print("Realizando autenticación web... Esto abrirá una ventana del navegador.")
        gauth.LocalWebserverAuth() 
        print("Autenticación web completada y credenciales guardadas.")

    drive = GoogleDrive(gauth)

    # --- CAMBIO CLAVE AQUÍ: Especificar mimeType al crear el archivo ---
    # Esto ayuda a Google Drive a saber qué tipo de archivo es.
    mime_type_excel = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    file_metadata = {'name': nombre, 'mimeType': mime_type_excel}
    
    gfile = drive.CreateFile(file_metadata)
    gfile.SetContentFile(path)
    gfile.Upload()
    print(f"Archivo '{nombre}' subido a Google Drive. ID: {gfile['id']}")

    gfile.InsertPermission({
        'type': 'anyone',
        'value': 'reader',
        'role': 'reader'
    })
    print("Permisos de compartir configurados a 'cualquiera con el enlace puede leer'.")

    # --- Segundo cambio clave: Obtener URL de exportación explícitamente ---
    # Esta es la forma más fiable de obtener un enlace de descarga con el Content-Type correcto.
    try:
        url_descarga = gfile.GetDownloadUrl(mimetype=mime_type_excel)
        print(f"URL de descarga (exportación XLSX): {url_descarga}")
    except Exception as e:
        print(f"Error al obtener URL de exportación XLSX: {e}. Volviendo a webContentLink/direct download.")
        # Fallback si GetDownloadUrl falla, aunque es menos probable que funcione con Twilio
        url_descarga = gfile.get('webContentLink')
        if not url_descarga:
            url_descarga = f"https://drive.google.com/uc?id={gfile['id']}&export=download"
        print(f"URL de descarga fallback: {url_descarga}")

    print(f"URL final del archivo para Twilio: {url_descarga}")
    print("--- FIN: Función subir_a_drive_y_obtener_url ---\n")
    return url_descarga


def enviar_link_whatsapp(numero, url_drive_del_reporte, nombre_reporte): # Renombrar para mayor claridad si quieres
    account_sid = settings.TWILIO_ACCOUNT_SID
    auth_token = settings.TWILIO_AUTH_TOKEN
    whatsapp_from_number = settings.TWILIO_WHATSAPP_NUMBER 

    client = Client(account_sid, auth_token)

    try:
        message = client.messages.create(
            from_=whatsapp_from_number,
            to=f'whatsapp:{numero}', 
            body=f'Aquí tienes el reporte de Excel de Mojica\'s Barbershop ({nombre_reporte}): {url_drive_del_reporte}', 
        )
        print(f"Mensaje de WhatsApp enviado. SID: {message.sid}")
        return message.sid
    except Exception as e:
        print(f"Error al enviar el mensaje de WhatsApp: {e}")
        raise 
    


def enviar_reporte_excel_whatsapp(request):
    if request.method == 'POST':
        numero = request.POST.get('numero') 

        if not numero:
            messages.error(request, "Número de WhatsApp no proporcionado.")
            return redirect('reporte_servicios')

        try:
            # Asegúrate que filtrar_servicios_por_fecha esté definida y funcione correctamente
            servicios = filtrar_servicios_por_fecha(request)
            if not servicios:
                messages.warning(request, "No se encontraron servicios para generar el reporte.")
                return redirect('reporte_servicios')
        except Exception as e:
            messages.error(request, f"Error al filtrar servicios: {e}")
            return redirect('reporte_servicios')

        filename = f'reporte_servicios_{timezone.now().strftime("%Y%m%d%H%M%S")}.xlsx'
        file_path = None
        url_drive = None 

        # --- ETAPA 1: Generar el Excel localmente ---
        try:
            file_path = generar_reporte_excel_y_guardar(servicios, filename)
            messages.info(request, f'Reporte Excel "{filename}" generado localmente.')
        except Exception as e:
            messages.error(request, f'Error al generar el reporte Excel: {e}')
            return redirect('reporte_servicios') 

        # --- ETAPA 2: Subir a Google Drive y obtener el URL público ---
        try:
            # Esta es la función que sube a Drive y obtiene el enlace
            url_drive = subir_a_drive_y_obtener_url(file_path, filename)
            messages.info(request, 'Reporte subido y compartido en Google Drive.')
        except Exception as e:
            messages.error(request, f'Error al subir el reporte a Google Drive: {e}. '
                                    'Asegúrate de que las credenciales de PyDrive estén bien y la API de Drive habilitada.')
            # Limpiar el archivo local si la subida falla
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            return redirect('reporte_servicios') 

        # --- ETAPA 3: Enviar ENLACE por WhatsApp ---
        try:
            # Llamada a la función que envía el ENLACE (¡no el adjunto!)
            # Pasa el nombre del archivo para que aparezca en el cuerpo del mensaje
            sid = enviar_link_whatsapp(numero, url_drive, filename) 
            messages.success(request, f'Enlace del reporte enviado exitosamente a WhatsApp. SID: {sid}')
        except Exception as e:
            messages.error(request, f'Error al enviar el reporte por WhatsApp: {e}. '
                                    'Revisa tu configuración de Twilio y el número de destino.')

        # --- LIMPIEZA: Eliminar el archivo local después de usarlo ---
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Archivo local '{file_path}' eliminado.")
            except Exception as e:
                print(f"Advertencia: No se pudo eliminar el archivo local '{file_path}': {e}")

    return redirect('reporte_servicios')