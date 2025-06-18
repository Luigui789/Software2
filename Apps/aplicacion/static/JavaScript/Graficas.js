const labels = JSON.parse(document.getElementById('labels-data').textContent);
const data = JSON.parse(document.getElementById('data-data').textContent);


// Gráfica de barberos
const ctx1 = document.getElementById('barberoChart').getContext('2d');
new Chart(ctx1, {
    type: 'bar',
    data: {
        labels: labels,
        datasets: [{
            label: 'Cortes por barbero',
            data: data,
            backgroundColor: 'rgba(54, 162, 235, 0.7)',
            borderColor: 'rgba(54, 162, 235, 1)',
            borderWidth: 1
        }]
    },
    options: {
        responsive: true,
        scales: { y: { beginAtZero: true, precision: 0 } }
    }
});

// Gráfica de cortes más realizados


// Datos para gráfico 2
const corteLabels = JSON.parse(document.getElementById('corte-labels-data').textContent);
const corteData = JSON.parse(document.getElementById('corte-data-data').textContent);

const ctxCortes = document.getElementById('corteChart').getContext('2d');
new Chart(ctxCortes, {
    type: 'bar',
    data: {
        labels: corteLabels,   // <--- usa corteLabels
        datasets: [{
            label: 'Corte más realizado',
            data: corteData,   // <--- usa corteData
            backgroundColor: 'rgba(255, 99, 132, 0.5)',
            borderColor: 'rgba(255, 99, 132, 1)',
            borderWidth: 1
        }]
    }
});