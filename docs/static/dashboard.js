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

function renderMacroScoreHistoryChart() {
  const points = dashboardData.scoreHistory || [];
  const canvas = document.getElementById("macro-score-history-chart");
  if (!points.length || !canvas || !window.Chart || renderedCharts.has("macro-score-history")) return;

  const normalizeRange = (days) => {
    if (days === "all") return points;
    const parsedDays = Number.parseInt(days || "365", 10);
    const lastDate = new Date(points[points.length - 1].date);
    const cutoff = new Date(lastDate);
    cutoff.setDate(lastDate.getDate() - (Number.isFinite(parsedDays) ? parsedDays : 365));
    return points.filter((point) => new Date(point.date) >= cutoff);
  };
  const defaultRange = "365";
  let activePoints = normalizeRange(defaultRange);
  const chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: activePoints.map((point) => point.date),
      datasets: [
        {
          label: "시장 환경 점수",
          data: activePoints.map((point) => point.score),
          borderColor: "#153b25",
          backgroundColor: "transparent",
          borderWidth: 3,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: "#f4d56b",
          pointHoverBorderColor: "#153b25",
          pointHoverBorderWidth: 2,
          tension: 0.22,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      animation: {
        duration: 650,
        easing: "easeOutQuart",
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          displayColors: false,
          callbacks: {
            label: (context) => {
              const point = activePoints[context.dataIndex];
              const label = point?.regime_label ? ` · ${point.regime_label}` : "";
              return `${context.parsed.y}/100${label}`;
            },
          },
        },
      },
      scales: {
        x: { ticks: { maxTicksLimit: 7 }, grid: { display: false } },
        y: {
          min: 0,
          max: 100,
          ticks: { stepSize: 20 },
          grid: { color: "rgba(148, 163, 184, 0.18)" },
        },
      },
    },
  });
  canvas.dataset.activeRange = defaultRange;
  renderedCharts.set("macro-score-history", chart);

  document.querySelectorAll(".score-range-control button").forEach((button) => {
    button.addEventListener("click", () => {
      const range = button.dataset.scoreDays || defaultRange;
      canvas.dataset.activeRange = range;
      activePoints = normalizeRange(range);
      chart.data.labels = activePoints.map((point) => point.date);
      chart.data.datasets[0].data = activePoints.map((point) => point.score);
      chart.update();
      document.querySelectorAll(".score-range-control button").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
    });
  });
}

function renderSectorComparisonChart() {
  const config = dashboardData.comparison;
  const canvas = document.getElementById("sector-comparison-chart");
  if (!config || !canvas || !window.Chart) return;
  let dismissedTooltipKey = null;
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
  const getOrCreateTooltip = () => {
    const parent = canvas.parentNode;
    let tooltipEl = parent.querySelector(".chart-tooltip");
    if (tooltipEl) return tooltipEl;

    tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    tooltipEl.setAttribute("role", "status");
    tooltipEl.setAttribute("aria-live", "polite");

    const closeButton = document.createElement("button");
    closeButton.className = "chart-tooltip-close";
    closeButton.type = "button";
    closeButton.setAttribute("aria-label", "툴팁 닫기");
    closeButton.textContent = "x";
    closeButton.addEventListener("click", (event) => {
      event.stopPropagation();
      dismissedTooltipKey = tooltipEl.dataset.tooltipKey || dismissedTooltipKey;
      tooltipEl.classList.remove("visible");
    });

    const titleEl = document.createElement("strong");
    titleEl.className = "chart-tooltip-title";
    const bodyEl = document.createElement("div");
    bodyEl.className = "chart-tooltip-body";

    tooltipEl.append(closeButton, titleEl, bodyEl);
    parent.appendChild(tooltipEl);
    return tooltipEl;
  };
  const renderExternalTooltip = ({ chart, tooltip }) => {
    const tooltipEl = getOrCreateTooltip();
    if (tooltip.opacity === 0) {
      tooltipEl.classList.remove("visible");
      return;
    }

    const dataIndex = tooltip.dataPoints?.[0]?.dataIndex ?? null;
    const tooltipKey = dataIndex === null ? "" : `${chart.data.labels[dataIndex]}-${dataIndex}`;
    if (dismissedTooltipKey === tooltipKey) {
      tooltipEl.classList.remove("visible");
      return;
    }

    const titleEl = tooltipEl.querySelector(".chart-tooltip-title");
    const bodyEl = tooltipEl.querySelector(".chart-tooltip-body");
    titleEl.textContent = tooltip.title?.[0] || "";
    bodyEl.replaceChildren();

    tooltip.dataPoints.forEach((point) => {
      const value = formatRankValue(point.parsed.y);
      const rank = sectorRankAt(point.dataIndex, point.datasetIndex);
      const row = document.createElement("div");
      row.className = "chart-tooltip-row";

      const marker = document.createElement("span");
      marker.className = "chart-tooltip-marker";
      marker.style.backgroundColor = point.dataset.borderColor;

      const label = document.createElement("span");
      label.textContent =
        point.datasetIndex === 0
          ? `${rank ? `${rank}위 ` : ""}${point.dataset.label} 시장: ${value}`
          : `${rank ? `${rank}위 ` : ""}${point.dataset.label}: ${value}`;

      row.append(marker, label);
      bodyEl.appendChild(row);
    });

    const parentRect = chart.canvas.parentNode.getBoundingClientRect();
    const maxLeft = Math.max(12, parentRect.width - 238);
    const maxTop = Math.max(12, parentRect.height - 220);
    const left = Math.min(Math.max(12, tooltip.caretX + 14), maxLeft);
    const top = Math.min(Math.max(12, tooltip.caretY + 14), maxTop);
    tooltipEl.dataset.tooltipKey = tooltipKey;
    tooltipEl.style.left = `${left}px`;
    tooltipEl.style.top = `${top}px`;
    tooltipEl.classList.add("visible");
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
          display: false,
        },
        tooltip: {
          enabled: false,
          external: renderExternalTooltip,
          itemSort: (a, b) => {
            return b.parsed.y - a.parsed.y;
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

const scoreHistoryPanel = document.getElementById("score-history-panel");
if (scoreHistoryPanel) {
  scoreHistoryPanel.addEventListener("toggle", () => {
    if (scoreHistoryPanel.open) renderMacroScoreHistoryChart();
  });
}

if (dashboardData.type === "sector") {
  renderSectorComparisonChart();
}
