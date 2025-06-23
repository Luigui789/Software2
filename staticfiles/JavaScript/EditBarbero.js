document.addEventListener('DOMContentLoaded', (event) => {
    console.log('DOM completamente cargado y parseado. Iniciando script EditBarbero.js.'); // Log para depuración

    // AHORA, TODO EL CÓDIGO QUE YA TIENES VA AQUÍ DENTRO:

    const btnsig_empleado = document.getElementById("Sig_empleado");
    const btnAtras = document.getElementById("Atras_empleado");

    // Selecciona los formularios por sus IDs.
    const formEmpleadoContainer = document.getElementById("formEmpleadoContainer"); 
    const formsSaveContainer = document.querySelector(".container-form.Save");     
    const formSaveContainer = document.getElementById("formSaveContainer");       

    const guardarBtn = document.getElementById("Guardar"); 

    let datosPrimerForm = {};

    // Paso al siguiente formulario
    // Verifica si el botón existe antes de añadir el listener
    if (btnsig_empleado) {
        btnsig_empleado.addEventListener("click", e => {
            e.preventDefault(); 
            
            datosPrimerForm = Object.fromEntries(new FormData(formEmpleadoContainer));
            
            // Asegúrate de que estos contenedores existan antes de manipularlos
            if (document.querySelector(".container-form.Empleado") && formsSaveContainer) {
                document.querySelector(".container-form.Empleado").classList.add("Hide");
                formsSaveContainer.classList.remove("Hide");
                console.log("Se movió al siguiente paso."); 
            } else {
                console.error("Error: No se encontraron los contenedores para cambiar de paso.");
            }
        });
        console.log("Listener para botón 'Siguiente' adjuntado."); // Log para depuración
    } else {
        console.error("Error: No se encontró el botón con ID 'Sig_empleado' al cargar el DOM."); // Log para depuración
    }


    // Volver al primer formulario
    if (btnAtras) {
        btnAtras.addEventListener("click", e => {
            if (document.querySelector(".container-form.Empleado") && formsSaveContainer) {
                document.querySelector(".container-form.Empleado").classList.remove("Hide");
                formsSaveContainer.classList.add("Hide");
                console.log("Se movió de vuelta al paso anterior."); 
            } else {
                console.error("Error: No se encontraron los contenedores para cambiar de paso (botón Atrás).");
            }
        });
        console.log("Listener para botón 'Atrás' adjuntado.");
    } else {
        console.error("Error: No se encontró el botón con ID 'Atras_empleado' al cargar el DOM.");
    }

    // Adjuntamos el evento al botón de "Guardar"
    if (guardarBtn) {
        guardarBtn.addEventListener('click', event => {
            event.preventDefault(); 
            
            console.log('DEBUG: Clic en botón Guardar detectado.'); 

            // Asegúrate de que los contenedores de los formularios existan
            if (!formEmpleadoContainer || !formSaveContainer) {
                console.error("Error: Uno o ambos contenedores de formulario no fueron encontrados.");
                alert("Error interno: No se pudo preparar el envío de datos. Recargue la página.");
                return;
            }

            const datosSegundoForm = Object.fromEntries(new FormData(formSaveContainer));
            const datosCompletos = { ...datosPrimerForm, ...datosSegundoForm };
            
            const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            console.log('DEBUG: Valor de barberoId:', barberoId); 

            if (typeof barberoId === 'undefined' || barberoId === null || barberoId === '') {
                alert('Error: No se encontró el ID del barbero para editar. Vuelva a cargar la página.');
                console.error('Error: barberoId no definido, es nulo o está vacío.');
                return; 
            }

            console.log('DEBUG: Verificación de barberoId superada. Continuando con fetch.'); 
            console.log('DEBUG: Datos completos antes de enviar (objeto JS):', datosCompletos);
            console.log('DEBUG: JSON String que se enviará:', JSON.stringify(datosCompletos));

            fetch(`/editar_barbero/${barberoId}/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json', 
                    'X-CSRFToken': csrftoken
                },
                body: JSON.stringify(datosCompletos) 
            })
            .then(response => {
                console.log('DEBUG: Respuesta de Fetch recibida.', response); 
                if (!response.ok) { 
                    return response.json().then(errorData => {
                        throw new Error(errorData.message || 'Error en la respuesta del servidor');
                    });
                }
                return response.json(); 
            })
            .then(data => {
                console.log('DEBUG: Datos de la respuesta:', data); 
                if (data.status === 'ok' || data.status === 'success') { 
                    alert(data.message || 'Operación completada exitosamente.');
                    window.location.href = "/AdBarbero/"; 
                } else { 
                    let errorMessage = data.message || 'Error al guardar.';
                    if (data.errores && data.errores.length > 0) {
                        errorMessage += '\n\n' + data.errores.join('\n'); 
                    }
                    alert(errorMessage); 
                }
            })
            .catch(error => {
                console.error('Error en la petición Fetch o en el parseo de la respuesta:', error);
                alert(error.message || 'Ocurrió un error inesperado al procesar la solicitud.'); 
            });
        });
        console.log("Listener para botón 'Guardar' adjuntado.");
    } else {
        console.error("Error: No se encontró el botón con ID 'Guardar' al cargar el DOM.");
    }

}); // CIERRE DE DOMContentLoaded