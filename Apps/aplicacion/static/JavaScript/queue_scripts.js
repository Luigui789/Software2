document.addEventListener('DOMContentLoaded', function() {
    const quadrants = document.querySelectorAll('.quadrant');

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

    // Obtener el token CSRF una vez al cargar el script
    const csrftoken = getCookie('csrftoken');

    // Función para configurar y conectar el WebSocket para un barbero específico
    function setupBarberSocket(barberId, currentNumberDisplay) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socketUrl = protocol + window.location.host + '/ws/queue/' + barberId + '/';
        console.log(`✅ Barbero: Intentando conectar WebSocket para barbero ${barberId} a ${socketUrl}`);

        const socket = new WebSocket(socketUrl);

        socket.onopen = function(e) {
            console.log(`Barbero: WebSocket para barbero ${barberId} conectado.`);
            // Si quieres, aquí podrías enviar un mensaje para solicitar el estado actual de la cola.
            // socket.send(JSON.stringify({ 'action': 'request_initial_state', 'barber_id': barberId }));
        };

        socket.onmessage = function(e) {
            const data = JSON.parse(e.data);
            if (data.type === 'queue_update' && data.barber_id == barberId) {
                currentNumberDisplay.textContent = data.number;
                console.log(`Barbero ${barberId}: Número actualizado a ${data.number}. Último ticket emitido: ${data.last_issued_number}`);
            } else if (data.type === 'error') {
                console.error(`Barbero: Error del servidor para barbero ${barberId}: ${data.message}`);
                alert(`Error para barbero ${barberId}: ${data.message}`);
            }
        };

        socket.onclose = function(e) {
            let message = `Barbero: Socket para barbero ${barberId} cerrado.`;
            if (e.wasClean) {
                console.log(`${message} La conexión se cerró limpiamente. Código: ${e.code}, Razón: ${e.reason}`);
            } else {
                console.error(`${message} Cerrado inesperadamente. Código: ${e.code}, Razón: ${e.reason}`, e);
                // Intento de reconexión si no fue un cierre limpio
                console.warn(`Barbero: Reconectando WebSocket para barbero ${barberId} en 3 segundos...`);
                setTimeout(() => {
                    // Reasignar el nuevo socket
                    // Esto asume que 'sockets' es un mapa o que manejas cada socket individualmente
                    // Si tienes un array de sockets, necesitarías una lógica más compleja para reasignar el correcto.
                    // Para este 'forEach' simple, podrías sobrescribir la variable local 'socket' si solo se usa aquí.
                    // O, si necesitas acceder a él desde los botones, tendrías que almacenar los sockets.
                    // Por simplicidad, lo reconfiguramos aquí mismo, asumiendo que es una función aislada para cada cuadrante.
                    setupBarberSocket(barberId, currentNumberDisplay); 
                }, 3000); 
            }
        };

        // Consolidamos la lógica de error aquí
        socket.onerror = function(error) {
            console.error(`Barbero: Error fatal en el socket para barbero ${barberId}:`, error);
            // Considera un mensaje menos disruptivo que alert() si es en producción
            alert(`Error de conexión para barbero ${barberId}. Recarga la página si persiste.`);
        };

        return socket; // Devuelve el objeto socket
    }

    quadrants.forEach(quadrant => {
        const barberId = quadrant.dataset.barberId;
        // Validar barberId antes de usarlo en la URL del WebSocket
        if (!/^[a-zA-Z0-9_.-]+$/.test(barberId)) {
            console.error(`ID de barbero inválido: ${barberId}. Solo se permiten letras, números, guiones, guiones bajos y puntos.`);
            return; // No continúes con este cuadrante
        }
        const currentNumberDisplay = quadrant.querySelector('.current-queue-number');
        const nextButton = quadrant.querySelector('.next-button');
        const resetButton = quadrant.querySelector('.reset-button');

        // Configuración de WebSocket para cada barbero
        const socket = setupBarberSocket(barberId, currentNumberDisplay); // Asignamos el socket

        // --- Lógica del botón "Siguiente Turno" ---
        if (nextButton) {
            nextButton.onclick = function() {
                fetch('/increment-queue/', { // La URL debe coincidir con la definida en Django
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrftoken, 
                    },
                    body: JSON.stringify({ barber_id: barberId }) // Envía el ID del barbero
                })
                .then(response => {
                    if (response.status === 403) {
                        console.error("Error 403 Forbidden: Probablemente CSRF token missing o inválido. Asegúrate de que el token se esté enviando correctamente.");
                        throw new Error("Error de seguridad: Petición bloqueada (CSRF).");
                    }
                    if (!response.ok) {
                        return response.json().then(err => { throw new Error(`Error HTTP! Estado: ${response.status}: ${err.message || response.statusText}`); });
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        console.log(`Botón de barbero ${barberId} presionado. Nuevo número: ${data.new_number}`); // Cambiado a new_number
                        // El número en la UI se actualizará automáticamente gracias al mensaje del WebSocket.
                    } else {
                        console.error('Error al incrementar la cola:', data.message);
                        alert(`Error al avanzar el turno para barbero ${barberId}: ${data.message}`);
                    }
                })
                .catch(error => {
                    console.error('Error de red o servidor al intentar avanzar turno:', error);
                    alert('Hubo un problema de conexión al intentar avanzar el turno. Detalle: ' + error.message);
                });
            };
        } else {
            console.warn(`Botón 'Siguiente Turno' no encontrado para barbero ${barberId}.`);
        }

        // --- Lógica del botón "Reset" para este barbero específico ---
        if (resetButton) {
            resetButton.addEventListener('click', function() {
                console.log(`Botón Reset para barbero ${barberId} clickeado.`);
                if (socket && socket.readyState === WebSocket.OPEN) { 
                    socket.send(JSON.stringify({
                        'action': 'reset_counter', // Usar 'action' para consistencia con el backend
                        'barber_id': barberId, 
                        'message': `Reiniciar el contador para barbero ${barberId}`
                    }));
                    console.log(`Mensaje de reinicio para barbero ${barberId} enviado al servidor.`);
                } else {
                    console.error(`WebSocket para barbero ${barberId} no está conectado o no está listo para enviar.`);
                    alert(`No se pudo conectar al servidor para reiniciar para barbero ${barberId}.`);
                }
            });
        } else {
            console.warn(`Botón 'Reset' no encontrado para barbero ${barberId}.`);
        }
    });
});