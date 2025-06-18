document.addEventListener('DOMContentLoaded', function() {
    const quadrants = document.querySelectorAll('.quadrant');

    // Función auxiliar para obtener el token CSRF desde la cookie
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

    // Obtener el token CSRF una vez al cargar el script
    const csrftoken = getCookie('csrftoken'); 

    quadrants.forEach(quadrant => {
        const barberId = quadrant.dataset.barberId;
        const currentNumberDisplay = quadrant.querySelector('.current-queue-number');
        const nextButton = quadrant.querySelector('.next-button');
        const resetButton = quadrant.querySelector('.reset-button'); // <-- Obtener el botón de reset para este cuadrante

        // --- Configuración de WebSocket para cada barbero ---
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket( // <-- Esta es la variable 'socket' para este barbero
            protocol + '//' + window.location.host + `/ws/queue/${barberId}/`
        );

        socket.onmessage = function(e) {
            const data = JSON.parse(e.data);
            if (data.type === 'queue_update' && data.barber_id == barberId) {
                currentNumberDisplay.textContent = data.number;
                console.log(`Barbero ${barberId}: Número actualizado a ${data.number}`);
            }
        };

        socket.onclose = function(e) {
            console.error(`Socket para barbero ${barberId} cerrado inesperadamente.`, e);
        };

        socket.onerror = function(e) {
            console.error(`Error en el socket para barbero ${barberId}:`, e);
        };

        // --- Lógica del botón "Siguiente Turno" ---
        if (nextButton) {
            nextButton.onclick = function() {
                fetch('/increment-queue/', { // La URL debe coincidir con la definida en Django
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        // ¡IMPORTANTE! Envía el token CSRF aquí:
                        'X-CSRFToken': csrftoken, 
                    },
                    body: JSON.stringify({ barber_id: barberId }) // Envía el ID del barbero
                })
                .then(response => {
                    // Verifica si la respuesta es un 403 Forbidden para un mejor mensaje de depuración
                    if (response.status === 403) {
                        console.error("Error 403 Forbidden: Probablemente CSRF token missing o inválido. Asegúrate de que el token se esté enviando correctamente.");
                        throw new Error("Error de seguridad: Petición bloqueada (CSRF).");
                    }
                    if (!response.ok) {
                        throw new Error(`Error HTTP! Estado: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    if (data.success) {
                        console.log(`Botón de barbero ${barberId} presionado. Nuevo número: ${data.new_current_number}`);
                        // El número en la UI se actualizará automáticamente gracias al mensaje del WebSocket,
                        // por lo que no necesitas actualizar currentNumberDisplay.textContent directamente aquí.
                    } else {
                        console.error('Error al incrementar la cola:', data.message);
                        alert(`Error al avanzar el turno para barbero ${barberId}: ${data.message}`);
                    }
                })
                .catch(error => {
                    console.error('Error de red o servidor:', error);
                    alert('Hubo un problema de conexión al intentar avanzar el turno.');
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
                        'type': 'reset_counter', // El tipo de mensaje
                        'barber_id': barberId,   // ¡Enviar el ID del barbero para que el consumer sepa cuál resetear!
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