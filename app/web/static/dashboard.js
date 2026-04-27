const dataEl = document.getElementById("chart-data");
const dashboardData = dataEl ? JSON.parse(dataEl.textContent) : { charts: {} };
const renderedCharts = new Map();

function ensureChart(chartId) {
  if (renderedCharts.has(chartId)) return;
  const config = dashboardData.charts[chartId];
  const canvas = document.getElementById(`chart-${chartId}`);
  if (!config || !canvas || !window.Chart) return;

  const labels = config.points.map((point) => point.date);
  const datasets =
    dashboardData.type === "sector"
      ? [
          {
            label: config.label,
            data: config.points.map((point) => point.sector),
            borderColor: "#2563eb",
            backgroundColor: "rgba(37, 99, 235, 0.10)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.25,
          },
          {
            label: config.benchmark,
            data: config.points.map((point) => point.benchmark),
            borderColor: "#6b7280",
            backgroundColor: "rgba(107, 114, 128, 0.08)",
            borderWidth: 2,
            pointRadius: 0,
            tension: 0.25,
          },
        ]
      : [
          {
            label: config.label,
            data: config.points.map((point) => point.value),
            borderColor: "#0f766e",
            backgroundColor: "rgba(15, 118, 110, 0.10)",
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.25,
          },
        ];

  const chart = new Chart(canvas, {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: dashboardData.type === "sector", labels: { boxWidth: 10 } },
        tooltip: { displayColors: false },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 6 }, grid: { display: false } },
        y: { ticks: { maxTicksLimit: 5 }, grid: { color: "rgba(148, 163, 184, 0.18)" } },
      },
    },
  });
  renderedCharts.set(chartId, chart);
}

document.querySelectorAll(".history-panel").forEach((panel) => {
  panel.addEventListener("toggle", () => {
    if (panel.open) ensureChart(panel.dataset.chartId);
  });
});

