// Apps/aplicacion/static/JavaScript/customer_scripts.js

document.addEventListener('DOMContentLoaded', function() {
    const selectionScreen = document.getElementById('selection-screen');
    const assignedTicketDisplay = document.getElementById('assigned-ticket-display');
    const restartSelectionButton = document.getElementById('restart-selection-button');

    const yourTicketNumberSpan = document.getElementById('your-ticket-number');
    const currentTicketNumberDisplaySpan = document.getElementById('current-ticket-number-display');
    const assignedBarberNameSpan = document.getElementById('assigned-barber-name');
    const currentBarberNameDisplaySpan = document.getElementById('current-barber-name-display'); // Para el display actual

    let currentBarberSocket = null; // Guardará la conexión WebSocket para el barbero seleccionado
    let selectedBarberId = null; // Guarda el ID del barbero seleccionado

    // Función auxiliar para obtener el token CSRF desde la cookie
    // (Esta es la forma estándar recomendada por la documentación de Django)
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                // Does this cookie string begin with the name we want?
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    document.querySelectorAll('.select-barber-button').forEach(button => {
        button.addEventListener('click', function() {
            const barberCard = this.closest('.barber-card');
            selectedBarberId = barberCard.dataset.barberId;
            const barberName = barberCard.querySelector('h2').textContent;

            // Validar el ID antes de continuar
            if (!/^[a-zA-Z0-9_.-]+$/.test(selectedBarberId)) {
                alert("ID de barbero inválido. Selecciona otro barbero.");
                // Volver a habilitar botones si hay un error
                document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = false);
                return;
            }

            // Deshabilitar todos los botones para evitar múltiples clics
            document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = true);

            // *** Obtener el token CSRF ANTES de la petición fetch ***
            const csrfToken = getCookie('csrftoken');

            // Fetch para emitir un nuevo número de ticket
            fetch('/issue-customer-ticket/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    // *** AÑADE ESTE ENCABEZADO para enviar el token CSRF ***
                    'X-CSRFToken': csrfToken, 
                },
                body: JSON.stringify({ barber_id: selectedBarberId })
            })
            .then(response => {
                // Ya no debería dar 403 por CSRF si el token se envía correctamente
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.success) {
                    console.log('Ticket emitido:', data);
                    // Ocultar la pantalla de selección y mostrar la de ticket
                    selectionScreen.style.display = 'none';
                    assignedTicketDisplay.style.display = 'block';

                    // Rellenar la información del ticket
                    yourTicketNumberSpan.textContent = data.assigned_number;
                    assignedBarberNameSpan.textContent = data.barber_name;
                    currentBarberNameDisplaySpan.textContent = data.barber_name;
                    currentTicketNumberDisplaySpan.textContent = data.current_number_for_barber;

                    // Abrir conexión WebSocket para este barbero específico para actualizaciones en vivo
                    if (currentBarberSocket) {
                        currentBarberSocket.close(); // Cerrar conexión anterior si existe
                    }
                    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                    console.log("✅ WebSocket abriéndose con barber_id =", selectedBarberId);
                    currentBarberSocket = new WebSocket(
                        protocol + '//' + window.location.host + `/ws/queue/${selectedBarberId}/`
                    );

                    currentBarberSocket.onmessage = function(e) {
                        const wsData = JSON.parse(e.data);
                        // Asegurarse de que la actualización es para el barbero correcto
                        if (wsData.type === 'queue_update' && wsData.barber_id == selectedBarberId) {
                            // Actualizar el número actual siendo atendido
                            currentTicketNumberDisplaySpan.textContent = wsData.number;
                            console.log(`Actualización en vivo: Barbero ${selectedBarberId} actual número: ${wsData.number}`);
                            // No actualizamos 'yourTicketNumberSpan' aquí, ese es fijo una vez asignado.
                        }
                    };

                    currentBarberSocket.onclose = function(e) {
                        console.error(`WebSocket para barbero ${selectedBarberId} cerrado inesperadamente.`, e);
                    };

                    currentBarberSocket.onerror = function(e) {
                        console.error(`Error en WebSocket para barbero ${selectedBarberId}:`, e);
                    };

                } else {
                    alert('Error al asignar turno: ' + data.message);
                    // Volver a habilitar botones si hay un error
                    document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = false);
                }
            })
            .catch(error => {
                console.error('Error de red o servidor al seleccionar barbero:', error);
                alert('Hubo un problema al intentar seleccionar un barbero. Inténtalo de nuevo.');
                // Volver a habilitar botones en caso de error de red
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
        // Volver a habilitar todos los botones de selección
        document.querySelectorAll('.select-barber-button').forEach(btn => btn.disabled = false);
    });
});