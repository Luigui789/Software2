const btnsig_empleado = document.getElementById("Sig_empleado");
const btnAtras = document.getElementById("Atras_empleado");

const formEmpleado = document.querySelector(".Empleado form");
const formsSave = document.querySelector(".Save");
const formSave = document.querySelector(".Save form");

// Al dar click en "Siguiente", guarda los datos del primer form
btnsig_empleado.addEventListener("click", e => {
    e.preventDefault(); // Evita submit y recarga
    datosPrimerForm = Object.fromEntries(new FormData(formEmpleado));
    document.querySelector(".Empleado").classList.add("Hide");
    formsSave.classList.remove("Hide");
});

// Al dar click en "Atrás"
btnAtras.addEventListener("click", e => {
    document.querySelector(".Empleado").classList.remove("Hide");
    formsSave.classList.add("Hide");
});

// Al guardar el segundo form, muestra los datos de ambos forms
formSave.addEventListener('submit', event => {
    event.preventDefault();
    console.log("Holas")
    const datosSegundoForm = Object.fromEntries(new FormData(formSave));
    // Combina ambos objetos
    const datosCompletos = { ...datosPrimerForm, ...datosSegundoForm };
    
    const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    fetch(`/editar_barbero/${barberoId}/`, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrftoken
    },
    body: JSON.stringify(datosCompletos)
})
    .then(response => response.json())
    .then(data => {
        if (data.status === 'ok') {
            window.location.href = "/AdBarbero/"; // Cambia la URL si tu ruta es diferente
        } else {
            alert('Error al guardar');
        }
})
    .catch(error => {
        alert('Error al guardar');
        console.error(error);
    });
});