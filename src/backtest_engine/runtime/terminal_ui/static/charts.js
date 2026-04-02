(function () {
    const TerminalUI = (window.TerminalUI = window.TerminalUI || {});
    const chartUtils = TerminalUI.chartUtils || {};
    const beginChartRequest = chartUtils.beginChartRequest;
    const endChartRequest = chartUtils.endChartRequest;

    function getChartRenderer(name) {
        const renderers = TerminalUI.chartRenderers || {};
        if (name && typeof renderers[name] === "function") {
            return renderers[name];
        }
        return renderers.line;
    }

    function resolveChartEndpoint(element) {
        const endpoint = element.dataset.chartEndpoint;
        if (!endpoint) {
            return "";
        }
        if (element.dataset.decompositionLinked !== "true") {
            return endpoint;
        }
        const sortInput = document.getElementById("decomposition-sort-by-input");
        const sortBy = sortInput ? (sortInput.value || "").trim() : "";
        if (!sortBy) {
            return endpoint;
        }
        const separator = endpoint.includes("?") ? "&" : "?";
        return endpoint + separator + "sort_by=" + encodeURIComponent(sortBy);
    }

    function renderChart(element) {
        const endpoint = resolveChartEndpoint(element);
        const rendererName = element.dataset.chartRenderer || "line";
        const renderer = getChartRenderer(rendererName);
        if (!endpoint || typeof renderer !== "function") {
            return;
        }

        const requestStartedAtMs = beginChartRequest();
        fetch(endpoint, { headers: { Accept: "application/json" } })
            .then((response) => {
                if (!response.ok) {
                    throw new Error("HTTP " + String(response.status));
                }
                return response.json();
            })
            .then((payload) => {
                renderer(element, payload);
            })
            .catch(() => {
                element.innerHTML = '<div class="terminal-empty-state">Chart request failed.</div>';
            })
            .finally(() => {
                endChartRequest(requestStartedAtMs);
            });
    }

    function wireCorrelationHorizon(root) {
        const select = root.querySelector ? root.querySelector("#correlation-horizon-select") : null;
        if (!select || select.dataset.terminalHorizonBound === "true") {
            return;
        }
        select.dataset.terminalHorizonBound = "true";
        select.addEventListener("change", function () {
            const horizon = select.value;
            const container = document.getElementById("correlation-heatmaps");
            if (!container) {
                return;
            }
            container.querySelectorAll(".terminal-chart[data-chart-endpoint]").forEach((element) => {
                const current = element.dataset.chartEndpoint || "";
                let updated = current;
                try {
                    const absoluteUrl = new URL(current, window.location.origin);
                    absoluteUrl.searchParams.set("horizon", horizon);
                    updated = absoluteUrl.pathname + absoluteUrl.search;
                } catch (_) {
                    updated = current.includes("horizon=")
                        ? current.replace(/horizon=[^&]+/, "horizon=" + horizon)
                        : current + (current.includes("?") ? "&" : "?") + "horizon=" + horizon;
                }
                element.dataset.chartEndpoint = updated;
                element.innerHTML = "";
                renderChart(element);
            });
            const sidebarSelect = document.querySelector('#dashboard-filters [name="correlation_horizon"]');
            if (sidebarSelect) {
                sidebarSelect.value = horizon;
            }
        });
    }

    TerminalUI.renderChart = renderChart;
    TerminalUI.initCharts = function (root) {
        root.querySelectorAll(".terminal-chart[data-chart-endpoint]").forEach((element) => {
            renderChart(element);
        });
        wireCorrelationHorizon(root);
    };
})();
