// Apps/aplicacion/static/JavaScript/customer_scripts.js

document.addEventListener('DOMContentLoaded', function() {
    const selectionScreen = document.getElementById('selection-screen');
    const assignedTicketDisplay = document.getElementById('assigned-ticket-display');
    const restartSelectionButton = document.getElementById('restart-selection-button');

    const yourTicketNumberSpan = document.getElementById('your-ticket-number');
    const currentTicketNumberDisplaySpan = document.getElementById('current-ticket-number-display');
    const assignedBarberNameSpan = document.getElementById('assigned-barber-name');
    const currentBarberNameDisplaySpan = document.getElementById('current-barber-name-display');

    let currentBarberSocket = null; // Guardará la conexión WebSocket para el barbero seleccionado
    let selectedBarberId = null; // Guarda el ID del barbero seleccionado

    // Función auxiliar para obtener el token CSRF desde la cookie
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Función para configurar y conectar el WebSocket del cliente
    function setupCustomerSocket(barberId) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socketUrl = protocol + window.location.host + '/ws/queue/' + barberId + '/';
        console.log(`✅ Cliente: Intentando conectar WebSocket para barbero ${barberId} a ${socketUrl}`);

        const socket = new WebSocket(socketUrl);

        socket.onopen = function(e) {
            console.log(`Cliente: WebSocket para barbero ${barberId} conectado.`);
        };

        socket.onmessage = function(e) {
            const wsData = JSON.parse(e.data);
            if (wsData.type === 'queue_update' && wsData.barber_id == selectedBarberId) {
                // Actualizar el número actual siendo atendido
                currentTicketNumberDisplaySpan.textContent = wsData.number;
                console.log(`Cliente: Actualización en vivo. Barbero ${selectedBarberId} número actual: ${wsData.number}. Último ticket emitido: ${wsData.last_issued_number}`);
            } else if (wsData.type === 'error') {
                console.error(`Cliente: Error del servidor para barbero ${selectedBarberId}: ${wsData.message}`);
                // Podrías mostrar un alert o mensaje en la UI para el cliente
            } else {
                console.log(`Cliente: Mensaje WebSocket recibido no manejado para barbero ${selectedBarberId}:`, wsData);
            }
        };

        socket.onclose = function(e) {
            let message = `Cliente: Socket para barbero ${barberId} cerrado.`;
            if (e.wasClean) {
                console.log(`${message} La conexión se cerró limpiamente. Código: ${e.code}, Razón: ${e.reason}`);
            } else {
                console.error(`${message} Cerrado inesperadamente. Código: ${e.code}, Razón: ${e.reason}`, e);
                // Intento de reconexión si no fue un cierre limpio
                // OJO: Podrías querer limitar los reintentos para evitar bucles infinitos
                if (assignedTicketDisplay.style.display === 'block') { // Solo reconectar si el cliente sigue en la pantalla de ticket
                    console.warn(`Cliente: Reconectando WebSocket para barbero ${barberId} en 3 segundos...`);
                    setTimeout(() => {
                        currentBarberSocket = setupCustomerSocket(barberId); // Reasignar el nuevo socket
                    }, 3000); 
                }
            }
        };

        socket.onerror = function(error) {
            console.error(`Cliente: Error fatal en el socket para barbero ${barberId}:`, error);
            // Podrías mostrar un mensaje al usuario para que intente de nuevo
            alert("Hubo un error con la conexión en vivo. Recarga la página o inténtalo de nuevo.");
        };

        return socket; // Devuelve el objeto socket
    }

    // Manejador de clics para los botones de selección de barbero
    document.querySelectorAll('.select-barber-button').forEach(button => {
        button.addEventListener('click', function() {
            const barberCard = this.closest('.barber-card');
            selectedBarberId = barberCard.dataset.barberId;
            const barberName = barberCard.querySelector('h2').textContent;

            // Validar el ID antes de continuar
            if (!/^[a-zA-Z0-9_.-]+$/.test(selectedBarberId)) {
                alert("ID de barbero inválido. Selecciona otro barbero.");
                document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = false);
                return;
            }

            // Deshabilitar todos los botones para evitar múltiples clics
            document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = true);

            const csrfToken = getCookie('csrftoken');

            // Fetch para emitir un nuevo número de ticket
            fetch('/issue-customer-ticket/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken, 
                },
                body: JSON.stringify({ barber_id: selectedBarberId })
            })
            .then(response => {
                if (!response.ok) {
                    // Si el servidor devuelve un error HTTP (ej. 400, 404, 500)
                    return response.json().then(err => { throw new Error(`Error ${response.status}: ${err.message || response.statusText}`); });
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    console.log('Cliente: Ticket emitido:', data);
                    
                    // Ocultar la pantalla de selección y mostrar la de ticket
                    selectionScreen.style.display = 'none';
                    assignedTicketDisplay.style.display = 'block';

                    // Rellenar la información del ticket
                    yourTicketNumberSpan.textContent = data.assigned_number;
                    assignedBarberNameSpan.textContent = data.barber_name;
                    currentBarberNameDisplaySpan.textContent = data.barber_name; // Nombre del barbero para el current queue display
                    currentTicketNumberDisplaySpan.textContent = data.current_number_for_barber; // Número actual que atiende el barbero

                    // Cerrar conexión anterior si existe y abrir una nueva
                    if (currentBarberSocket) {
                        currentBarberSocket.close(); 
                    }
                    // **CORRECCIÓN CLAVE AQUÍ: ASIGNAR EL NUEVO SOCKET A LA VARIABLE GLOBAL**
                    currentBarberSocket = setupCustomerSocket(selectedBarberId);

                } else {
                    alert('Cliente: Error al asignar turno: ' + data.message);
                    document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = false);
                }
            })
            .catch(error => {
                console.error('Cliente: Error de red o servidor al seleccionar barbero:', error);
                alert('Hubo un problema al intentar seleccionar un barbero. Inténtalo de nuevo. Detalle: ' + error.message);
                document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = false);
            });
        });
    });

    // Botón para volver a la selección
    restartSelectionButton.addEventListener('click', function() {
        if (currentBarberSocket) {
            currentBarberSocket.close(); // Cerrar WebSocket al volver
            currentBarberSocket = null;
        }
        assignedTicketDisplay.style.display = 'none';
        selectionScreen.style.display = 'block';
        document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = false);
    });
});