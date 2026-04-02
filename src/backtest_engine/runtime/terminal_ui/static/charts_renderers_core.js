(function () {
    const TerminalUI = (window.TerminalUI = window.TerminalUI || {});
    const renderers = (TerminalUI.chartRenderers = TerminalUI.chartRenderers || {});
    const chartUtils = TerminalUI.chartUtils || {};
    const attachResize = chartUtils.attachResize;
    const buildEchartsSeries = chartUtils.buildEchartsSeries;
    const clamp = chartUtils.clamp;
    const collectLineValues = chartUtils.collectLineValues;
    const computeNiceAxisBounds = chartUtils.computeNiceAxisBounds;
    const formatCompactAxisValue = chartUtils.formatCompactAxisValue;
    const formatFullAxisValue = chartUtils.formatFullAxisValue;
    const formatTimeAxisLabel = chartUtils.formatTimeAxisLabel;
    const resetEchartInstance = chartUtils.resetEchartInstance;

    function renderLineChart(element, payload) {
        if (!payload.series || payload.series.length === 0) {
            element.innerHTML = '<div class="terminal-empty-state">No chart data available.</div>';
            return;
        }
        resetEchartInstance(element);
        const isMini = element.classList.contains("terminal-chart--mini");
        const containerWidth = Math.max(320, element.clientWidth || 320);
        const axisFontSize = isMini ? (containerWidth <= 720 ? 9 : 10) : containerWidth <= 720 ? 10 : 11;
        const plotHeight = Math.max(120, (element.clientHeight || 0) - 88);
        const targetTickCount = clamp(Math.floor(plotHeight / 44), 4, 6);
        const defaultYAxisPadding = isMini ? 0.02 : 0.06;
        const yAxisPaddingRatio = Number.isFinite(Number(payload.yAxisPaddingRatio))
            ? Number(payload.yAxisPaddingRatio)
            : defaultYAxisPadding;
        const chart = echarts.init(element);
        const markLineData = (payload.thresholds || []).map((threshold) => ({
            yAxis: threshold.value,
            label: isMini
                ? { show: false }
                : {
                    formatter: threshold.label || "",
                    position: "start",
                },
        }));
        const builtSeries = buildEchartsSeries(payload.series);
        const axisBounds = computeNiceAxisBounds(
            collectLineValues(builtSeries, payload.thresholds),
            yAxisPaddingRatio,
            targetTickCount,
        );
        const grid = isMini
            ? { left: 4, right: 6, top: 4, bottom: 4, containLabel: true }
            : { left: 12, right: 12, top: 40, bottom: 28, containLabel: true };
        const legend = isMini
            ? {
                show: true,
                top: 0,
                left: "center",
                padding: [0, 0],
                itemGap: 8,
                itemWidth: 12,
                itemHeight: 10,
                textStyle: { color: "#FFFFFF", fontSize: 12, fontFamily: "JetBrains Mono" },
                selectedMode: true,
                inactiveColor: "#666666",
            }
            : {
                top: 0,
                textStyle: { color: "#FFFFFF" },
            };

        chart.setOption({
            backgroundColor: "#0D0D0D",
            animation: false,
            textStyle: { color: "#FFFFFF", fontFamily: "JetBrains Mono" },
            tooltip: {
                trigger: "axis",
                valueFormatter: (value) => formatFullAxisValue(Number(value)),
            },
            legend: legend,
            grid: grid,
            xAxis: {
                type: "time",
                axisLine: { lineStyle: { color: "#222222" } },
                axisLabel: {
                    color: "#8A8A8A",
                    fontSize: axisFontSize,
                    margin: isMini ? 4 : 8,
                    hideOverlap: true,
                    formatter: formatTimeAxisLabel,
                },
                splitLine: { lineStyle: { color: "#111111" } },
            },
            yAxis: {
                type: "value",
                scale: true,
                min: axisBounds.min,
                max: axisBounds.max,
                interval: axisBounds.interval,
                splitNumber: axisBounds.splitNumber,
                axisLine: { lineStyle: { color: "#222222" } },
                axisLabel: {
                    color: "#8A8A8A",
                    fontSize: axisFontSize,
                    margin: isMini ? 4 : 8,
                    hideOverlap: true,
                    formatter: (value) => formatCompactAxisValue(Number(value)),
                },
                splitLine: { lineStyle: { color: "#111111" } },
            },
            series: builtSeries.map((item) => ({
                ...item,
                markLine: markLineData.length > 0 ? { symbol: "none", lineStyle: { color: "#444444" }, data: markLineData } : undefined,
            })),
        });
        attachResize(element, chart);
    }

    function renderHeatmap(element, payload) {
        if (!payload.values || payload.values.length === 0) {
            const reason = payload.emptyReason ? " " + payload.emptyReason : "";
            const dropped = payload.droppedLabels && payload.droppedLabels.length > 0
                ? " Dropped: " + payload.droppedLabels.join(", ") + "."
                : "";
            element.innerHTML =
                '<div class="terminal-empty-state">No heatmap data available.' + reason + dropped + "</div>";
            return;
        }
        resetEchartInstance(element);
        const xLabels = payload.xLabels || [];
        const yLabels = payload.yLabels || [];
        const containerWidth = Math.max(320, element.clientWidth || 320);
        const containerHeight = Math.max(220, element.clientHeight || 220);
        const maxXLabelLength = xLabels.reduce((maxLen, label) => Math.max(maxLen, String(label || "").length), 0);
        const maxYLabelLength = yLabels.reduce((maxLen, label) => Math.max(maxLen, String(label || "").length), 0);

        const xAxisMaxChars = containerWidth <= 900 ? 10 : 16;
        const yAxisMaxChars = containerWidth <= 900 ? 12 : 18;
        const xAxisRotate = maxXLabelLength > xAxisMaxChars ? 26 : 0;

        const heatmapClamp = (value, min, max) => Math.max(min, Math.min(max, value));
        const dynamicBottom = heatmapClamp(
            Math.round(containerHeight * 0.08 + (xAxisRotate > 0 ? 20 : 6)),
            28,
            56,
        );
        const dynamicLeft = heatmapClamp(
            Math.round(18 + Math.min(maxYLabelLength, yAxisMaxChars) * 7.2),
            76,
            148,
        );

        const compactLabel = (label, maxChars) => {
            const raw = String(label || "");
            if (raw.length <= maxChars) {
                return raw;
            }
            return raw.slice(0, Math.max(4, maxChars - 3)) + "...";
        };
        const chart = echarts.init(element);
        chart.setOption({
            backgroundColor: "#0D0D0D",
            animation: false,
            textStyle: { color: "#FFFFFF", fontFamily: "JetBrains Mono" },
            tooltip: {
                confine: true,
                formatter: ({ value }) => {
                    const xIndex = Number(value[0]);
                    const yIndex = Number(value[1]);
                    const corrValue = Number(value[2]);
                    const xLabel = xLabels[xIndex] || "";
                    const yLabel = yLabels[yIndex] || "";
                    return (
                        yLabel + " -> " + xLabel + ": " + corrValue.toFixed(2)
                    );
                },
            },
            grid: { left: dynamicLeft, right: 14, top: 44, bottom: dynamicBottom, containLabel: false },
            xAxis: {
                type: "category",
                data: xLabels,
                splitArea: { show: true },
                axisLabel: {
                    color: "#8A8A8A",
                    rotate: xAxisRotate,
                    margin: xAxisRotate > 0 ? 12 : 8,
                    formatter: (value) => compactLabel(value, xAxisMaxChars),
                },
                axisLine: { lineStyle: { color: "#222222" } },
            },
            yAxis: {
                type: "category",
                data: yLabels,
                splitArea: { show: true },
                axisLabel: {
                    color: "#8A8A8A",
                    margin: 6,
                    formatter: (value) => compactLabel(value, yAxisMaxChars),
                },
                axisLine: { lineStyle: { color: "#222222" } },
            },
            visualMap: {
                min: -1,
                max: 1,
                calculable: false,
                orient: "horizontal",
                left: "center",
                top: 2,
                textStyle: { color: "#8A8A8A" },
                inRange: { color: ["#EF4444", "#1A1A1A", "#22C55E"] },
            },
            series: [
                {
                    type: "heatmap",
                    data: payload.values,
                    label: { show: true, color: "#FFFFFF", formatter: ({ value }) => Number(value[2]).toFixed(2) },
                    emphasis: { itemStyle: { borderColor: "#FFFFFF", borderWidth: 1 } },
                },
            ],
        });
        attachResize(element, chart);
    }

    function renderBarChart(element, payload) {
        if (!payload.categories || payload.categories.length === 0) {
            const reason = payload.emptyReason ? " " + payload.emptyReason : "";
            element.innerHTML = '<div class="terminal-empty-state">No bar-chart data available.' + reason + '</div>';
            return;
        }
        resetEchartInstance(element);
        const chart = echarts.init(element);
        const yAxisIsPercent = payload.yAxisFormat === "percent";
        const yAxisLabelFormatter = yAxisIsPercent ? "{value}%" : undefined;
        const showAllCategoryLabels = payload.showAllCategoryLabels === true;
        const hasSecondAxis = (payload.series || []).some((s) => s.yAxisIndex === 1);
        const yAxis = [
            {
                type: "value",
                axisLabel: { color: "#8A8A8A", formatter: yAxisLabelFormatter },
                axisLine: { lineStyle: { color: "#222222" } },
                splitLine: { lineStyle: { color: "#111111" } },
            },
        ];
        if (hasSecondAxis) {
            yAxis.push({
                type: "value",
                axisLabel: { color: "#3B82F6", formatter: "{value}%" },
                axisLine: { lineStyle: { color: "#3B82F6" } },
                splitLine: { show: false },
            });
        }
        chart.setOption({
            backgroundColor: "#0D0D0D",
            animation: false,
            textStyle: { color: "#FFFFFF", fontFamily: "JetBrains Mono" },
            tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
            legend: payload.hideLegend ? { show: false } : { top: 0, textStyle: { color: "#FFFFFF" } },
            grid: { left: 56, right: hasSecondAxis ? 56 : 20, top: 36, bottom: showAllCategoryLabels ? 52 : 28 },
            xAxis: {
                type: "category",
                data: payload.categories,
                axisLabel: {
                    color: "#8A8A8A",
                    interval: showAllCategoryLabels ? 0 : "auto",
                    hideOverlap: !showAllCategoryLabels,
                    fontSize: showAllCategoryLabels ? 10 : 12,
                },
                axisLine: { lineStyle: { color: "#222222" } },
            },
            yAxis: yAxis,
            series: (payload.series || []).map((item, index) => {
                const isItemPercent = yAxisIsPercent || item.yAxisIndex === 1;
                return {
                    name: item.name,
                    type: "bar",
                    yAxisIndex: item.yAxisIndex || 0,
                    tooltip: {
                        valueFormatter: (value) => Number(value).toFixed(2) + (isItemPercent ? "%" : "")
                    },
                    data: item.itemColors
                        ? (item.values || []).map((v, i) => ({
                            value: v,
                            itemStyle: { color: (item.itemColors || [])[i] || "#8A8A8A" },
                        }))
                        : item.values,
                    itemStyle: item.itemColors
                        ? undefined
                        : { color: ["#22C55E", "#3B82F6", "#EAB308"][index % 3] },
                };
            }),
        });
        attachResize(element, chart);
    }

    function renderDistributionChart(element, payload) {
        if (!payload.bins || payload.bins.length === 0) {
            element.innerHTML = '<div class="terminal-empty-state">No distribution data available.</div>';
            return;
        }
        resetEchartInstance(element);
        const bins = payload.bins || [];
        const centers = bins.map((bin) => Number(bin.center));
        const markerStyles = {
            "VaR 95": { color: "#F59E0B", type: "solid" },
            "CVaR 95": { color: "#FB923C", type: "solid" },
            "VaR 99": { color: "#EF4444", type: "solid" },
            Mean: { color: "#9CA3AF", type: "dashed" },
        };
        const markerIndexHits = {};
        const markLineData = (payload.markers || [])
            .filter((marker) => marker && Number.isFinite(Number(marker.value)))
            .map((marker) => {
                const value = Number(marker.value);
                let closestIndex = 0;
                let closestDistance = Infinity;
                centers.forEach((center, index) => {
                    const distance = Math.abs(center - value);
                    if (distance < closestDistance) {
                        closestDistance = distance;
                        closestIndex = index;
                    }
                });
                const hitCount = markerIndexHits[closestIndex] || 0;
                markerIndexHits[closestIndex] = hitCount + 1;
                const style = markerStyles[marker.label] || { color: "#8A8A8A", type: "solid" };
                return {
                    xAxis: closestIndex,
                    lineStyle: { color: style.color, type: style.type, width: 1.5 },
                    label: {
                        show: true,
                        formatter: marker.label,
                        color: style.color,
                        position: "insideEndTop",
                        distance: 8 + hitCount * 12,
                        fontSize: 10,
                    },
                };
            });

        const chart = echarts.init(element);
        chart.setOption({
            backgroundColor: "#0D0D0D",
            animation: false,
            textStyle: { color: "#FFFFFF", fontFamily: "JetBrains Mono" },
            tooltip: { trigger: "axis" },
            grid: { left: 48, right: 20, top: 20, bottom: 28 },
            xAxis: {
                type: "category",
                data: bins.map((bin) => bin.label),
                axisLabel: { color: "#8A8A8A", interval: Math.max(0, Math.floor(bins.length / 12)) },
                axisLine: { lineStyle: { color: "#222222" } },
            },
            yAxis: {
                type: "value",
                axisLabel: { color: "#8A8A8A" },
                axisLine: { lineStyle: { color: "#222222" } },
                splitLine: { lineStyle: { color: "#111111" } },
            },
            series: [
                {
                    type: "bar",
                    data: bins.map((bin) => ({
                        value: bin.value,
                        itemStyle: {
                            color: Number(bin.center) < 0 ? "#EF4444" : "#22C55E",
                        },
                    })),
                    markLine: markLineData.length > 0 ? { symbol: "none", data: markLineData } : undefined,
                },
            ],
        });
        attachResize(element, chart);
    }

    renderers.distribution = renderDistributionChart;
    renderers.bar = renderBarChart;
    renderers.heatmap = renderHeatmap;
    renderers.line = renderLineChart;
})();
