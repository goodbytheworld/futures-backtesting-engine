(function () {
    const TerminalUI = (window.TerminalUI = window.TerminalUI || {});
    let pendingChartRequests = 0;
    let loadingWordTimerId = null;
    let loadingEtaTimerId = null;
    let loadingWordIndex = 0;
    let loadingSessionStartedAtMs = 0;
    const recentRequestDurationsMs = [];
    const MAX_STORED_DURATIONS = 20;

    function resetEchartInstance(element) {
        const existing = echarts.getInstanceByDom(element);
        if (existing) {
            existing.dispose();
        }
    }

    function getLoadingOverlay() {
        return document.getElementById("terminal-loading-overlay");
    }

    function getLoadingConfig() {
        const overlay = getLoadingOverlay();
        if (!overlay) {
            return {
                words: ["Loading data", "Building correlations", "Syncing charts", "Computing metrics", "Finalizing view"],
                wordIntervalMs: 1100,
                etaPerRequestSeconds: 2.2,
            };
        }
        let words = [];
        try {
            words = JSON.parse(overlay.dataset.loadingWords || "[]");
        } catch (_) {
            words = [];
        }
        const cleanedWords = Array.isArray(words)
            ? words.filter((x) => typeof x === "string" && x.trim().length > 0)
            : [];
        const parsedInterval = Number(overlay.dataset.loadingWordIntervalMs || 1100);
        const parsedEta = Number(overlay.dataset.loadingEtaPerRequestSeconds || 2.2);
        return {
            words: cleanedWords.length > 0 ? cleanedWords : ["Loading data"],
            wordIntervalMs: Number.isFinite(parsedInterval) && parsedInterval > 150 ? parsedInterval : 1100,
            etaPerRequestSeconds: Number.isFinite(parsedEta) && parsedEta > 0 ? parsedEta : 2.2,
        };
    }

    function averageRequestDurationMs() {
        if (recentRequestDurationsMs.length === 0) {
            const cfg = getLoadingConfig();
            return cfg.etaPerRequestSeconds * 1000;
        }
        const sum = recentRequestDurationsMs.reduce((acc, value) => acc + value, 0);
        return sum / recentRequestDurationsMs.length;
    }

    function updateLoadingEtaText() {
        const etaElement = document.getElementById("terminal-loading-eta");
        if (!etaElement) {
            return;
        }
        if (pendingChartRequests <= 0) {
            etaElement.textContent = "ETA ~0.0s";
            return;
        }
        const elapsedMs = Math.max(0, Date.now() - loadingSessionStartedAtMs);
        const estimatedRemainingMs = Math.max(
            100,
            pendingChartRequests * averageRequestDurationMs() - elapsedMs,
        );
        etaElement.textContent = "ETA ~" + (estimatedRemainingMs / 1000).toFixed(1) + "s";
    }

    function rotateLoadingWord() {
        const wordElement = document.getElementById("terminal-loading-word");
        if (!wordElement) {
            return;
        }
        const cfg = getLoadingConfig();
        const words = cfg.words;
        if (words.length === 0) {
            return;
        }
        loadingWordIndex = (loadingWordIndex + 1) % words.length;
        wordElement.classList.add("is-fading");
        setTimeout(() => {
            wordElement.textContent = words[loadingWordIndex];
            wordElement.classList.remove("is-fading");
        }, 130);
    }

    function stopLoadingAnimationTimers() {
        if (loadingWordTimerId !== null) {
            clearInterval(loadingWordTimerId);
            loadingWordTimerId = null;
        }
        if (loadingEtaTimerId !== null) {
            clearInterval(loadingEtaTimerId);
            loadingEtaTimerId = null;
        }
    }

    function startLoadingAnimationTimers() {
        const cfg = getLoadingConfig();
        stopLoadingAnimationTimers();
        const wordElement = document.getElementById("terminal-loading-word");
        if (wordElement) {
            loadingWordIndex = 0;
            wordElement.textContent = cfg.words[loadingWordIndex] || "Loading data";
        }
        updateLoadingEtaText();
        loadingWordTimerId = window.setInterval(rotateLoadingWord, cfg.wordIntervalMs);
        loadingEtaTimerId = window.setInterval(updateLoadingEtaText, 180);
    }

    function setGlobalLoading(isLoading) {
        const overlay = document.getElementById("terminal-loading-overlay");
        if (!overlay) {
            return;
        }
        overlay.classList.toggle("is-active", isLoading);
        overlay.setAttribute("aria-hidden", isLoading ? "false" : "true");
    }

    function beginChartRequest() {
        const startedAtMs = Date.now();
        pendingChartRequests += 1;
        if (pendingChartRequests === 1) {
            loadingSessionStartedAtMs = startedAtMs;
            setGlobalLoading(true);
            startLoadingAnimationTimers();
        } else {
            updateLoadingEtaText();
        }
        return startedAtMs;
    }

    function endChartRequest(startedAtMs) {
        if (Number.isFinite(startedAtMs)) {
            const elapsedMs = Math.max(0, Date.now() - Number(startedAtMs));
            recentRequestDurationsMs.push(elapsedMs);
            if (recentRequestDurationsMs.length > MAX_STORED_DURATIONS) {
                recentRequestDurationsMs.splice(
                    0,
                    recentRequestDurationsMs.length - MAX_STORED_DURATIONS,
                );
            }
        }
        pendingChartRequests = Math.max(0, pendingChartRequests - 1);
        if (pendingChartRequests === 0) {
            stopLoadingAnimationTimers();
            setGlobalLoading(false);
            loadingSessionStartedAtMs = 0;
            const etaElement = document.getElementById("terminal-loading-eta");
            if (etaElement) {
                etaElement.textContent = "ETA ~0.0s";
            }
        } else {
            updateLoadingEtaText();
        }
    }

    function buildEchartsSeries(series) {
        return (series || []).map((item) => ({
            name: item.name,
            type: "line",
            showSymbol: false,
            smooth: false,
            lineStyle: { width: 2, color: item.color || "#FFFFFF" },
            itemStyle: { color: item.color || "#FFFFFF" },
            data: (item.points || []).map((point) => [point.time, point.value]),
        }));
    }

    function formatCompactAxisValue(value) {
        if (!Number.isFinite(value)) {
            return "";
        }
        const absoluteValue = Math.abs(value);
        if (absoluteValue >= 1000000000) {
            return (value / 1000000000).toFixed(absoluteValue >= 10000000000 ? 0 : 1).replace(/\.0$/, "") + "B";
        }
        if (absoluteValue >= 1000000) {
            return (value / 1000000).toFixed(absoluteValue >= 10000000 ? 0 : 1).replace(/\.0$/, "") + "M";
        }
        if (absoluteValue >= 1000) {
            return (value / 1000).toFixed(absoluteValue >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k";
        }
        if (Number.isInteger(value)) {
            return String(value);
        }
        return value.toFixed(Math.abs(value) >= 10 ? 0 : 1).replace(/\.0$/, "");
    }

    function formatFullAxisValue(value) {
        if (!Number.isFinite(value)) {
            return "n/a";
        }
        const absoluteValue = Math.abs(value);
        const fractionDigits = absoluteValue >= 1000 ? 0 : absoluteValue >= 10 ? 1 : 2;
        return new Intl.NumberFormat("en-US", {
            maximumFractionDigits: fractionDigits,
        }).format(value);
    }

    function formatTimeAxisLabel(value) {
        if (value == null || value === "") {
            return "";
        }
        const date = value instanceof Date ? value : new Date(value);
        if (!Number.isFinite(date.getTime())) {
            return "";
        }
        return date.toLocaleDateString(undefined, { month: "short", year: "numeric" });
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function computeNiceStep(rawStep) {
        if (!Number.isFinite(rawStep) || rawStep <= 0) {
            return 1;
        }
        const exponent = Math.floor(Math.log10(rawStep));
        const magnitude = Math.pow(10, exponent);
        const normalized = rawStep / magnitude;
        if (normalized <= 1) {
            return 1 * magnitude;
        }
        if (normalized <= 2) {
            return 2 * magnitude;
        }
        if (normalized <= 2.5) {
            return 2.5 * magnitude;
        }
        if (normalized <= 5) {
            return 5 * magnitude;
        }
        return 10 * magnitude;
    }

    function computeNiceAxisBounds(values, paddingRatio, targetTickCount) {
        const finiteValues = (values || []).filter((value) => Number.isFinite(value));
        if (finiteValues.length === 0) {
            return {
                min: null,
                max: null,
                interval: null,
                splitNumber: targetTickCount,
            };
        }
        const rawMin = Math.min(...finiteValues);
        const rawMax = Math.max(...finiteValues);
        const rawSpan = Math.abs(rawMax - rawMin);
        const referenceSpan = rawSpan > 0 ? rawSpan : Math.max(Math.abs(rawMax), Math.abs(rawMin), 1);
        const paddedMin = rawMin - referenceSpan * paddingRatio;
        const paddedMax = rawMax + referenceSpan * paddingRatio;
        const paddedSpan = Math.max(Math.abs(paddedMax - paddedMin), 1e-9);
        const resolvedTickCount = clamp(targetTickCount, 4, 6);
        const interval = computeNiceStep(paddedSpan / resolvedTickCount);
        const niceMin = Math.floor(paddedMin / interval) * interval;
        const niceMax = Math.ceil(paddedMax / interval) * interval;
        return {
            min: niceMin,
            max: niceMax,
            interval: interval,
            splitNumber: Math.max(1, Math.round((niceMax - niceMin) / interval)),
        };
    }

    function collectLineValues(series, thresholds) {
        const seriesValues = (series || [])
            .flatMap((item) => (item && Array.isArray(item.data) ? item.data : []))
            .map((point) => (Array.isArray(point) ? Number(point[1]) : Number.NaN))
            .filter((value) => Number.isFinite(value));
        const thresholdValues = (thresholds || [])
            .map((threshold) => Number(threshold && threshold.value))
            .filter((value) => Number.isFinite(value));
        return seriesValues.concat(thresholdValues);
    }

    function attachResize(element, instance, lightweight) {
        const MAX_DEFERRED_MEASURE_ATTEMPTS = 12;
        let deferredMeasureAttempts = 0;

        function measuredSize() {
            return { width: element.clientWidth, height: element.clientHeight };
        }

        function applySize() {
            const size = measuredSize();
            if (size.width < 16 || size.height < 16) {
                if (deferredMeasureAttempts < MAX_DEFERRED_MEASURE_ATTEMPTS) {
                    deferredMeasureAttempts += 1;
                    window.requestAnimationFrame(applySize);
                }
                return;
            }
            deferredMeasureAttempts = 0;
            if (lightweight) {
                instance.applyOptions({ width: size.width, height: size.height });
            } else {
                instance.resize({ width: size.width, height: size.height });
            }
        }

        const observer = new ResizeObserver(() => {
            applySize();
        });
        observer.observe(element);
        applySize();
    }

    TerminalUI.chartUtils = {
        attachResize: attachResize,
        beginChartRequest: beginChartRequest,
        buildEchartsSeries: buildEchartsSeries,
        clamp: clamp,
        collectLineValues: collectLineValues,
        computeNiceAxisBounds: computeNiceAxisBounds,
        endChartRequest: endChartRequest,
        formatCompactAxisValue: formatCompactAxisValue,
        formatFullAxisValue: formatFullAxisValue,
        formatTimeAxisLabel: formatTimeAxisLabel,
        resetEchartInstance: resetEchartInstance,
    };
})();
