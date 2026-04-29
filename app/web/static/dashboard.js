const dataEl = document.getElementById("chart-data");
const dashboardData = dataEl ? JSON.parse(dataEl.textContent) : { charts: {} };
const renderedCharts = new Map();
const sectorPalette = [
  "#153b25",
  "#2563eb",
  "#dc2626",
  "#f59e0b",
  "#7c3aed",
  "#0f766e",
  "#db2777",
  "#0891b2",
  "#65a30d",
  "#ea580c",
  "#475569",
];

function renderSectorComparisonChart() {
  const config = dashboardData.comparison;
  const canvas = document.getElementById("sector-comparison-chart");
  if (!config || !canvas || !window.Chart) return;
  const fullDates = config.dates;
  const fullSeries = config.series;
  const normalizeRangeValues = (values) => {
    const base = values.find((value) => Number.isFinite(value));
    if (!Number.isFinite(base) || base === 0) return values;
    return values.map((value) => (Number.isFinite(value) ? Number(((value / base) * 100).toFixed(2)) : value));
  };
  const sliceConfig = (range) => {
    const start = Math.max(0, fullDates.length - range);
    return {
      dates: fullDates.slice(start),
      series: fullSeries.map((serie) => {
        const values = serie.values.slice(start);
        return { ...serie, values: normalizeRangeValues(values) };
      }),
    };
  };
  const defaultRange = 126;
  const initialConfig = sliceConfig(defaultRange);

  const datasets = initialConfig.series.map((serie, index) => {
    const isBenchmark = index === 0;
    return {
      label: serie.label,
      data: serie.values,
      borderColor: sectorPalette[index % sectorPalette.length],
      backgroundColor: "transparent",
      borderWidth: isBenchmark ? 3 : 2,
      borderDash: isBenchmark ? [6, 4] : [],
      pointRadius: 0,
      tension: 0.22,
      spanGaps: true,
    };
  });
  const formatRankValue = (value) =>
    Number.isFinite(value) ? value.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : "-";
  const sectorRankAt = (dataIndex, datasetIndex) => {
    const value = datasets[datasetIndex]?.data?.[dataIndex];
    if (!Number.isFinite(value)) return null;
    const ranked = datasets
      .map((dataset, index) => ({ index, value: dataset.data[dataIndex] }))
      .filter((item) => Number.isFinite(item.value))
      .sort((a, b) => b.value - a.value);
    const rankIndex = ranked.findIndex((item) => item.index === datasetIndex);
    return rankIndex >= 0 ? rankIndex + 1 : null;
  };

  const chart = new Chart(canvas, {
    type: "line",
    data: { labels: initialConfig.dates, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          display: true,
          position: "bottom",
          labels: { boxWidth: 10, usePointStyle: true },
        },
        tooltip: {
          displayColors: true,
          itemSort: (a, b) => {
            return b.parsed.y - a.parsed.y;
          },
          callbacks: {
            label: (context) => {
              const value = formatRankValue(context.parsed.y);
              const rank = sectorRankAt(context.dataIndex, context.datasetIndex);
              if (context.datasetIndex === 0) {
                return `${rank ? `${rank}위 ` : ""}${context.dataset.label} 시장: ${value}`;
              }
              return `${rank ? `${rank}위 ` : ""}${context.dataset.label}: ${value}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 7 }, grid: { display: false } },
        y: {
          ticks: { maxTicksLimit: 6 },
          grid: { color: "rgba(148, 163, 184, 0.18)" },
        },
      },
    },
  });
  renderedCharts.set("sector-comparison", chart);
  document.querySelectorAll(".chart-range-control button").forEach((button) => {
    button.addEventListener("click", () => {
      const range = Number.parseInt(button.dataset.range || `${defaultRange}`, 10);
      const nextConfig = sliceConfig(Number.isFinite(range) ? range : defaultRange);
      chart.data.labels = nextConfig.dates;
      chart.data.datasets.forEach((dataset, index) => {
        dataset.data = nextConfig.series[index]?.values || [];
        datasets[index].data = dataset.data;
      });
      chart.update();
      document.querySelectorAll(".chart-range-control button").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
    });
  });
}

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

if (dashboardData.type === "sector") {
  renderSectorComparisonChart();
}
