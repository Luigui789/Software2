from django.shortcuts import render,redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from datetime import timedelta
from .models import Persona, Empleado, Barbero
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from .models import Persona, Empleado, Barbero, Cliente, Servicio, Servicio_Realizado, Detalle_ServicioRealizado
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from decimal import Decimal
import json




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

def logout_view(request):
    auth_logout(request)
    return redirect('login')

@login_required(login_url='login')  # Redirige a 'login' si no está autenticado
def administracion(request):
    return render(request, 'Administracion.html')

def equipo(request):
    return render(request, 'Conoce_al_equipo.html')

def quienes(request):
    return render(request, 'Quienes_somos.html')

def contacto(request):
    return render(request, 'Contactanos.html')

def AdminBarbero(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        errores = []

        # Validaciones
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
        if not data['Cargo']:
            errores.append("El cargo es obligatorio.")
        if not data['Salario'] or not str(data['Salario']).replace('.', '', 1).isdigit():
            errores.append("El salario es obligatorio y debe ser un número.")
        if not data['Direccion']:
            errores.append("La dirección es obligatoria.")
        if data['email'] and '@' not in data['email']:
            errores.append("El correo electrónico no es válido.")

        if errores:
            return JsonResponse({'status': 'error', 'errores': errores})

        # Inserción en las tablas
        persona = Persona.objects.create(
            nombre1=data['primer_nombre'],
            nombre2=data['segundo_nombre'],
            apellidoP=data['primer_Apellido'],
            apellidoM=data['segundo_Apellido'],
            telefono=data['telefono'],
            email=data['email'],
            username=data['usuario'],
            password=data['password']
        )
        empleado = Empleado.objects.create(
            persona=persona,
            cargo=data['Cargo'],
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

    # Mostrar todos los barberos para la tabla
    barberos = Barbero.objects.select_related('Empleado__persona').filter(Estado=True)
    return render(request, 'admin_barbero.html', {'barberos': barberos})


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
            # Actualiza los datos del barbero
            barbero = get_object_or_404(Barbero, id=barbero_id)
            barbero.Empleado.persona.nombre1 = data['primer_nombre']
            barbero.Empleado.persona.nombre2 = data['segundo_nombre']
            barbero.Empleado.persona.apellidoP = data['primer_Apellido']
            barbero.Empleado.persona.apellidoM = data['segundo_Apellido']
            barbero.Empleado.persona.telefono = data['telefono']
            barbero.Empleado.persona.email = data['email']
            barbero.Empleado.persona.username = data['usuario']
            barbero.Empleado.persona.password = data['password']
            barbero.Empleado.Salario = data['Salario']
            barbero.Direccion = data['Direccion']
            barbero.cedula = data['Cedula']

            # Guarda los cambios
            barbero.Empleado.persona.save()
            barbero.Empleado.save()
            barbero.save()
            return JsonResponse({'status': 'ok'})  # <-- RESPUESTA JSON EXITOSA
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)})
    barbero = get_object_or_404(Barbero, id=barbero_id)
    return render(request, 'Editbarbero.html', {'barbero': barbero})
    


def AdminCliente(request):
    errores = []
    if request.method == 'POST':
        nombre1 = request.POST.get('primer_nombre', '').strip()
        nombre2 = request.POST.get('segundo_nombre', '').strip()
        apellidoP = request.POST.get('primer_Apellido', '').strip()
        apellidoM = request.POST.get('segundo_Apellido', '').strip()
        instagram = request.POST.get('instagram', '').strip()
        correo = request.POST.get('email', '').strip()

        # Validaciones
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

    clientes = Cliente.objects.all()
    return render(request, 'Admin_Cliente.html', {'clientes': clientes})

def EditarCliente(request, cliente_id):
    cliente = get_object_or_404(Cliente, id=cliente_id)
    if request.method == 'POST':
        cliente.nombre1 = request.POST.get('primer_nombre')
        cliente.nombre2 = request.POST.get('segundo_nombre')
        cliente.apellidoP = request.POST.get('primer_Apellido')
        cliente.apellidoM = request.POST.get('segundo_Apellido')
        cliente.instagram = request.POST.get('instagram')
        cliente.correo = request.POST.get('email')
        cliente.save()
        return redirect('AdCliente')
    return render(request, 'EditCliente.html', {'cliente': cliente})


def AdminServicio(request):
    errores = []
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        tipo_servicio = request.POST.get('tipo', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        precio = request.POST.get('precio', '').strip()

        # Validaciones
        if not nombre:
            errores.append("El nombre del servicio es obligatorio.")
        if not tipo_servicio:
            errores.append("El tipo de servicio es obligatorio.")
        if not descripcion:
            errores.append("La descripción es obligatoria.")
        if not precio or not precio.replace('.', '', 1).isdigit():
            errores.append("El precio es obligatorio y debe ser un número.")

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
    if request.method == 'POST':
        servicio.nombre = request.POST.get('nombre')
        servicio.tipo = request.POST.get('tipo')
        servicio.descripcion = request.POST.get('descripcion')
        servicio.precio = request.POST.get('precio')
        estado = request.POST.get('estado', 'True')
        # Convierte el estado a booleano
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