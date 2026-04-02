(function () {
    const TerminalUI = (window.TerminalUI = window.TerminalUI || {});
    const renderers = (TerminalUI.chartRenderers = TerminalUI.chartRenderers || {});
    const chartUtils = TerminalUI.chartUtils || {};
    const attachResize = chartUtils.attachResize;
    const clamp = chartUtils.clamp;
    const computeNiceAxisBounds = chartUtils.computeNiceAxisBounds;
    const formatCompactAxisValue = chartUtils.formatCompactAxisValue;
    const formatFullAxisValue = chartUtils.formatFullAxisValue;
    const resetEchartInstance = chartUtils.resetEchartInstance;

    function renderEquityChart(element, payload) {
        if (!payload.series || payload.series.length === 0) {
            element.innerHTML = '<div class="terminal-empty-state">No time-series data available.</div>';
            return;
        }

        element.innerHTML = "";
        const hasDrawdown = payload.series.some((s) => s.priceScaleId === "drawdown");

        const chart = LightweightCharts.createChart(element, {
            layout: {
                background: { color: "#0D0D0D" },
                textColor: "#FFFFFF",
                fontFamily: "JetBrains Mono",
            },
            grid: {
                vertLines: { color: "#111111" },
                horzLines: { color: "#111111" },
            },
            leftPriceScale: {
                visible: hasDrawdown,
                borderColor: "#222222",
                scaleMargins: { top: 0, bottom: 0.87 },
            },
            rightPriceScale: {
                borderColor: "#222222",
            },
            timeScale: {
                borderColor: "#222222",
                timeVisible: true,
                minBarSpacing: 0,
            },
            crosshair: {
                vertLine: { color: "#444444" },
                horzLine: { color: "#444444" },
            },
        });

        let benchmarkSeries = null;
        let minTime = Infinity;
        let maxTime = -Infinity;

        payload.series.forEach((seriesItem) => {
            const isDrawdown = seriesItem.priceScaleId === "drawdown";
            const seriesData = (seriesItem.points || []).map((point) => ({
                time: Math.floor(new Date(point.time).getTime() / 1000),
                value: point.value,
            }));

            let activeSeries;
            if (isDrawdown) {
                activeSeries = chart.addBaselineSeries({
                    baseValue: { type: "price", price: 0 },
                    topLineColor: "transparent",
                    topFillColor1: "transparent",
                    topFillColor2: "transparent",
                    bottomLineColor: "rgba(239, 83, 80, 0.8)",
                    bottomFillColor1: "rgba(239, 83, 80, 0.35)",
                    bottomFillColor2: "rgba(239, 83, 80, 0.05)",
                    lineWidth: 1,
                    title: seriesItem.name,
                    priceScaleId: "left",
                    priceLineVisible: false,
                    lastValueVisible: false,
                    crosshairMarkerVisible: false,
                });
            } else {
                activeSeries = chart.addLineSeries({
                    color: seriesItem.color || "#FFFFFF",
                    lineWidth: seriesItem.lineWidth || 2,
                    title: seriesItem.name,
                    priceScaleId: seriesItem.priceScaleId || "right",
                    priceLineVisible: false,
                    lastValueVisible: false,
                });
            }

            activeSeries.setData(seriesData);
            if (seriesData.length > 0) {
                minTime = Math.min(minTime, seriesData[0].time);
                maxTime = Math.max(maxTime, seriesData[seriesData.length - 1].time);
            }
            if (seriesItem.name === "Benchmark") {
                benchmarkSeries = activeSeries;
            }
        });

        if (hasDrawdown) {
            chart.priceScale("left").applyOptions({
                scaleMargins: { top: 0, bottom: 0.87 },
                borderColor: "#222222",
            });
        }

        attachResize(element, chart, true);

        setTimeout(() => {
            chart.timeScale().fitContent();
            if (minTime !== Infinity && maxTime !== -Infinity) {
                chart.timeScale().setVisibleRange({
                    from: minTime,
                    to: maxTime,
                });
            }
        }, 100);

        const toggleBenchmark = document.getElementById("toggle-benchmark");
        if (toggleBenchmark) {
            if (benchmarkSeries) {
                toggleBenchmark.parentElement.style.display = "";

                const newToggle = toggleBenchmark.cloneNode(true);
                toggleBenchmark.parentNode.replaceChild(newToggle, toggleBenchmark);

                newToggle.addEventListener("change", (e) => {
                    benchmarkSeries.applyOptions({
                        visible: e.target.checked
                    });
                });
                benchmarkSeries.applyOptions({
                    visible: newToggle.checked
                });
            } else {
                toggleBenchmark.parentElement.style.display = "none";
            }
        }
    }

    function renderScatterChart(element, payload) {
        const series = (payload.series || []).filter(
            (item) => item.points && item.points.length > 0,
        );
        if (series.length === 0) {
            const reason = payload.emptyReason ? " " + payload.emptyReason : "";
            element.innerHTML =
                '<div class="terminal-empty-state">No scatter data available.' + reason + "</div>";
            return;
        }
        resetEchartInstance(element);
        const chart = echarts.init(element);
        chart.setOption({
            backgroundColor: "#0D0D0D",
            animation: false,
            textStyle: { color: "#FFFFFF", fontFamily: "JetBrains Mono" },
            legend: { top: 0, textStyle: { color: "#FFFFFF" } },
            tooltip: {
                trigger: "item",
                formatter: (params) => {
                    const xVal = params.data[0];
                    const yVal = params.data[1];
                    return (
                        params.seriesName +
                        "<br>MAE: $" +
                        formatFullAxisValue(xVal) +
                        "<br>MFE: $" +
                        formatFullAxisValue(yVal)
                    );
                },
            },
            grid: { left: 12, right: 12, top: 40, bottom: 36, containLabel: true },
            xAxis: {
                type: "value",
                name: payload.xAxisLabel || "",
                nameLocation: "middle",
                nameGap: 26,
                inverse: payload.xAxisReversed === true,
                axisLabel: {
                    color: "#8A8A8A",
                    formatter: (value) => formatCompactAxisValue(Number(value)),
                },
                axisLine: { lineStyle: { color: "#222222" } },
                splitLine: { lineStyle: { color: "#111111" } },
            },
            yAxis: {
                type: "value",
                name: payload.yAxisLabel || "",
                nameLocation: "middle",
                nameGap: 44,
                axisLabel: {
                    color: "#8A8A8A",
                    formatter: (value) => formatCompactAxisValue(Number(value)),
                },
                axisLine: { lineStyle: { color: "#222222" } },
                splitLine: { lineStyle: { color: "#111111" } },
            },
            series: [
                ...series.map((item) => ({
                    name: item.name,
                    type: "scatter",
                    symbolSize: 6,
                    itemStyle: { color: item.color || "#8A8A8A", opacity: 0.7 },
                    data: (item.points || []).map((p) => [p.x, p.y]),
                })),
                ...(payload.diagonal
                    ? [
                        {
                            name: "Break-even",
                            type: "line",
                            showSymbol: false,
                            data: [
                                [payload.diagonal.x1, payload.diagonal.y1],
                                [payload.diagonal.x2, payload.diagonal.y2],
                            ],
                            lineStyle: { type: "dashed", color: "#6B7280", width: 1 },
                            itemStyle: { color: "#6B7280" },
                        },
                    ]
                    : []),
            ],
        });
        attachResize(element, chart);
    }

    function renderCategoryLineChart(element, payload) {
        if (!payload.categories || payload.categories.length === 0) {
            const reason = payload.emptyReason ? " " + payload.emptyReason : "";
            element.innerHTML =
                '<div class="terminal-empty-state">No data available.' + reason + "</div>";
            return;
        }
        resetEchartInstance(element);
        const chart = echarts.init(element);
        const containerWidth = Math.max(320, element.clientWidth || 320);
        const axisFontSize = containerWidth <= 720 ? 10 : 11;
        const plotHeight = Math.max(120, (element.clientHeight || 0) - 88);
        const targetTickCount = clamp(Math.floor(plotHeight / 44), 4, 6);
        const markLineData = (payload.thresholds || [])
            .filter((t) => t && Number.isFinite(Number(t.value)))
            .map((t) => ({
                yAxis: Number(t.value),
                lineStyle: { type: "dashed", color: t.color || "#8A8A8A", width: 1.5 },
                label: { formatter: t.label || "", color: t.color || "#8A8A8A", fontSize: 10 },
            }));
        const verticalMarkLineData = (payload.verticalMarkers || [])
            .filter((marker) => marker && marker.category)
            .map((marker) => ({
                xAxis: marker.category,
                lineStyle: { type: "dashed", color: marker.color || "#F59E0B", width: 1.5 },
                label: {
                    formatter: marker.label || "Time Stop Hold",
                    color: marker.color || "#F59E0B",
                    fontSize: 10,
                },
            }));
        const yValues = [];
        (payload.series || []).forEach((item) => {
            (item.values || []).forEach((value) => {
                const parsed = Number(value);
                if (Number.isFinite(parsed)) {
                    yValues.push(parsed);
                }
            });
        });
        (payload.thresholds || []).forEach((threshold) => {
            const parsed = Number(threshold && threshold.value);
            if (Number.isFinite(parsed)) {
                yValues.push(parsed);
            }
        });
        const axisBounds = computeNiceAxisBounds(yValues, 0.06, targetTickCount);
        const mainSeries = (payload.series || []).map((item) => ({
            name: item.name,
            type: "line",
            data: item.values,
            symbol: "circle",
            symbolSize: 7,
            lineStyle: { color: item.color || "#FFFFFF", width: 2 },
            itemStyle: { color: item.color || "#FFFFFF" },
            markLine: undefined,
        }));
        const helperLegendSeries = [];
        (payload.thresholds || []).forEach((t, index) => {
            if (!t || !markLineData[index]) {
                return;
            }
            helperLegendSeries.push({
                name: t.legend || t.label || "Threshold",
                type: "line",
                data: (payload.categories || []).map(() => null),
                symbol: "none",
                lineStyle: { type: "dashed", color: t.color || "#8A8A8A", width: 1.5 },
                itemStyle: { color: t.color || "#8A8A8A" },
                tooltip: { show: false },
                markLine: { symbol: "none", data: [markLineData[index]] },
            });
        });
        (payload.verticalMarkers || []).forEach((marker, index) => {
            if (!marker || !verticalMarkLineData[index]) {
                return;
            }
            helperLegendSeries.push({
                name: marker.legend || marker.label || "Vertical Marker",
                type: "line",
                data: (payload.categories || []).map(() => null),
                symbol: "none",
                lineStyle: { type: "dashed", color: marker.color || "#F59E0B", width: 1.5 },
                itemStyle: { color: marker.color || "#F59E0B" },
                tooltip: { show: false },
                markLine: { symbol: "none", data: [verticalMarkLineData[index]] },
            });
        });

        const mainSeriesByLegendName = new Map();
        (payload.series || []).forEach((item) => {
            mainSeriesByLegendName.set(item.name, item);
        });
        const thresholdByLegendName = new Map();
        (payload.thresholds || []).forEach((threshold) => {
            if (!threshold) {
                return;
            }
            const legendName = threshold.legend || threshold.label || "Threshold";
            thresholdByLegendName.set(legendName, threshold);
        });

        function updateCategoryLineAxisFromLegend(selected) {
            const activeValues = [];

            mainSeriesByLegendName.forEach((seriesItem, legendName) => {
                if (!selected || selected[legendName] !== false) {
                    (seriesItem.values || []).forEach((value) => {
                        const parsed = Number(value);
                        if (Number.isFinite(parsed)) {
                            activeValues.push(parsed);
                        }
                    });
                }
            });

            thresholdByLegendName.forEach((threshold, legendName) => {
                if (!selected || selected[legendName] !== false) {
                    const parsed = Number(threshold && threshold.value);
                    if (Number.isFinite(parsed)) {
                        activeValues.push(parsed);
                    }
                }
            });

            const bounds = computeNiceAxisBounds(activeValues, 0.06, targetTickCount);
            chart.setOption({
                yAxis: {
                    min: bounds.min,
                    max: bounds.max,
                    interval: bounds.interval,
                    splitNumber: bounds.splitNumber,
                },
            });
        }

        chart.setOption({
            backgroundColor: "#0D0D0D",
            animation: false,
            textStyle: { color: "#FFFFFF", fontFamily: "JetBrains Mono" },
            tooltip: {
                trigger: "axis",
                valueFormatter: (value) => "$" + formatFullAxisValue(Number(value)),
            },
            legend: { top: 0, textStyle: { color: "#FFFFFF" } },
            grid: { left: 12, right: 12, top: 40, bottom: 28, containLabel: true },
            xAxis: {
                type: "category",
                data: payload.categories,
                axisLabel: { color: "#8A8A8A", fontSize: axisFontSize },
                axisLine: { lineStyle: { color: "#222222" } },
            },
            yAxis: {
                type: "value",
                scale: true,
                min: axisBounds.min,
                max: axisBounds.max,
                interval: axisBounds.interval,
                splitNumber: axisBounds.splitNumber,
                axisLabel: {
                    color: "#8A8A8A",
                    fontSize: axisFontSize,
                    hideOverlap: true,
                    formatter: (value) => formatCompactAxisValue(Number(value)),
                },
                axisLine: { lineStyle: { color: "#222222" } },
                splitLine: { lineStyle: { color: "#111111" } },
            },
            series: mainSeries.concat(helperLegendSeries),
        });
        chart.on("legendselectchanged", (event) => {
            updateCategoryLineAxisFromLegend(event.selected || {});
        });
        attachResize(element, chart);
    }

    renderers.category_line = renderCategoryLineChart;
    renderers.scatter = renderScatterChart;
    renderers.equity = renderEquityChart;
})();
