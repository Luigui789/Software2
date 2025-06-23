import json
import openpyxl
import os
import re

from .utils import safe_channel_name
from django.conf import settings
from django.shortcuts import render,redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import Group
from django.utils import timezone
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from datetime import timedelta, date, datetime
from django.http import JsonResponse,HttpResponse
from .models import Persona, Empleado, Barbero, BarberQueue, Cliente, Servicio, Servicio_Realizado, Detalle_ServicioRealizado,Rol
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation
from functools import wraps
from django.template.loader import get_template
from xhtml2pdf import pisa
from openpyxl.utils import get_column_letter
from django.db.models import Count, ObjectDoesNotExist
from django.db import transaction
from twilio.rest import Client
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
# Create your views here.

def rol_requerido(roles_permitidos):
    def decorator(view_func):
        # Opcional: Usar el decorador login_required de Django para asegurar que el usuario esté autenticado.
        # Si ya usas @login_required en tus vistas, no necesitas esto aquí.
        # @login_required 
        def _wrapped_view(request, *args, **kwargs):
            # 1. Verificar si el usuario está autenticado al principio
            if not request.user.is_authenticated:
                messages.error(request, "Debes iniciar sesión para acceder a esta página.")
                return redirect('aplicacion:login') # Redirigir a login si no está autenticado

            # 2. Permitir acceso a superusuarios primero
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            try:
                persona = Persona.objects.get(id=request.user.pk)
            except Persona.DoesNotExist:
                # El usuario autenticado no tiene un registro de Persona asociado.
                messages.error(request, "Tu cuenta de usuario no está asociada a un perfil de persona válido.")
                return redirect('aplicacion:login') # O a una página de error/perfil incompleto

            # 3. Verificar si la persona tiene un rol asignado
            if not persona.rol:
                messages.warning(request, "Tu cuenta de usuario no tiene un rol asignado. Acceso denegado.")
                return redirect('aplicacion:login') # O a una página donde se pueda asignar un rol

            # 4. Verificar el rol
            rol_usuario = persona.rol.nombre.lower()
            if rol_usuario in [r.lower() for r in roles_permitidos]:
                return view_func(request, *args, **kwargs)
            else:
                messages.error(request, "No tienes los permisos necesarios para acceder a esta página.")
                return redirect('aplicacion:index') # O a una página de "acceso denegado"
        return _wrapped_view
    return decorator

def assign_persona_to_group_by_rol(persona_instance, request=None):
    if persona_instance.rol:
        cargo_name = persona_instance.rol.nombre
        try:
            target_group = Group.objects.get(name=cargo_name)
            persona_instance.groups.clear() # Limpia grupos existentes (siempre quieres 1 por Rol)
            persona_instance.groups.add(target_group)
            return True
        except Group.DoesNotExist:
            error_msg = f"Error: El grupo de Django '{cargo_name}' (basado en el Rol) no existe. Asegúrese de crearlo en el admin."
            if request:
                messages.error(request, error_msg)
            else:
                print(f"ERROR: {error_msg}")
            return False
        except Exception as e:
            error_msg = f"Error inesperado al asignar el grupo de Django: {e}"
            if request:
                messages.error(request, error_msg)
            else:
                print(f"ERROR: {error_msg}")
            return False
    else:
        # Si la Persona no tiene un rol asignado, puedes decidir si es un error
        warning_msg = f"Advertencia: La persona {persona_instance.username} no tiene un Rol asignado, por lo que no se asignará a un grupo de Django específico."
        if request:
            messages.warning(request, warning_msg)
        else:
            print(warning_msg)
        return True # Se considera un éxito si no hay rol que asignar

def index(request):
    return render(request, 'aplicacion/index.html')

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
        return render(request, 'aplicacion/login.html', {'error': 'Has superado el número máximo de intentos. Contacta al administrador para desbloquear la cuenta.'})

    # Si está bloqueado temporalmente, verifica el tiempo
    if request.session['block_until']:
        block_until = timezone.datetime.fromisoformat(request.session['block_until'])
        if timezone.now() < block_until:
            remaining = int((block_until - timezone.now()).total_seconds())
            return render(request, 'aplicacion/login.html', {'error': f'Has excedido los intentos. Intenta de nuevo en {remaining} segundos.'})
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
            return redirect('aplicacion:index')
        else:
            request.session['login_attempts'] += 1

            if request.session['login_attempts'] >= 5:
                # Bloqueo permanente
                request.session['permanent_block'] = True
                return render(request, 'aplicacion/login.html', {'error': 'Has superado el número máximo de intentos. Contacta al administrador para desbloquear la cuenta.'})
            elif request.session['login_attempts'] >= 3:
                # Bloqueo temporal de 30 segundos
                block_until = timezone.now() + timedelta(seconds=30)
                request.session['block_until'] = block_until.isoformat()
                return render(request, 'aplicacion/login.html', {'error': 'Has excedido los intentos. Intenta de nuevo en 30 segundos.'})
            else:
                return render(request, 'aplicacion/login.html', {'error': 'Usuario o contraseña incorrectos'})

    return render(request, 'aplicacion/login.html')

def logout_view(request):
    auth_logout(request)
    return redirect('aplicacion:login')

@login_required(login_url='login')
@rol_requerido(['Administrador', 'Barbero', 'Aprendiz'])
@permission_required(
    (
    'aplicacion.view_servicio_realizado',
    'aplicacion.view_detalle_serviciorealizado',
    'aplicacion.view_cliente'
    ), raise_exception=True)
def administracion(request):
    ultimos_servicios_query = Servicio_Realizado.objects.all()

    # --- Determinar el rol para la lógica de filtrado de la vista ---
    user_rol = None
    if request.user.is_superuser:
        # Si es un superusuario, tratarlo como 'administrador' para la lógica de datos
        user_rol = 'administrador'
    elif hasattr(request.user, 'rol') and request.user.rol:
        # Para usuarios regulares, obtener el rol de su objeto Persona
        user_rol = request.user.rol.nombre.lower()

    # --- Lógica de filtrado de servicios basada en el rol del usuario ---
    if user_rol == 'administrador':
        # Administradores (y superusuarios) ven todos los servicios
        ultimos_servicios_query = ultimos_servicios_query.order_by('-fecha', '-id')
    elif user_rol == 'barbero' or user_rol == 'aprendiz':
        # Barberos y aprendices solo ven los servicios en los que son el barbero
        try:
            # Obtener el objeto Empleado asociado a la Persona logueada (request.user es Persona)
            empleado_asociado = Empleado.objects.get(persona=request.user)
            # Obtener el objeto Barbero asociado a ese Empleado
            barbero_asociado = Barbero.objects.get(Empleado=empleado_asociado) # Aquí 'Empleado' es el campo ForeignKey en Barbero
            
            ultimos_servicios_query = ultimos_servicios_query.filter(barbero=barbero_asociado).order_by('-fecha', '-id')
        except (Empleado.DoesNotExist, Barbero.DoesNotExist):
            messages.warning(request, "Tu perfil de barbero no está correctamente asociado. No se pueden mostrar tus servicios.")
            ultimos_servicios_query = ultimos_servicios_query.none() # No mostrar nada
        except Exception as e:
            messages.error(request, f"Error inesperado al filtrar servicios: {e}")
            ultimos_servicios_query = ultimos_servicios_query.none() # No mostrar nada
    else:
        # Este bloque solo debería ser alcanzado si el usuario no tiene un rol válido
        # o si hay algún problema inesperado con request.user.rol,
        # ya que el decorador @rol_requerido ya debería haber filtrado.
        messages.error(request, "Acceso no autorizado para tu rol.")
        return redirect('aplicacion:index') # O a una página de acceso denegado

    # --- Optimización de consultas con select_related y prefetch_related ---
    ultimos_servicios = ultimos_servicios_query.select_related(
        'cliente',
        'barbero',
        'barbero__Empleado',
        'barbero__Empleado__persona'
    ).prefetch_related(
        'detalle__Servicio'
    ).distinct()[:5]

    # --- Calcular el precio total y preparar datos para la plantilla ---
    for realizado in ultimos_servicios:
        total = 0
        for detalle in realizado.detalle.all():
            if hasattr(detalle, 'Servicio') and detalle.Servicio and hasattr(detalle.Servicio, 'precio'):
                total += float(detalle.Servicio.precio)
        realizado.precio_total = total

        # Pre-formatear nombres para la plantilla
        realizado.cliente_nombre_completo = f"{realizado.cliente.nombre1} {realizado.cliente.apellidoP}" \
            if realizado.cliente and realizado.cliente.nombre1 and realizado.cliente.apellidoP \
            else "Cliente Desconocido"

        barbero_persona = realizado.barbero.Empleado.persona if realizado.barbero and realizado.barbero.Empleado and hasattr(realizado.barbero.Empleado, 'persona') else None
        realizado.barbero_nombre_completo = f"{barbero_persona.nombre1} {barbero_persona.apellidoP}" \
                    if barbero_persona and barbero_persona.nombre1 and barbero_persona.apellidoP \
            else "Barbero Desconocido"

    return render(request, 'aplicacion/Administracion.html', {
        'ultimos_servicios': ultimos_servicios,
    })


def equipo(request):
    return render(request, 'aplicacion/Conoce_al_equipo.html')

def servicios(request):
    servicios = Servicio.objects.filter(estado=True)
    return render(request, 'aplicacion/Servicios.html', {'servicios': servicios})

def quienes(request):
    return render(request, 'aplicacion/Quienes_somos.html')

def contacto(request):
    return render(request, 'aplicacion/Contactanos.html')

# Constantes de longitud máxima (sincronizadas con tus modelos)
MAX_LEN_NOMBRE = 15
MAX_LEN_APELLIDO = 15
MAX_LEN_TELEFONO = 15 # Tu modelo lo tiene en 15, no en 8
MAX_LEN_USUARIO = 15
MAX_LEN_CEDULA = 14
MIN_LEN_PASSWORD = 8

# Función para validar cédula (ejemplo, puede necesitar más reglas específicas de Nicaragua)
def validar_cedula_nicaragua(cedula):
    if len(cedula) != 14:
        return False, "La cédula debe tener exactamente 14 caracteres."
    # Cédulas nicaragüenses son NNN-NNNNNN-NLLLL, pero la validación actual es 13 dígitos y 1 letra.
    # Ajusta según el formato real. Por ahora, me baso en tu lógica.
    numeros = sum(c.isdigit() for c in cedula)
    letras = sum(c.isalpha() for c in cedula)
    if numeros != 13 or letras != 1:
        return False, "La cédula debe contener exactamente 13 números y 1 letra (ej. XXXXXXXXXXXXL)."
    return True, ""


@login_required(login_url='login')
@rol_requerido(['Administrador'])
@permission_required('aplicacion.add_barbero', raise_exception=True)
def AdminBarbero(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'errores': ['Formato de datos JSON inválido.']})

        errores = []

        # 1. Validación de campos obligatorios y tipo de datos
        required_fields = ['primer_nombre', 'primer_Apellido', 'telefono', 'usuario', 'password', 'Rol', 'Salario', 'Direccion', 'Cedula']
        for field in required_fields:
            if not data.get(field): # Usa .get() para evitar KeyError si el campo no existe
                errores.append(f"El campo '{field.replace('_', ' ').capitalize()}' es obligatorio.")

        # Si faltan campos obligatorios, no tiene sentido continuar con otras validaciones
        if errores:
            return JsonResponse({'status': 'error', 'errores': errores})

        # 2. Validaciones de longitud y contenido
        # Nombres y Apellidos
        if len(data['primer_nombre']) > MAX_LEN_NOMBRE or not data['primer_nombre'].isalpha():
            errores.append(f"El primer nombre es obligatorio, solo letras y no más de {MAX_LEN_NOMBRE} caracteres.")
        if data.get('segundo_nombre'): # Usar .get() para campos opcionales
            if len(data['segundo_nombre']) > MAX_LEN_NOMBRE or not data['segundo_nombre'].isalpha():
                errores.append(f"El segundo nombre solo letras y no más de {MAX_LEN_NOMBRE} caracteres.")
        
        if len(data['primer_Apellido']) > MAX_LEN_APELLIDO or not data['primer_Apellido'].isalpha():
            errores.append(f"El primer apellido es obligatorio, solo letras y no más de {MAX_LEN_APELLIDO} caracteres.")
        if data.get('segundo_Apellido'):
            if len(data['segundo_Apellido']) > MAX_LEN_APELLIDO or not data['segundo_Apellido'].isalpha():
                errores.append(f"El segundo apellido solo letras y no más de {MAX_LEN_APELLIDO} caracteres.")

        # Teléfono
        if len(data['telefono']) > MAX_LEN_TELEFONO or not data['telefono'].isdigit():
            errores.append(f"El teléfono es obligatorio, solo números y no más de {MAX_LEN_TELEFONO} caracteres.")
        if Persona.objects.filter(telefono__iexact=data['telefono']).exists(): # __iexact para case-insensitive
            errores.append("El teléfono ya está en uso por otro usuario.")

        # Usuario
        if len(data['usuario']) > MAX_LEN_USUARIO:
            errores.append(f"El usuario no puede tener más de {MAX_LEN_USUARIO} caracteres.")
        # Validación de unicidad de usuario
        if Persona.objects.filter(username__iexact=data['usuario']).exists(): # __iexact para case-insensitive
            errores.append("El nombre de usuario ya está en uso.")

        # Contraseña
        password = data['password']
        if len(password) < MIN_LEN_PASSWORD:
            errores.append(f"La contraseña es obligatoria y debe tener al menos {MIN_LEN_PASSWORD} caracteres.")
        # Validaciones de complejidad de contraseña (ejemplo)
        if not re.search(r'[A-Z]', password):
            errores.append("La contraseña debe incluir al menos una letra mayúscula.")
        if not re.search(r'[a-z]', password):
            errores.append("La contraseña debe incluir al menos una letra minúscula.")
        if not re.search(r'\d', password):
            errores.append("La contraseña debe incluir al menos un número.")
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password): # Añade los caracteres especiales que desees
            errores.append("La contraseña debe incluir al menos un carácter especial.")

        # Salario
        try:
            salario_value = Decimal(str(data['Salario'])) # Convertir a Decimal para precisión
            # Validación de decimales y tamaño, si lo deseas mantener aquí
            # Modelo tiene max_digits=10, decimal_places=2. 
            # Esto significa 8 dígitos antes del punto (10 - 2 = 8)
            if salario_value.as_tuple().exponent < -2: # Si tiene más de 2 decimales
                errores.append("El salario puede tener como máximo 2 decimales.")
            # Convertir a cadena para contar dígitos antes del punto
            if len(str(int(salario_value))) > 8: # Max 8 dígitos enteros
                errores.append("El salario es demasiado grande. Máximo 8 dígitos antes del punto.")
        except (ValueError, TypeError):
            errores.append("El salario debe ser un número válido.")
        # Asegurarse de que salario_value esté definido aunque haya un error en el try
        if 'salario_value' not in locals(): # Si la conversión falló y salario_value no se definió
            salario_value = Decimal('0.00') # Valor por defecto para evitar KeyError en la creación

        # Dirección
        # Direccion es TextField, no tiene max_length en el modelo, pero puedes poner un límite si quieres
        if not data['Direccion']:
            errores.append("La dirección es obligatoria.")
        if len(data['Direccion']) > 255: # Límite razonable para un TextField si no hay max_length
            errores.append("La dirección es demasiado larga.")

        # Cédula
        cedula_ok, cedula_msg = validar_cedula_nicaragua(data['Cedula'])
        if not cedula_ok:
            errores.append(cedula_msg)
        # Validación de unicidad de cédula
        if Barbero.objects.filter(cedula=data['Cedula']).exists():
            errores.append("La cédula ya está registrada para otro barbero.")

        # Email
        email = data.get('email') # Es opcional en tu modelo
        if email:
            if '@' not in email or '.' not in email:
                errores.append("El correo electrónico no es válido.")
            # Validación de unicidad de email (si email se usa como único en Persona)
            if Persona.objects.filter(email__iexact=email).exists():
                errores.append("El correo electrónico ya está en uso.")


        if errores:
            return JsonResponse({'status': 'error', 'errores': errores})
        
        # 3. Validar y obtener el objeto Rol
        try:
            rol_obj = Rol.objects.get(nombre=data['Rol'])
        except Rol.DoesNotExist:
            return JsonResponse({'status': 'error', 'errores': ['El rol seleccionado no existe.']})

        # --- TRANSACCIÓN ATÓMICA PARA CREAR OBJETOS RELACIONADOS ---
        try:
            with transaction.atomic():
                persona = Persona.objects.create(
                    nombre1=data['primer_nombre'],
                    nombre2=data.get('segundo_nombre', ''), # Use .get para campos opcionales y valor por defecto
                    apellidoP=data['primer_Apellido'],
                    apellidoM=data.get('segundo_Apellido', ''),
                    telefono=data['telefono'],
                    rol=rol_obj,
                    email=data.get('email', ''), # Usar .get para campos opcionales
                    username=data['usuario'],
                    password=make_password(password), # Usar la variable 'password' limpia
                    is_active=True,
                    is_staff=(rol_obj.nombre == 'Administrador'), # True si es Admin, False en otro caso
                    is_superuser=(rol_obj.nombre == 'Administrador') # True si es Admin, False en otro caso
                )

                # 2. Asignar el Grupo de Django a la Persona
                # Esto es crucial: llama a la función aquí
                if not assign_persona_to_group_by_rol(persona, request):
                    # Si falla la asignación del grupo, forzar la reversión de la transacción
                    raise Exception("Fallo la asignación del grupo de la Persona.")

                # 3. Crear Empleado (si aplica)
                if rol_obj.nombre in ['Barbero', 'Aprendiz', 'Administrador']: # Administrador también puede ser empleado
                    empleado = Empleado.objects.create(
                        persona=persona,
                        Salario=salario_value, # Usar el Decimal convertido
                        fecha_contratacion=timezone.now()
                    )
                else: # Si el rol no requiere ser empleado (ej. un rol futuro de "Cliente Interno")
                    empleado = None 

                # 4. Crear Barbero (si aplica)
                if rol_obj.nombre == 'Barbero':
                    # Asegúrate de que el empleado se creó
                    if empleado:
                        barbero = Barbero.objects.create(
                            Empleado=empleado,
                            Direccion=data['Direccion'],
                            cedula=data['Cedula'],
                            Estado=True,
                            Comisiones=Decimal('0.00')
                        )
                        # Opcional: Crear una cola de barbero para él si aplica
                        BarberQueue.get_or_create_queue_for_barber(barbero)
                    else:
                        raise Exception("No se pudo crear el Empleado para el Barbero.")

                return JsonResponse({'status': 'ok', 'mensaje': 'Usuario y perfil creados exitosamente.'})

        except Exception as e:
            # Capturar cualquier otro error durante la creación/asignación y revertir la transacción
            print(f"DEBUG: Error en transacción: {e}") # Para depuración
            return JsonResponse({'status': 'error', 'errores': [f'Error al procesar la solicitud: {str(e)}']})

    # Si es una solicitud GET, renderiza la plantilla
    barberos = Barbero.objects.select_related('Empleado__persona__rol').filter(Estado=True).order_by('-id')[:10]
    roles = Rol.objects.all() # Necesitarás los roles para el select en el frontend
    return render(request, 'aplicacion/admin_barbero.html', {
        'barberos': barberos,
        'roles': roles,
    })

@login_required(login_url='login')
@rol_requerido(['Administrador'])
@permission_required('aplicacion.delete_barbero', raise_exception=True)
def Removerbarbero(request, barbero_id):
    if request.method == 'POST':
        try:
            barbero = get_object_or_404(Barbero, id=barbero_id)

            with transaction.atomic():
                barbero.Estado = False  # Desactivar el barbero
                barbero.save()

                # Desactivar la cuenta de usuario (Persona) asociada
                # Acceso a través de las relaciones: Barbero -> Empleado -> Persona
                # Asegurarse de que Empleado y Persona existen antes de intentar acceder
                if hasattr(barbero, 'Empleado') and hasattr(barbero.Empleado, 'persona'):
                    barbero.Empleado.persona.is_active = False
                    barbero.Empleado.persona.save()
                else:
                    # Esto no debería pasar si las FK son obligatorias, pero es un fallback
                    messages.warning(request, f'Advertencia: No se pudo desactivar la cuenta de usuario para el barbero "{barbero.id}" (Empleado/Persona no encontrados).')

            # Mensaje de éxito al usuario
            messages.success(request, f'Barbero "{barbero.Empleado.persona.username if hasattr(barbero.Empleado, "persona") else barbero.id}" y su cuenta de usuario han sido desactivados exitosamente.')
            
            # Redirigir a la vista de administración de barberos
            return redirect('aplicacion:AdBarbero') 

        except Barbero.DoesNotExist:
            # Esto ya lo maneja get_object_or_404, pero se añade un mensaje por claridad
            messages.error(request, 'El barbero especificado no fue encontrado.')
            return redirect('aplicacion:AdBarbero') # Redirigir de vuelta con el error

        except Exception as e:
            # Capturar cualquier otro error inesperado durante el proceso
            messages.error(request, f'Ocurrió un error inesperado al desactivar el barbero: {str(e)}')
            return redirect('aplicacion:AdBarbero')

    else:
        # Si la petición no es POST, se considera un error o un intento de acceso directo
        messages.warning(request, "Acceso no permitido. Por favor, utiliza el formulario de desactivación.")
        return redirect('aplicacion:AdBarbero') # O podrías devolver un HttpResponseNotAllowed(['POST'])

@login_required(login_url='login')
@rol_requerido(['Administrador']) # Solo administradores pueden editar barberos
@permission_required('aplicacion.change_barbero', raise_exception=True)
def EditarBarbero(request, barbero_id):
    # Obtener el objeto Barbero a editar o devolver 404
    barbero_existente = get_object_or_404(Barbero, id=barbero_id)
    empleado_existente = barbero_existente.Empleado
    persona_existente = barbero_existente.Empleado.persona

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'title': 'Error de Solicitud',
                'message': 'Formato de datos JSON inválido. Por favor, verifica el envío.',
                'errores': []
            })
        errores = []
        # --- VALIDACIONES DE DATOS ---
        # 1. Validación de campos obligatorios y tipo de datos
        required_fields = ['primer_nombre', 'primer_Apellido', 'telefono', 'usuario', 'Salario', 'Direccion', 'Cedula']
        for field in required_fields:
            if not data.get(field):
                errores.append(f"El campo '{field.replace('_', ' ').capitalize()}' es obligatorio.") 
        # Validar que el campo 'Rol' no sea nulo si lo pasas, aunque no lo editas

        if errores:
            return JsonResponse({'status': 'error', 'title': 'Errores de Validación', 'message': 'Por favor, corrige los siguientes problemas:', 'errores': errores})

        # 2. Validaciones de longitud y contenido
        if len(data['primer_nombre']) > MAX_LEN_NOMBRE or not data['primer_nombre'].isalpha():
            errores.append(f"El primer nombre es obligatorio, solo letras y no más de {MAX_LEN_NOMBRE} caracteres.")
        if data.get('segundo_nombre'):
            if len(data['segundo_nombre']) > MAX_LEN_NOMBRE or not data['segundo_nombre'].isalpha():
                errores.append(f"El segundo nombre solo letras y no más de {MAX_LEN_NOMBRE} caracteres.")
        
        if len(data['primer_Apellido']) > MAX_LEN_APELLIDO or not data['primer_Apellido'].isalpha():
            errores.append(f"El primer apellido es obligatorio, solo letras y no más de {MAX_LEN_APELLIDO} caracteres.")
        if data.get('segundo_Apellido'):
            if len(data['segundo_Apellido']) > MAX_LEN_APELLIDO or not data['segundo_Apellido'].isalpha():
                errores.append(f"El segundo apellido solo letras y no más de {MAX_LEN_APELLIDO} caracteres.")

        # Teléfono
        if len(data['telefono']) > MAX_LEN_TELEFONO or not data['telefono'].isdigit():
            errores.append(f"El teléfono es obligatorio, solo números y no más de {MAX_LEN_TELEFONO} caracteres.")
        # Validación de unicidad de teléfono (excluyendo el propio barbero)
        if Persona.objects.filter(telefono=data['telefono']).exclude(id=persona_existente.id).exists():
            errores.append("El número de teléfono ya está registrado para otra persona.")

        # Usuario
        if len(data['usuario']) > MAX_LEN_USUARIO:
            errores.append(f"El usuario no puede tener más de {MAX_LEN_USUARIO} caracteres.")
        # Validación de unicidad de usuario (excluyendo el propio barbero)
        if Persona.objects.filter(username__iexact=data['usuario']).exclude(id=persona_existente.id).exists():
            errores.append("El nombre de usuario ya está en uso por otra persona.")

        # Contraseña (manejo especial para edición: solo si se proporciona una nueva)
        new_password = data.get('password', '') # Obtener la contraseña, vacía si no se envía
        if new_password: # Si se proporciona una nueva contraseña, validarla
            if len(new_password) < MIN_LEN_PASSWORD:
                errores.append(f"La contraseña debe tener al menos {MIN_LEN_PASSWORD} caracteres.")
            if not re.search(r'[A-Z]', new_password):
                errores.append("La contraseña debe incluir al menos una letra mayúscula.")
            if not re.search(r'[a-z]', new_password):
                errores.append("La contraseña debe incluir al menos una letra minúscula.")
            if not re.search(r'\d', new_password):
                errores.append("La contraseña debe incluir al menos un número.")
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', new_password):
                errores.append("La contraseña debe incluir al menos un carácter especial.")

        # Salario
        try:
            salario_value = Decimal(str(data['Salario'])) # Convertir a Decimal
            # Modelo tiene max_digits=10, decimal_places=2. Esto significa 8 dígitos antes del punto (10 - 2 = 8)
            if salario_value.as_tuple().exponent < -2: # Si tiene más de 2 decimales
                errores.append("El salario puede tener como máximo 2 decimales.")
            if len(str(int(salario_value))) > 8: # Máximo 8 dígitos enteros
                errores.append("El salario es demasiado grande. Máximo 8 dígitos antes del punto.")
        except (ValueError, TypeError):
            errores.append("El salario debe ser un número válido.")

        # Dirección (TextField)
        if not data['Direccion']:
            errores.append("La dirección es obligatoria.")
        if len(data['Direccion']) > 255: # Límite razonable para TextField
            errores.append("La dirección es demasiado larga.")

        # Cédula
        cedula_ok, cedula_msg = validar_cedula_nicaragua(data['Cedula'])
        if not cedula_ok:
            errores.append(cedula_msg)
        # Validación de unicidad de cédula (excluyendo el propio barbero)
        if Barbero.objects.filter(cedula=data['Cedula']).exclude(id=barbero_existente.id).exists():
            errores.append("La cédula ya está registrada para otro barbero.")

        # Email
        email = data.get('email', '')
        if email:
            if '@' not in email or '.' not in email:
                errores.append("El correo electrónico no es válido.")
            # Validación de unicidad de email (excluyendo el propio barbero)
            if Persona.objects.filter(email__iexact=email).exclude(id=persona_existente.id).exists():
                errores.append("El correo electrónico ya está en uso por otra persona.")

        if errores:
            return JsonResponse({'status': 'error', 'title': 'Errores de Validación', 'message': 'Por favor, corrige los siguientes problemas:', 'errores': errores})

        # --- ACTUALIZACIÓN DE DATOS CON TRANSACCIÓN ATÓMICA ---
        try:
            with transaction.atomic():
                # Actualizar Persona
                persona_existente.nombre1 = data['primer_nombre']
                persona_existente.nombre2 = data.get('segundo_nombre', '')
                persona_existente.apellidoP = data['primer_Apellido']
                persona_existente.apellidoM = data.get('segundo_Apellido', '')
                persona_existente.telefono = data['telefono']
                persona_existente.email = data.get('email', '')
                persona_existente.username = data['usuario']
                
                # Solo actualizar la contraseña si se proporcionó una nueva
                if new_password:
                    persona_existente.password = make_password(new_password)
                
                persona_existente.save()
                if not assign_persona_to_group_by_rol(persona_existente, request):
                    # Si hay un error al asignar el grupo (ej. el grupo no existe),
                    # se lanzará una excepción que revertirá la transacción.
                    raise Exception("Fallo la asignación del grupo de Django para la Persona.")

                # Actualizar Empleado
                empleado_existente = barbero_existente.Empleado
                empleado_existente.Salario = salario_value # Usar el valor float convertido
                empleado_existente.save()

                # Actualizar Barbero
                barbero_existente.Direccion = data['Direccion']
                barbero_existente.cedula = data['Cedula']
                barbero_existente.save()

            return JsonResponse({
                'status': 'ok', # O 'success'
                'title': '¡Éxito!',
                'message': 'Datos del barbero actualizados exitosamente.'
            })

        except Exception as e:
            import traceback
            print('--- Error al guardar barbero ---')
            print(e)
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'title': 'Error al Actualizar',
                'message': f'Ocurrió un error inesperado al guardar los cambios: {str(e)}',
                'errores': [str(e)] 
            })

    # Si es una petición GET, renderizar la página de edición con los datos actuales del barbero
    roles = Rol.objects.all() # Necesitas los roles para el select en el formulario
    return render(request, 'aplicacion/Editbarbero.html', {'barbero': barbero_existente, 'roles': roles})

@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador', 'Barbero'])
@permission_required('aplicacion.add_cliente', raise_exception=True)
def AdminCliente(request):
    errores = [] # Lista para almacenar los mensajes de error
    
    if request.method == 'POST':
        # Obtención y limpieza de datos
        nombre1 = request.POST.get('primer_nombre', '').strip()
        nombre2 = request.POST.get('segundo_nombre', '').strip()
        apellidoP = request.POST.get('primer_Apellido', '').strip()
        apellidoM = request.POST.get('segundo_Apellido', '').strip()
        instagram = request.POST.get('instagram', '').strip()
        correo = request.POST.get('email', '').strip()

        # 1. Validaciones de Longitud
        if len(nombre1) > 15:
            errores.append("El primer nombre no puede tener más de 15 caracteres.")
        if len(nombre2) > 15:
            errores.append("El segundo nombre no puede tener más de 15 caracteres.")
        if len(apellidoP) > 15:
            errores.append("El primer apellido no puede tener más de 15 caracteres.")
        if len(apellidoM) > 30: # Asumo que es 30, no 15 como en tu comentario original
            errores.append("El segundo apellido no puede tener más de 30 caracteres.")
        if len(instagram) > 15:
            errores.append("El usuario de Instagram no puede tener más de 15 caracteres.")
        if len(correo) > 50:
            errores.append("El correo electrónico no puede tener más de 50 caracteres.")

        # 2. Validaciones de Contenido y Formato
        if not nombre1.isalpha():
            errores.append("El primer nombre es obligatorio y solo debe contener letras.")
        if nombre2 and not nombre2.isalpha():
            errores.append("El segundo nombre solo debe contener letras.")
        if not apellidoP.isalpha():
            errores.append("El primer apellido es obligatorio y solo debe contener letras.")   
        if apellidoM and not apellidoM.isalpha():
            errores.append("El segundo apellido solo debe contener letras.")

        # Validación de Correo Electrónico (Obligatorio y Formato)
        if not correo:
            errores.append("El correo electrónico es obligatorio.")
        else:
            try:
                validate_email(correo)
            except ValidationError:
                errores.append("El formato del correo electrónico no es válido.")

        # Validación de Instagram (Opcional, solo valida si se proporcionó)
        if instagram and not re.fullmatch(r"^[a-zA-Z0-9_.]+$", instagram):
            errores.append("El usuario de Instagram solo puede contener letras, números, guiones bajos o puntos.")
        
        # 3. Validaciones de Unicidad
        # Para correo electrónico
        if Cliente.objects.filter(correo=correo).exists():
            errores.append("El correo electrónico ya está registrado para otro cliente.")
        
        # Para usuario de Instagram (solo si se proporcionó uno)
        if instagram and Cliente.objects.filter(instagram=instagram).exists():
            errores.append("El usuario de Instagram ya está en uso por otro cliente.")

        # Si hay errores, añadir a mensajes de Django y volver a renderizar el formulario
        if errores:
            for error_msg in errores:
                messages.error(request, error_msg) # Usa messages.error para mostrar los errores
            
            clientes = Cliente.objects.all().order_by('-id')[:10]
            return render(request, 'aplicacion/Admin_Cliente.html', {
                'clientes': clientes,
                'datos': request.POST # Para pre-rellenar el formulario con los datos enviados
            })

        # Si no hay errores, guardar el cliente
        Cliente.objects.create(
            nombre1=nombre1,
            nombre2=nombre2,
            apellidoP=apellidoP,
            apellidoM=apellidoM,
            instagram=instagram,
            correo=correo
        )
        messages.success(request, 'Cliente agregado exitosamente!') # Mensaje de éxito
        return redirect('aplicacion:AdCliente')

    # Para solicitudes GET, o si el POST no es válido inicialmente
    clientes = Cliente.objects.all().order_by('-id')[:10] # Solo los últimos 10 registros
    return render(request, 'aplicacion/Admin_Cliente.html', {'clientes': clientes})

@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador', 'Barbero'])
@permission_required('aplicacion.change_cliente', raise_exception=True)
def EditarCliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id) # Obtiene el cliente a editar
    errores = [] # Lista para almacenar los mensajes de error
    
    if request.method == 'POST':
        # Obtención y limpieza de datos
        nombre1 = request.POST.get('primer_nombre', '').strip()
        nombre2 = request.POST.get('segundo_nombre', '').strip()
        apellidoP = request.POST.get('primer_Apellido', '').strip()
        apellidoM = request.POST.get('segundo_Apellido', '').strip()
        instagram = request.POST.get('instagram', '').strip()
        correo = request.POST.get('email', '').strip()

        # 1. Validaciones de Longitud
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

        # 2. Validaciones de Contenido y Formato
        # Uso de re.fullmatch para permitir tildes, espacios, etc.
        # Validación de Primer Nombre (Obligatorio)
        if not nombre1:
            errores.append("El primer nombre es obligatorio.")
        elif not re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\.'-]+$", nombre1):
            errores.append("El primer nombre solo debe contener letras, espacios, guiones, puntos o apóstrofes.")

        # Validación de Segundo Nombre (Opcional, solo valida si se proporcionó)
        if nombre2 and not re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\.'-]+$", nombre2):
            errores.append("El segundo nombre solo debe contener letras, espacios, guiones, puntos o apóstrofes.")

        # Validación de Primer Apellido (Obligatorio)
        if not apellidoP:
            errores.append("El primer apellido es obligatorio.")
        elif not re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\.'-]+$", apellidoP):
            errores.append("El primer apellido solo debe contener letras, espacios, guiones, puntos o apóstrofes.")

        # Validación de Segundo Apellido (Opcional, solo valida si se proporcionó)
        if apellidoM and not re.fullmatch(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s\.'-]+$", apellidoM):
            errores.append("El segundo apellido solo debe contener letras, espacios, guiones, puntos o apóstrofes.")

        # Validación de Correo Electrónico (Obligatorio y Formato)
        if not correo:
            errores.append("El correo electrónico es obligatorio.")
        else:
            try:
                validate_email(correo)
            except ValidationError:
                errores.append("El formato del correo electrónico no es válido.")

        # 3. Validaciones de Unicidad (CRÍTICO PARA EDICIÓN)
        # Para correo electrónico: debe ser único, EXCLUYENDO al cliente actual
        if Cliente.objects.filter(correo=correo).exclude(id=cliente.id).exists():
            errores.append("El correo electrónico ya está registrado para otro cliente.")
        
        # Para usuario de Instagram: debe ser único, EXCLUYENDO al cliente actual (si se proporcionó)
        if instagram and Cliente.objects.filter(instagram=instagram).exclude(id=cliente.id).exists():
            errores.append("El usuario de Instagram ya está en uso por otro cliente.")

        # Si hay errores, añadir a mensajes de Django y volver a renderizar el formulario
        if errores:
            for error_msg in errores:
                messages.error(request, error_msg) # Usa messages.error para mostrar los errores
            
            return render(request, 'aplicacion/EditCliente.html', {
                'cliente': cliente, # Pasa el objeto cliente original para pre-rellenar datos si no se sobrescriben
                'datos': request.POST # Para pre-rellenar el formulario con los datos enviados (incluyendo los inválidos)
            })

        # Si no hay errores, actualizar y guardar el cliente
        cliente.nombre1 = nombre1
        cliente.nombre2 = nombre2
        cliente.apellidoP = apellidoP
        cliente.apellidoM = apellidoM
        cliente.instagram = instagram
        cliente.correo = correo
        
        cliente.save() # Guarda los cambios en la base de datos

        messages.success(request, 'Cliente actualizado exitosamente!') # Mensaje de éxito
        return redirect('aplicacion:AdCliente') # Redirige a la página que muestra la lista de clientes

    # Para solicitudes GET (cuando se carga la página de edición por primera vez)
    # Se renderiza el formulario con los datos existentes del cliente
    return render(request, 'aplicacion/EditCliente.html', {'cliente': cliente})


@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador']) # Solo Administradores pueden gestionar servicios
@permission_required('aplicacion.add_servicio', raise_exception=True)
def AdminServicio(request):
    errores = [] # Lista para almacenar los mensajes de error
    
    if request.method == 'POST':
        # Obtención y limpieza de datos
        nombre = request.POST.get('nombre', '').strip()
        tipo_servicio = request.POST.get('tipo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        precio_str = request.POST.get('precio', '').strip() # Lo guardamos como string inicialmente

        # 1. Validaciones de Longitud
        if len(nombre) > 20:
            errores.append("El nombre del servicio no puede tener más de 50 caracteres.")
        if len(tipo_servicio) > 20:
            errores.append("El tipo de servicio no puede tener más de 30 caracteres.")
        if len(descripcion) > 254:
            errores.append("La descripción no puede tener más de 100 caracteres.")
        if len(precio_str) > 6: 
            errores.append("El precio no puede tener más de 6 caracteres (incluyendo el punto decimal).")

        # 2. Validaciones de Contenido y Formato
        if not nombre:
            errores.append("El nombre del servicio es obligatorio.")
        elif not re.fullmatch(r"^[a-zA-Z0-9\sáéíóúÁÉÍÓÚñÑüÜ\.'-]+$", nombre):
            errores.append("El nombre del servicio contiene caracteres inválidos.")

        if not tipo_servicio:
            errores.append("El tipo de servicio es obligatorio.")
        elif not re.fullmatch(r"^[a-zA-Z\sáéíóúÁÉÍÓÚñÑüÜ\.'-]+$", tipo_servicio):
            errores.append("El tipo de servicio contiene caracteres inválidos.")

        if not descripcion:
            errores.append("La descripción es obligatoria.")
        
        # Validación de Precio
        precio_decimal = None # Inicializamos el precio Decimal a None
        if not precio_str:
            errores.append("El precio es obligatorio.")
        else:
            try:
                precio_decimal = Decimal(precio_str) # Intenta convertir a Decimal
                if precio_decimal <= 0:
                    errores.append("El precio debe ser mayor a cero.")
            except InvalidOperation: # Captura errores durante la conversión a Decimal
                errores.append("El precio debe ser un número válido.")

        
        # 3. Validaciones de Unicidad
        # Uso de __iexact para búsqueda insensible a mayúsculas/minúsculas
        if Servicio.objects.filter(nombre__iexact=nombre).exists():
            errores.append("Ya existe un servicio con este nombre.")

        if errores:
            for error_msg in errores:
                messages.error(request, error_msg) # Usa messages.error para mostrar los errores
            
            servicios = Servicio.objects.filter(estado=True) # Se mantienen los servicios activos
            return render(request, 'aplicacion/admin_servicios.html', {
                'servicios': servicios,
                'datos': request.POST # Para pre-rellenar el formulario con los datos enviados
            })

        # Si no hay errores, guardar el servicio
        # Asegúrate de que 'precio' ya es un float aquí
        Servicio.objects.create(
            nombre=nombre,
            tipo=tipo_servicio,
            descripcion=descripcion,
            precio=precio_decimal, # Asegúrate de usar la variable 'precio' convertida a float
            estado=True # Asumo que se crean como activos
        )
        messages.success(request, 'Servicio agregado exitosamente!') # Mensaje de éxito
        return redirect('aplicacion:AdServicio') # Redirige a la página de administración de servicios

    # Se muestran solo los servicios con estado=True por defecto
    servicios = Servicio.objects.filter(estado=True)
    return render(request, 'aplicacion/admin_servicios.html', {'servicios': servicios})

@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador']) # Solo los Administradores pueden editar servicios
@permission_required('aplicacion.change_servicio', raise_exception=True)
def EditarServicio(request, servicio_id):
    servicio = get_object_or_404(Servicio, id=servicio_id) # Obtiene el servicio a editar
    errores = [] # Lista para almacenar los mensajes de error
    
    if request.method == 'POST':
        # Obtención y limpieza de datos
        nombre = request.POST.get('nombre', '').strip()
        tipo_servicio = request.POST.get('tipo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        precio_str = request.POST.get('precio', '').strip() # Lo guardamos como string inicialmente

        # 1. Validaciones de Longitud
        if len(nombre) > 20:
            errores.append("El nombre del servicio no puede tener más de 50 caracteres.")
        if len(tipo_servicio) > 20:
            errores.append("El tipo de servicio no puede tener más de 30 caracteres.")
        if len(descripcion) > 254:
            errores.append("La descripción no puede tener más de 100 caracteres.")
        if len(precio_str) > 6:
            errores.append("El precio no puede tener más de 6 caracteres (incluyendo el punto decimal).")

        # 2. Validaciones de Contenido y Formato
        if not nombre:
            errores.append("El nombre del servicio es obligatorio.")
        elif not re.fullmatch(r"^[a-zA-Z0-9\sáéíóúÁÉÍÓÚñÑüÜ\.'-]+$", nombre):
            errores.append("El nombre del servicio contiene caracteres inválidos.")

        if not tipo_servicio:
            errores.append("El tipo de servicio es obligatorio.")
        elif not re.fullmatch(r"^[a-zA-Z\sáéíóúÁÉÍÓÚñÑüÜ\.'-]+$", tipo_servicio):
            errores.append("El tipo de servicio contiene caracteres inválidos.")

        if not descripcion:
            errores.append("La descripción es obligatoria.")
        
        # Validación de Precio (usando Decimal para precisión)
        precio_decimal = None # Inicializamos el precio Decimal a None
        if not precio_str:
            errores.append("El precio es obligatorio.")
        else:
            try:
                precio_decimal = Decimal(precio_str) # Intenta convertir a Decimal
                if precio_decimal <= 0:
                    errores.append("El precio debe ser mayor a cero.")
            except InvalidOperation: # Captura errores durante la conversión a Decimal
                errores.append("El precio debe ser un número válido.")

        # 3. Validaciones de Unicidad
        # Comprueba si ya existe un servicio con este nombre, EXCLUYENDO el servicio actual que se está editando.
        if Servicio.objects.filter(nombre__iexact=nombre).exclude(id=servicio.id).exists():
            errores.append("Ya existe otro servicio con este nombre.")

        # Si hay errores, añadirlos a los mensajes de Django y volver a renderizar el formulario
        if errores:
            for error_msg in errores:
                messages.error(request, error_msg) # Usa messages.error para mostrar los errores
            
            # Pasa el objeto 'servicio' original y 'datos' (request.POST) para pre-rellenar
            return render(request, 'aplicacion/EditServicio.html', {
                'servicio': servicio, # Objeto de servicio original
                'datos': request.POST # Datos que el usuario intentó enviar
            })

        # Si no hay errores, actualiza y guarda el servicio
        servicio.nombre = nombre
        servicio.tipo = tipo_servicio
        servicio.descripcion = descripcion
        servicio.precio = precio_decimal # Asigna el valor Decimal validado
        
        servicio.save() # Guarda los cambios en la base de datos

        messages.success(request, 'Servicio actualizado exitosamente!') # Mensaje de éxito
        return redirect('aplicacion:AdServicio') # Redirige a la página de administración de servicios

    # Para solicitudes GET (cuando la página de edición se carga por primera vez)
    # Renderiza el formulario con los datos existentes del servicio.
    return render(request, 'aplicacion/EditServicio.html', {'servicio': servicio})

@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador']) # Solo los Administradores pueden "remover" servicios
@permission_required('aplicacion.delete_servicio', raise_exception=True)
def Removerservicio(request, servicio_id):
    # Obtener el servicio por su ID o devolver un 404 si no existe
    servicio = get_object_or_404(Servicio, id=servicio_id)

    if request.method == 'POST':
        try:
            # Cambiar el estado del servicio a inactivo
            servicio.estado = False
            servicio.save()

            messages.success(request, f'El servicio "{servicio.nombre}" ha sido desactivado exitosamente.')
            
        except Exception as e:
            # Captura cualquier error inesperado durante el guardado
            messages.error(request, f'Ocurrió un error al desactivar el servicio "{servicio.nombre}": {e}')
        
        # Siempre redirigir a la página de administración de servicios después de intentar la acción
        return redirect('aplicacion:AdServicio')
    
    # Si la solicitud no es POST (es decir, alguien intentó acceder vía GET directamente a esta URL),
    messages.warning(request, "Acceso no permitido. Por favor, utiliza el formulario de desactivación.")
    return redirect('aplicacion:AdServicio')


@login_required(login_url='login')
@rol_requerido(['Administrador', 'Barbero'])
@permission_required(
    ('aplicacion.add_servicio_realizado',
    'aplicacion.add_detalle_serviciorealizado',
    )                 , raise_exception=True)
def AdminServicioRealizado(request):
    clientes = Cliente.objects.all()
    # Filtramos barberos por Estado=True y que estén activos (si tienes un campo de "activo" en Usuario/Barbero)
    barberos = Barbero.objects.filter(Estado=True) 
    servicios = Servicio.objects.filter(estado=True) # Solo servicios activos
    
    # Inicializamos servicios_seleccionados_ids para mantener los checkboxes marcados
    servicios_seleccionados_ids = request.POST.getlist('Servicio') if request.method == 'POST' else []
    
    # Consulta todos los servicios realizados (para mostrar en la tabla)
    servicios_realizados = Servicio_Realizado.objects.all().order_by('-fecha')

    if request.method == 'POST':
        fecha_str = request.POST.get('Fecha', '').strip()
        cliente_id = request.POST.get('Cliente', '').strip()
        barbero_id = request.POST.get('Barbero', '').strip()
        servicios_ids = request.POST.getlist('Servicio') # Lista de IDs de servicios seleccionados

        errores = [] # Reiniciar la lista de errores para cada POST

        # --- Validaciones ---

        # Validación de Fecha
        fecha_obj = None
        if not fecha_str:
            errores.append("La fecha es obligatoria.")
        else:
            try:
                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                
                # Regla 1: La fecha no puede ser en el futuro
                if fecha_obj > date.today():
                    errores.append("La fecha no puede ser en el futuro.")
                
                # Regla 2: La fecha no puede ser anterior a hace 2 días (excluyendo el día actual)
                # Calcula la fecha mínima permitida: hoy menos 2 días.
                # Por ejemplo, si hoy es 22 de junio, la fecha mínima sería 20 de junio.
                min_fecha_valida = date.today() - timedelta(days=2)
                
                if fecha_obj < min_fecha_valida:
                    errores.append(f"La fecha no puede ser anterior al {min_fecha_valida.strftime('%d-%m-%Y')}.")
                
            except ValueError:
                errores.append("El formato de la fecha es inválido. Utiliza AAAA-MM-DD.")
        
        # Validación de Cliente
        cliente_obj = None
        if not cliente_id:
            errores.append("Debe seleccionar un cliente.")
        else:
            try:
                cliente_obj = Cliente.objects.get(id=cliente_id)
            except Cliente.DoesNotExist:
                errores.append("El cliente seleccionado no es válido.")

        # Validación de Barbero
        barbero_obj = None
        if not barbero_id:
            errores.append("Debe seleccionar un barbero.")
        else:
            try:
                barbero_obj = Barbero.objects.get(id=barbero_id, Estado=True)
            except Barbero.DoesNotExist:
                errores.append("El barbero seleccionado no es válido o está inactivo.")

        # Validación de Servicios
        servicios_seleccionados_objetos = []
        if not servicios_ids:
            errores.append("Debe seleccionar al menos un servicio.")
        else:
            for sid in servicios_ids:
                try:
                    servicio_obj = Servicio.objects.get(id=sid, estado=True)
                    servicios_seleccionados_objetos.append(servicio_obj)
                except Servicio.DoesNotExist:
                    # En lugar de agregar un error por cada ID inválido, puedes ser más general
                    errores.append(f"Uno o más servicios seleccionados no son válidos o están inactivos.")
                    # Rompe el bucle si encuentras un servicio inválido para no acumular mensajes
                    break 

        # Si hay errores, añadir a mensajes de Django y volver a renderizar el formulario
        if errores:
            for error_msg in errores:
                messages.error(request, error_msg)
            
            return render(request, 'aplicacion/admin_ServicioRealizado.html', {
                'clientes': clientes,
                'barberos': barberos,
                'servicios': servicios, # Todos los servicios activos para re-mostrar
                'datos': request.POST, # Para pre-rellenar los campos de texto
                'servicios_seleccionados_ids': servicios_seleccionados_ids, # Para pre-marcar los checkboxes
                'servicios_realizados': servicios_realizados, # La tabla inferior
            })

        # --- Creación y Guardado (Transacción Atómica) ---
        # Usamos una transacción para asegurar que todas las operaciones se completen
        # o se reviertan si algo falla (ej. si falla la actualización de comisiones).
        try:
            with transaction.atomic():
                # Crea el Servicio Realizado (maestro)
                servicio_realizado = Servicio_Realizado.objects.create(
                    fecha=fecha_obj, # Usar el objeto de fecha validado
                    cliente=cliente_obj, # Asignar el objeto Cliente validado
                    barbero=barbero_obj # Asignar el objeto Barbero validado
                )
                
                total_comision_sesion = Decimal('0.00')

                # Crea el Detalle para cada servicio seleccionado y suma la comisión
                for servicio_obj in servicios_seleccionados_objetos: # Usar los objetos ya obtenidos
                    Detalle_ServicioRealizado.objects.create(
                        Servicio=servicio_obj, # Asignar el objeto Servicio validado
                        Servicio_Realizado=servicio_realizado
                    )
                    
                    # Suma comisión al barbero
                    # Asegúrate de que 'comision_porcentaje' está en tu modelo Servicio o Barbero
                    # O definir un porcentaje fijo (ej. 20%)
                    porcentaje_comision = Decimal('0.20') # 20% de comisión
                    comision_servicio = servicio_obj.precio * porcentaje_comision
                    total_comision_sesion += comision_servicio
                
                # Actualizar la comisión del barbero UNA SOLA VEZ
                barbero_obj.Comisiones = (barbero_obj.Comisiones or Decimal('0.00')) + total_comision_sesion
                barbero_obj.save()

            messages.success(request, 'Servicio realizado registrado exitosamente y comisiones actualizadas!')
            return redirect('aplicacion:AdServicioRealizado')

        except Exception as e:
            # Si ocurre algún error durante la transacción (ej. problemas de DB, lógica inesperada)
            messages.error(request, f'Ocurrió un error inesperado al registrar el servicio: {e}')
            # Si la transacción falla, se revertirá automáticamente.
            
            # Renderizar el formulario con los datos y errores
            return render(request, 'aplicacion/admin_ServicioRealizado.html', {
                'clientes': clientes,
                'barberos': barberos,
                'servicios': servicios,
                'datos': request.POST,
                'servicios_seleccionados_ids': servicios_seleccionados_ids,
                'servicios_realizados': servicios_realizados,
            })

    # Para solicitudes GET (cuando se carga la página por primera vez)
    return render(request, 'aplicacion/admin_ServicioRealizado.html', {
        'clientes': clientes,
        'barberos': barberos,
        'servicios': servicios,
        'servicios_seleccionados_ids': servicios_seleccionados_ids, # Será una lista vacía en GET inicial
        'servicios_realizados': servicios_realizados,
    })

@login_required(login_url='login')
@rol_requerido(['Administrador', 'Barbero'])
@permission_required(
    (
        'aplicacion.change_servicio_realizado'
        'aplicacion.change_detalle_serviciorealizado',
    )                 , raise_exception=True)
def EditarServicioRealizado(request, servicio_realizado_id):
    servicio_realizado = get_object_or_404(Servicio_Realizado, id=servicio_realizado_id)
    clientes = Cliente.objects.all()
    barberos = Barbero.objects.filter(Estado=True)
    servicios = Servicio.objects.filter(estado=True) # Solo servicios activos para selección

    # --- CAPTURAR EL ESTADO ORIGINAL ANTES DE CUALQUIER CAMBIO EN EL POST ---
    # Obtenemos el ID del barbero y los detalles antiguos del Servicio_Realizado actual.
    barbero_original_id_sr = servicio_realizado.barbero.id if servicio_realizado.barbero else None
    servicios_antiguos_detalle = servicio_realizado.detalle.all() # QuerySet de Detalle_ServicioRealizado

    # Pre-calcular la comisión que generaban los servicios ANTES de la edición
    comision_generada_por_sr_original = Decimal('0.00')
    porcentaje_comision = Decimal('0.20') # Define esto una vez para consistencia
    for detalle in servicios_antiguos_detalle:
        comision_generada_por_sr_original += detalle.Servicio.precio * porcentaje_comision

    # Cuando es una solicitud GET (para mostrar el formulario de edición por primera vez)
    if request.method == 'GET':
        # Obtener los IDs de los servicios ya asociados a este Servicio_Realizado
        # Usamos str() para asegurar que la comparación en el template sea entre strings
        servicios_seleccionados_ids_actuales = [str(s.Servicio.id) for s in servicios_antiguos_detalle]
        
        return render(request, 'aplicacion/EditServRealizado.html', {
            'servicio_realizado': servicio_realizado,
            'clientes': clientes,
            'barberos': barberos,
            'servicios': servicios,
            'servicios_seleccionados_ids': servicios_seleccionados_ids_actuales,
        })

    # Cuando es una solicitud POST (para procesar el formulario de edición)
    elif request.method == 'POST':
        fecha_str = request.POST.get('Fecha', '').strip()
        cliente_id = request.POST.get('Cliente', '').strip()
        barbero_id = request.POST.get('Barbero', '').strip()
        nuevos_servicios_ids_str = request.POST.getlist('Servicio') 

        errores = [] 

        # --- 1. Validaciones ---
        fecha_obj = None
        if not fecha_str:
            errores.append("La fecha es obligatoria.")
        else:
            try:
                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                if fecha_obj > date.today():
                    errores.append("La fecha no puede ser en el futuro.")
                
                min_fecha_valida = date.today() - timedelta(days=2) 
                if fecha_obj < min_fecha_valida:
                    errores.append(f"La fecha no puede ser anterior al {min_fecha_valida.strftime('%d-%m-%Y')}.")
                
            except ValueError:
                errores.append("El formato de la fecha es inválido. Utiliza AAAA-MM-DD.")
        
        cliente_obj = None
        if not cliente_id:
            errores.append("Debe seleccionar un cliente.")
        else:
            try:
                cliente_obj = Cliente.objects.get(id=cliente_id)
            except Cliente.DoesNotExist:
                errores.append("El cliente seleccionado no es válido.")

        barbero_obj = None # Este será el barbero final del servicio_realizado
        if not barbero_id:
            errores.append("Debe seleccionar un barbero.")
        else:
            try:
                barbero_obj = Barbero.objects.get(id=barbero_id, Estado=True)
            except Barbero.DoesNotExist:
                errores.append("El barbero seleccionado no es válido o está inactivo.")

        nuevos_servicios_objetos = []
        if not nuevos_servicios_ids_str:
            errores.append("Debe seleccionar al menos un servicio.")
        else:
            for sid_str in nuevos_servicios_ids_str:
                try:
                    sid = int(sid_str) 
                    servicio_obj = Servicio.objects.get(id=sid, estado=True)
                    nuevos_servicios_objetos.append(servicio_obj)
                except (ValueError, Servicio.DoesNotExist):
                    errores.append(f"Uno o más servicios seleccionados no son válidos o están inactivos.")
                    break 

        # Si hay errores de validación, renderizar el formulario con mensajes de error
        if errores:
            for error_msg in errores:
                messages.error(request, error_msg)
            
            return render(request, 'aplicacion/EditServRealizado.html', {
                'servicio_realizado': servicio_realizado, 
                'clientes': clientes,
                'barberos': barberos,
                'servicios': servicios,
                'datos': request.POST, 
                'servicios_seleccionados_ids': nuevos_servicios_ids_str,
            })

        # --- 2. Lógica de Actualización y Recálculo de Comisiones (Transacción Atómica) ---
        try:
            with transaction.atomic():
                # --- Paso 1: Revertir la comisión generada por ESTE Servicio_Realizado del BARBERO ORIGINAL ---
                if barbero_original_id_sr:
                    # Obtenemos una instancia fresca del barbero original CON BLOQUEO (select_for_update)
                    # Esto asegura que leemos el valor más actual y lo bloqueamos para esta transacción.
                    barbero_para_deduccion = Barbero.objects.select_for_update().get(id=barbero_original_id_sr)
                    
                    barbero_para_deduccion.Comisiones = (barbero_para_deduccion.Comisiones or Decimal('0.00')) - comision_generada_por_sr_original
                    barbero_para_deduccion.save()

                # --- Paso 2: Actualizar el Servicio_Realizado (Maestro) con los nuevos datos ---
                servicio_realizado.fecha = fecha_obj
                servicio_realizado.cliente = cliente_obj
                servicio_realizado.barbero = barbero_obj # Aquí se asigna el nuevo barbero
                servicio_realizado.save() 

                # --- Paso 3: Actualizar los Detalles (Eliminar los viejos y crear los nuevos) ---
                servicio_realizado.detalle.all().delete() # Elimina todos los detalles antiguos

                comision_generada_por_sr_nueva = Decimal('0.00')

                # Crea nuevos Detalle_ServicioRealizado para los servicios seleccionados
                for servicio_obj in nuevos_servicios_objetos:
                    Detalle_ServicioRealizado.objects.create(
                        Servicio=servicio_obj,
                        Servicio_Realizado=servicio_realizado
                    )
                    comision_generada_por_sr_nueva += servicio_obj.precio * porcentaje_comision
                
                # --- Paso 4: Aplicar la nueva comisión al BARBERO ACTUALIZADO (barbero_obj) ---
                # Obtenemos una instancia fresca del barbero que recibirá la comisión CON BLOQUEO.
                # Esto es crucial si el barbero_obj es el mismo que barbero_original_id_sr,
                # para que Comisiones tenga el valor ya modificado por la deducción.
                barbero_para_adicion = Barbero.objects.select_for_update().get(id=barbero_obj.id)
                barbero_para_adicion.Comisiones = (barbero_para_adicion.Comisiones or Decimal('0.00')) + comision_generada_por_sr_nueva
                barbero_para_adicion.save()

            messages.success(request, 'Servicio realizado actualizado exitosamente y comisiones recalculadas.')
            return redirect('aplicacion:AdServicioRealizado')

        except Exception as e:
            messages.error(request, f'Ocurrió un error inesperado al actualizar el servicio: {e}')
            
            return render(request, 'aplicacion/EditServRealizado.html', {
                'servicio_realizado': servicio_realizado,
                'clientes': clientes,
                'barberos': barberos,
                'servicios': servicios,
                'datos': request.POST,
                'servicios_seleccionados_ids': nuevos_servicios_ids_str,
            })

@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador'])
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

login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador'])
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
                        'inicio': '',  
                        'fin': ''
                    }
                    return render(request, 'aplicacion/reporte_servicios.html', context)

                servicios = servicios.filter(fecha__range=(inicio_date, fin_date))

            except ValueError:
                messages.error(request, "Formato de fecha inválido.")
                servicios = Servicio_Realizado.objects.none()
                context = {
                    'servicios': servicios,
                    'filtro': filtro,
                    'inicio': '', 
                    'fin': ''
                }
                return render(request, 'aplicacion/reporte_servicios.html', context)

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
    return render(request, 'aplicacion/reporte_servicios.html', context)

login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador'])
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

    template = get_template('aplicacion/reporte_servicios_pdf.html')
    context = {'servicios': servicios, 'gran_total': gran_total}
    html = template.render(context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_servicios.pdf"'
    pisa.CreatePDF(html, dest=response)
    return response

login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador'])
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

login_required(login_url='login')  # Redirige a 'login' si no está autenticado
@rol_requerido(['Administrador', 'Barbero', 'Aprendiz'])
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
                    return render(request, 'aplicacion/reporte_grafica.html', context)

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
                return render(request, 'aplicacion/reporte_grafica.html', context)

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
    return render(request, 'aplicacion/reporte_grafica.html', context)

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
    Sube un archivo a Google Drive usando una Cuenta de Servicio
    y obtiene su URL de descarga pública.
    """
    # 1. Obtener la clave de la cuenta de servicio de las variables de entorno
    service_account_info_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY')

    if not service_account_info_json:
        try:
            # Asume que el archivo de la cuenta de servicio está en la raíz del proyecto
            with open(settings.BASE_DIR / 'google_service.json', 'r') as f:
                service_account_info = json.load(f)
        except FileNotFoundError:
            raise Exception("ERROR: La clave de la Cuenta de Servicio de Google (GOOGLE_SERVICE_ACCOUNT_KEY) no está configurada en Railway ni el archivo local existe. No se puede subir a Drive.")
    else:
        try:
            service_account_info = json.loads(service_account_info_json)
        except json.JSONDecodeError:
            raise Exception("ERROR: La variable GOOGLE_SERVICE_ACCOUNT_KEY no contiene un JSON válido para la cuenta de servicio.")

    # 2. Definir los Scopes (permisos que necesita la cuenta de servicio)
    # 'https://www.googleapis.com/auth/drive' para acceso completo a Drive (lee, escribe, borra)
    # 'https://www.googleapis.com/auth/drive.file' para acceso solo a los archivos creados por la app
    SCOPES = ['https://www.googleapis.com/auth/drive']

    # 3. Autenticar la cuenta de servicio
    try:
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        print("DEBUG: Autenticación de Cuenta de Servicio exitosa.")
    except Exception as e:
        raise Exception(f"ERROR: Fallo al autenticar la Cuenta de Servicio: {e}")

    # 4. Construir el servicio de Google Drive
    drive_service = build('drive', 'v3', credentials=credentials)
    print("DEBUG: Google Drive service inicializado.")

    # 5. --- Sigue tu lógica de subir archivo ---
    mime_type_excel = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    file_metadata = {'name': nombre, 'mimeType': mime_type_excel}

    # Opcional: Define un folder ID para subir a una carpeta específica
    # folder_id = 'ID_DE_TU_CARPETA_EN_GOOGLE_DRIVE'
    # file_metadata['parents'] = [folder_id] # Asegúrate de que la cuenta de servicio tenga acceso a esta carpeta

    try:
        media = MediaFileUpload(path, mimetype=mime_type_excel)
        gfile = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink, webContentLink').execute()
        print(f"DEBUG: Archivo '{nombre}' subido a Google Drive. ID: {gfile.get('id')}")

        # Configurar permisos para que 'cualquiera con el enlace' pueda leer
        permission = {
            'type': 'anyone',
            'role': 'reader',
        }
        drive_service.permissions().create(fileId=gfile.get('id'), body=permission, fields='id').execute()
        print("DEBUG: Permisos de compartir configurados a 'cualquiera con el enlace puede leer'.")

        url_descarga = gfile.get('webViewLink') # Esto da la URL para ver el archivo en Drive
        if not url_descarga:
            url_descarga = gfile.get('webContentLink') # URL de descarga directa
            if not url_descarga:
                url_descarga = f"https://drive.google.com/uc?id={gfile.get('id')}&export=download" # Fallback

        print(f"DEBUG: URL final del archivo para Twilio: {url_descarga}")
        return url_descarga

    except Exception as e:
        print(f"ERROR: Fallo al subir el archivo o configurar permisos/URL: {e}")
        # Considera cómo quieres manejar este error (ej. levantar una excepción, retornar None)
        raise # Re-levanta la excepción para que sea manejada más arriba


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
        # print(f"Mensaje de WhatsApp enviado. SID: {message.sid}")
        return message.sid
    except Exception as e:
        print(f"Error al enviar el mensaje de WhatsApp: {e}")
        raise 
    

# @login_required(login_url='login')  # Redirige a 'login' si no está autenticado
# @rol_requerido(['Administrador'])
def enviar_reporte_excel_whatsapp(request):
    if request.method == 'POST':
        numero = request.POST.get('numero') 

        if not numero:
            messages.error(request, "Número de WhatsApp no proporcionado.")
            return redirect('aplicacion:reporte_servicios')

        try:
            # Asegúrate que filtrar_servicios_por_fecha esté definida y funcione correctamente
            servicios = filtrar_servicios_por_fecha(request)
            if not servicios:
                messages.warning(request, "No se encontraron servicios para generar el reporte.")
                return redirect('aplicacion:reporte_servicios')
        except Exception as e:
            messages.error(request, f"Error al filtrar servicios: {e}")
            return redirect('aplicacion:reporte_servicios')

        filename = f'reporte_servicios_{timezone.now().strftime("%Y%m%d%H%M%S")}.xlsx'
        file_path = None
        url_drive = None 

        # --- ETAPA 1: Generar el Excel localmente ---
        try:
            file_path = generar_reporte_excel_y_guardar(servicios, filename)
            messages.info(request, f'Reporte Excel "{filename}" generado localmente.')
        except Exception as e:
            messages.error(request, f'Error al generar el reporte Excel: {e}')
            return redirect('aplicacion:reporte_servicios') 

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
            return redirect('aplicacion:reporte_servicios') 

        # --- ETAPA 3: Enviar ENLACE por WhatsApp ---
        try:
            sid = enviar_link_whatsapp(numero, url_drive, filename) 
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

    return redirect('aplicacion:reporte_servicios')

#============================================================================================================================
# Contador de turnos con WebSocket
#============================================================================================================================
@login_required
@rol_requerido(['Administrador', 'Barbero', 'Aprendiz'])
def queue_dashboard(request):
    # Obtener todos los barberos y su número de cola actual
    barberos = Barbero.objects.filter(Estado=True).select_related('Empleado__persona')

    queue_data = []
    for barbero in barberos:
        current_number = 0
        try:
            # Obtener el objeto BarberQueue relacionado con este barbero
            queue_obj = BarberQueue.objects.get(barbero=barbero)
            current_number = queue_obj.current_number
        except BarberQueue.DoesNotExist:
            # Si no hay una cola creada para este barbero, se inicializa en 0
            # (El método get_or_create_queue_for_barber en el consumer lo crearía al conectar)
            current_number = 0
            print(f"DEBUG: No se encontró BarberQueue para barbero ID {barbero.id}. Usando 0 como valor inicial.")
        except Exception as e:
            print(f"ERROR: Fallo al obtener la cola para barbero ID {barbero.id}: {e}")
            current_number = 0 # En caso de cualquier otro error al obtener la cola

        # Construir el nombre del barbero navegando a través de Empleado y Persona
        # Asegúrate de que barbero.Empleado.persona exista para cada barbero
        barber_name = "Nombre Desconocido"
        try:
            barber_name = f"{barbero.Empleado.persona.nombre1} {barbero.Empleado.persona.apellidoP}"
        except ObjectDoesNotExist:
            print(f"ADVERTENCIA: Barbero ID {barbero.id} no tiene un Empleado/Persona asociado.")
        except AttributeError:
            print(f"ADVERTENCIA: Problema al acceder a Empleado/Persona del Barbero ID {barbero.id}. Asegura tus relaciones.")


        queue_data.append({
            'barber_id': barbero.id,
            'barber_name': barber_name,
            'current_number': current_number,
        })

    user = request.user

    # --- Lógica para verificar el rol del usuario actual ---
    user_rol_name = None
    if user.is_authenticated:
        try:
            # Intentar acceder al nombre del rol del usuario
            if hasattr(user, 'rol') and user.rol:
                user_rol_name = user.rol.nombre
        except ObjectDoesNotExist:
            # Esto puede ocurrir si el campo rol es ForeignKey y el objeto Rol no existe
            print(f"ADVERTENCIA: El usuario '{user.username}' (ID: {user.id}) tiene un rol que no existe en la base de datos.")
            user_rol_name = None # Resetea a None si el objeto Rol no es válido
        except AttributeError:
            # Esto puede ocurrir si el modelo Persona no tiene un campo 'rol' o está mal configurado
            print(f"ERROR: El modelo Persona no tiene un atributo 'rol' o está mal configurado para el usuario '{user.username}'.")
            user_rol_name = None

    user_is_admin = (user.is_superuser or user_rol_name == 'Administrador')
    user_is_barbero = (user_rol_name == 'Barbero')
    user_is_aprendiz = (user_rol_name == 'Aprendiz')

    # La bandera final para controlar la visibilidad de los botones
    can_see_buttons = user_is_admin or user_is_barbero or user_is_aprendiz

    context = {
        'queue_data': queue_data,
        'can_see_buttons': can_see_buttons, # <-- Esta es la variable clave para tu template
        'user_is_admin': user_is_admin,       # Opcional: para control más granular en el template
        'user_is_barbero': user_is_barbero,   # Opcional
        'user_is_aprendiz': user_is_aprendiz, # Opcional
    }

    # Asegúrate de que 'aplicacion/queue_dashboard.html' es la ruta correcta a tu template
    return render(request, 'aplicacion/queue_dashboard.html', context)

# --- Nueva vista para incrementar el número de cola ---
@require_POST
@login_required # Esta vista es solo para usuarios logueados (barberos/admins)
@rol_requerido(['Administrador', 'Barbero', 'Aprendiz']) # Solo barberos y admins pueden usarla
def increment_served_queue(request): # Renombrada
    """
    Vista HTTP para que el barbero incremente el número de cola que está atendiendo.
    """
    try:
        data = json.loads(request.body)
        barber_id = data.get('barber_id')

        if not barber_id:
            return JsonResponse({'success': False, 'message': 'barber_id es requerido'}, status=400)

        barbero = Barbero.objects.get(id=barber_id)
        queue_obj = BarberQueue.get_or_create_queue_for_barber(barbero)
        
        # Usa el nuevo método para incrementar el número de atendidos
        new_served_number = queue_obj.increment_served_number() 

        # Notificar a los clientes a través de WebSocket
        channel_layer = get_channel_layer()
        room_group_name = f'queue_{safe_channel_name(barber_id)}'
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'queue_update',
                'barber_id': barber_id,
                'number': new_served_number, # El número actual siendo atendido
                'last_issued_number': queue_obj.last_issued_number # También envía el último emitido
            }
        )

        return JsonResponse({'success': True, 'new_number': new_served_number})

    except Barbero.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Barbero con ID {barber_id} no encontrado.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON inválido en el cuerpo de la solicitud.'}, status=400)
    except Exception as e:
        print(f"Error en increment_served_queue: {e}")
        return JsonResponse({'success': False, 'message': f'Error interno del servidor: {str(e)}'}, status=500)

def customer_queue_select(request):
    """
    Vista para que los clientes seleccionen un barbero y obtengan un turno.
    No requiere autenticación (@login_required), es una vista pública.
    """
    barberos_data = []
    # Solo mostrar barberos que estén marcados como 'Estado=True' (activos/disponibles)
    barberos = Barbero.objects.filter(Estado=True).order_by('id') 

    for barbero in barberos:
        barber_name = f"{barbero.Empleado.persona.nombre1} {barbero.Empleado.persona.apellidoP}"
        
        # Obtener el estado actual de la cola para mostrarlo al cliente
        current_number = 0
        last_issued_number = 0
        try:
            queue_obj = BarberQueue.objects.get(barbero=barbero)
            current_number = queue_obj.current_number
            last_issued_number = queue_obj.last_issued_number
        except BarberQueue.DoesNotExist:
            # Si no hay una cola para este barbero aún, se asume 0
            pass 

        barberos_data.append({
            'barber_id': barbero.id,
            'barber_name': barber_name,
            'current_number': current_number,       # Número actual siendo atendido
            'last_issued_number': last_issued_number # Último número de ticket emitido
        })

    context = {
        'barberos_data': barberos_data,
    }
    # Renderiza un template nuevo y específico para el cliente
    return render(request, 'aplicacion/customer_queue_select.html', context)


@require_POST # Solo permite peticiones POST
# No lleva @login_required porque es para clientes no autenticados
# CONSIDERACIÓN DE SEGURIDAD: CSRF (ver más abajo)
def issue_customer_ticket(request):
    """
    Vista HTTP para asignar un nuevo número de turno (ticket) a un cliente.
    """
    try:
        data = json.loads(request.body)
        barber_id = data.get('barber_id')

        if not barber_id:
            return JsonResponse({'success': False, 'message': 'barber_id es requerido'}, status=400)

        barbero = Barbero.objects.get(id=barber_id)
        queue_obj = BarberQueue.get_or_create_queue_for_barber(barbero)
        
        # Emite un nuevo número de ticket usando el método del modelo
        assigned_ticket_number = queue_obj.issue_new_ticket()

        # Notifica a través de WebSocket (para actualizar el dashboard de barberos y otros clientes)
        channel_layer = get_channel_layer()
        room_group_name = f'queue_{safe_channel_name(barber_id)}'  # <-- Sanitiza aquí
        async_to_sync(channel_layer.group_send)(
            room_group_name,
            {
                'type': 'queue_update',
                'barber_id': barber_id,
                'number': queue_obj.current_number,        # El número actual que el barbero atiende (no cambia con esto)
                'last_issued_number': assigned_ticket_number # El nuevo último número emitido
            }
        )

        # Devuelve la información al cliente que hizo la petición
        return JsonResponse({
            'success': True,
            'assigned_number': assigned_ticket_number,
            'current_number_for_barber': queue_obj.current_number, # El número que el barbero está atendiendo
            'barber_name': f"{barbero.Empleado.persona.nombre1} {barbero.Empleado.persona.apellidoP}"
        })

    except Barbero.DoesNotExist:
        return JsonResponse({'success': False, 'message': f'Barbero con ID {barber_id} no encontrado.'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'JSON inválido en el cuerpo de la solicitud.'}, status=400)
    except Exception as e:
        print(f"Error en issue_customer_ticket: {e}")
        return JsonResponse({'success': False, 'message': f'Error interno del servidor: {str(e)}'}, status=500)
    