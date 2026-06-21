let tempChart, humChart, lightChart;

const commonConfig = {
    responsive: true,
    maintainAspectRatio: false,
    elements: { point: { radius: 2 } },
    plugins: { legend: { display: false } }
};

function initCharts() {
    tempChart = new Chart(document.getElementById('tempChart'), {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Temp', data: [], borderColor: '#ff6384', backgroundColor: 'rgba(255, 99, 132, 0.2)', fill: true, tension: 0.4 }] },
        options: { ...commonConfig, scales: { x: { grid: { display: false } }, y: { suggestedMin: 10, suggestedMax: 40, ticks: { callback: v => v + ' °C' } } }, plugins: { title: { display: true, text: 'Temperature (°C)' }, legend: { display: false } } }
    });

    humChart = new Chart(document.getElementById('humChart'), {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Humidity', data: [], borderColor: '#36a2eb', backgroundColor: 'rgba(54, 162, 235, 0.2)', fill: true, tension: 0.4 }] },
        options: { ...commonConfig, scales: { x: { grid: { display: false } }, y: { min: 0, max: 100, ticks: { callback: v => v + ' %' } } }, plugins: { title: { display: true, text: 'Humidity (%)' }, legend: { display: false } } }
    });

    lightChart = new Chart(document.getElementById('lightChart'), {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Light', data: [], borderColor: '#ffcd56', backgroundColor: 'rgba(255, 205, 86, 0.2)', fill: true, tension: 0.4 }] },
        options: { ...commonConfig, scales: { x: { grid: { display: false } }, y: { suggestedMin: 0, suggestedMax: 1000, ticks: { callback: v => v + ' Lx' } } }, plugins: { title: { display: true, text: 'Light Level (Lux)' }, legend: { display: false } } }
    });
}

function updateCharts(range) {
    document.querySelectorAll('.time-filters button').forEach(b => b.classList.remove('active'));
    document.getElementById('btn-' + range).classList.add('active');

    fetch(`/api/history?range=${range}`)
        .then(res => res.json())
        .then(data => {
            tempChart.data.labels = data.labels;
            tempChart.data.datasets[0].data = data.temp;
            tempChart.update();
            humChart.data.labels = data.labels;
            humChart.data.datasets[0].data = data.hum;
            humChart.update();
            lightChart.data.labels = data.labels;
            lightChart.data.datasets[0].data = data.light;
            lightChart.update();
        })
        .catch(err => console.error("History Error:", err));
}

function updateRealTimeData() {
    fetch('/api/sensor_data')
        .then(res => res.json())
        .then(data => {
            if (data.timestamp) {
                document.getElementById('temp').innerText = data.Temp || "--";
                document.getElementById('hum').innerText = data.Hum || "--";
                document.getElementById('dist').innerText = data.Dist || "--";
                document.getElementById('light').innerText = data.Light || "--";
                document.getElementById('last-update').innerText = data.timestamp;

                if (data.Dist > 20) {
                    document.getElementById('tank-alert').style.display = 'block';
                } else {
                    document.getElementById('tank-alert').style.display = 'none';
                }
            }
        })
        .catch(err => console.error("Realtime Error:", err));
}

function triggerWatering() {
    if (confirm("Are you sure you want to activate the pump?")) {
        fetch('/api/water_plant', { method: 'POST' })
            .then(res => res.json())
            .then(data => alert(data.message))
            .catch(err => alert("Error sending command"));
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    updateRealTimeData();
    updateCharts('hour');

    setInterval(updateRealTimeData, 2000);
    setInterval(() => {
        const activeBtn = document.querySelector('.time-filters button.active');
        const activeRange = activeBtn ? activeBtn.id.replace('btn-', '') : 'hour';
        updateCharts(activeRange);
    }, 30000);
});