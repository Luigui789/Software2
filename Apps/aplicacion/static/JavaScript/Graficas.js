    const labels = JSON.parse(document.getElementById('labels-data').textContent);
    const data = JSON.parse(document.getElementById('data-data').textContent);

    const ctx = document.getElementById('barberoChart').getContext('2d');
    if (labels.length && data.length) {
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Cortes realizados',
                    data: data,
                    backgroundColor: 'rgba(54, 162, 235, 0.7)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0
                        }
                    }
                }
            }
        });
    } else {
        console.log("No hay datos para mostrar.");
    }