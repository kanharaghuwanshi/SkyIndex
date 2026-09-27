(() => {
    "use strict";

    const api = window.SkyIndexData;
    const charts = {};

    let quotes = [];
    let apix = [];
    let routes = [];
    let leadHistory = [];

    function el(id) {
        return document.getElementById(id);
    }

    function number(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : null;
    }

    function median(values) {
        const sorted = (values || [])
            .map(number)
            .filter(value => value !== null)
            .sort((a, b) => a - b);

        if (!sorted.length) return null;

        const middle = Math.floor(sorted.length / 2);

        return sorted.length % 2
            ? sorted[middle]
            : (sorted[middle - 1] + sorted[middle]) / 2;
    }

    function percentChange(current, baseline) {
        const c = number(current);
        const b = number(baseline);

        if (c === null || b === null || b === 0) return null;

        return (c / b - 1) * 100;
    }

    function money(value) {
        const n = number(value);
        return n === null
            ? "--"
            : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
    }

    function percent(value, decimals = 2) {
        const n = number(value);
        return n === null
            ? "--"
            : `${n >= 0 ? "+" : ""}${n.toFixed(decimals)}%`;
    }

    function routeKey(row) {
        return `${row.origin}-${row.destination}`;
    }

    function destroy(name) {
        if (charts[name]) {
            charts[name].destroy();
            charts[name] = null;
        }
    }

    function setupFilters() {
        const dates = [...new Set(
            quotes.map(row => row.collection_date).filter(Boolean)
        )].sort();

        const routesSet = [...new Set(
            quotes.map(routeKey)
        )].sort();

        const airlines = [...new Set(
            quotes.map(row => row.airline).filter(Boolean)
        )].sort();

        const sources = [...new Set(
            quotes.map(row => row.source).filter(Boolean)
        )].sort();

        el("fromDate").value = dates[0] || "";
        el("toDate").value = dates.at(-1) || "";

        el("routeFilter").innerHTML =
            '<option value="">All routes</option>' +
            routesSet.map(route => `<option value="${route}">${route}</option>`).join("");

        el("airlineFilter").innerHTML =
            '<option value="">All airlines</option>' +
            airlines.map(airline => `<option value="${airline}">${airline}</option>`).join("");

        el("sourceFilter").innerHTML =
            '<option value="">All sources</option>' +
            sources.map(source => `<option value="${source}">${source}</option>`).join("");
    }

    function filteredQuotes() {
        const from = el("fromDate").value || "0000-01-01";
        const to = el("toDate").value || "9999-12-31";
        const route = el("routeFilter").value;
        const airline = el("airlineFilter").value;
        const source = el("sourceFilter").value;
        const lead = el("leadFilter").value;

        return quotes.filter(row =>
            row.collection_date >= from &&
            row.collection_date <= to &&
            (!route || routeKey(row) === route) &&
            (!airline || row.airline === airline) &&
            (!source || row.source === source) &&
            (!lead || Number(row.lead_time) === Number(lead))
        );
    }

    function groupedByDate(rows) {
        const map = new Map();

        rows.forEach(row => {
            if (!map.has(row.collection_date)) {
                map.set(row.collection_date, []);
            }
            map.get(row.collection_date).push(row);
        });

        return [...map.entries()].sort((a, b) =>
            a[0].localeCompare(b[0])
        );
    }

    function renderKpis(rows, latestDate) {
        const groups = groupedByDate(rows);

        const firstFare = groups.length
            ? median(groups[0][1].map(row => row.total_fare))
            : null;

        const latestFare = groups.length
            ? median(groups.at(-1)[1].map(row => row.total_fare))
            : null;

        const periodChange = percentChange(
            latestFare,
            firstFare
        );

        el("periodFareChange").textContent =
            percent(periodChange);

        el("periodFareNote").textContent =
            groups.length > 1
                ? `${groups[0][0]} → ${groups.at(-1)[0]}`
                : "Only one real collection date available";

        el("latestMedianFare").textContent =
            money(latestFare);

        const latestLead = leadHistory.filter(
            row => row.index_date === latestDate
        );

        const t1 = median(
            latestLead
                .filter(row => Number(row.lead_time) === 1)
                .map(row => row.representative_total_fare)
        );

        const t45 = median(
            latestLead
                .filter(row => Number(row.lead_time) === 45)
                .map(row => row.representative_total_fare)
        );

        el("leadSpread").textContent =
            percentChange(t45, t1) === null
                ? "--"
                : percent(percentChange(t45, t1));

        const fares = rows
            .map(row => number(row.total_fare))
            .filter(value => value !== null);

        const mean = fares.length
            ? fares.reduce((a, b) => a + b, 0) / fares.length
            : null;

        const variance = mean !== null && fares.length > 1
            ? fares.reduce(
                (sum, value) => sum + Math.pow(value - mean, 2),
                0
            ) / (fares.length - 1)
            : null;

        const cv = mean && variance !== null
            ? Math.sqrt(variance) / mean * 100
            : null;

        el("fareCv").textContent =
            cv === null ? "--" : `${cv.toFixed(1)}%`;
    }

    function drawFareTrend(rows) {
        destroy("fare");

        const groups = groupedByDate(rows);

        charts.fare = new Chart(
            el("fareTrendChart"),
            {
                type: "line",
                data: {
                    labels: groups.map(([date]) => date),
                    datasets: [{
                        label: "Median Total Fare",
                        data: groups.map(([, values]) =>
                            median(values.map(row => row.total_fare))
                        ),
                        borderColor: "#2874d8",
                        backgroundColor: "rgba(40,116,216,0.08)",
                        fill: true,
                        tension: 0.28,
                        pointRadius: 3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    }
                }
            }
        );
    }

    function drawApix() {
        destroy("apix");

        charts.apix = new Chart(
            el("apixTrendChart"),
            {
                type: "line",
                data: {
                    labels: apix.map(row => row.index_date),
                    datasets: [{
                        label: "APIx",
                        data: apix.map(row => number(row.apix)),
                        borderColor: "#0b1f3a",
                        backgroundColor: "rgba(11,31,58,0.06)",
                        fill: true,
                        tension: 0.26,
                        pointRadius: 3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            suggestedMin: 90
                        }
                    }
                }
            }
        );
    }

    function drawLeadCurve(latestDate, selectedRoute) {
        destroy("lead");

        const rows = leadHistory.filter(row =>
            row.index_date === latestDate &&
            (!selectedRoute || routeKey(row) === selectedRoute)
        );

        const grouped = new Map();

        rows.forEach(row => {
            if (!grouped.has(row.lead_time)) {
                grouped.set(row.lead_time, []);
            }
            grouped.get(row.lead_time).push(
                number(row.representative_total_fare)
            );
        });

        const ordered = [...grouped.entries()]
            .sort((a, b) => Number(a[0]) - Number(b[0]));

        charts.lead = new Chart(
            el("leadChart"),
            {
                type: "line",
                data: {
                    labels: ordered.map(([lead]) => `T+${lead}`),
                    datasets: [{
                        label: "Representative Fare",
                        data: ordered.map(([, values]) =>
                            median(values)
                        ),
                        borderColor: "#2874d8",
                        backgroundColor: "rgba(40,116,216,0.08)",
                        fill: true,
                        tension: 0.24
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false
                }
            }
        );

        return ordered;
    }

    function drawComponents(rows) {
        destroy("components");

        const groups = groupedByDate(rows);
        const labels = groups.map(([date]) => date);

        const component = field =>
            groups.map(([, values]) =>
                median(values.map(row => row[field]))
            );

        charts.components = new Chart(
            el("componentChart"),
            {
                type: "line",
                data: {
                    labels,
                    datasets: [
                        {
                            label: "Base Fare",
                            data: component("base_fare"),
                            borderColor: "#2874d8",
                            tension: 0.24,
                            pointRadius: 3
                        },
                        {
                            label: "Taxes",
                            data: component("taxes"),
                            borderColor: "#687f97",
                            tension: 0.24,
                            pointRadius: 3
                        },
                        {
                            label: "UDF",
                            data: component("udf"),
                            borderColor: "#9b7738",
                            tension: 0.24,
                            pointRadius: 3
                        },
                        {
                            label: "Fees",
                            data: component("fees"),
                            borderColor: "#a15b61",
                            tension: 0.24,
                            pointRadius: 3
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: "category"
                        }
                    }
                }
            }
        );
    }

    function drawAirlines(rows) {
        destroy("airlines");

        const grouped = new Map();

        rows.forEach(row => {
            if (!grouped.has(row.airline)) {
                grouped.set(row.airline, []);
            }
            grouped.get(row.airline).push(
                number(row.total_fare)
            );
        });

        const ordered = [...grouped.entries()]
            .map(([airline, values]) => ({
                airline,
                fare: median(values)
            }))
            .sort((a, b) => (b.fare ?? 0) - (a.fare ?? 0));

        charts.airlines = new Chart(
            el("airlineChart"),
            {
                type: "bar",
                data: {
                    labels: ordered.map(row => row.airline),
                    datasets: [{
                        label: "Median Fare",
                        data: ordered.map(row => row.fare),
                        backgroundColor: "#2874d8"
                    }]
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    }
                }
            }
        );
    }

    function renderRouteTable(latestDate, selectedRoute) {
        const rows = routes
            .filter(row =>
                row.index_date === latestDate &&
                (!selectedRoute || routeKey(row) === selectedRoute)
            )
            .sort((a, b) =>
                (number(b.route_index) ?? -Infinity) -
                (number(a.route_index) ?? -Infinity)
            );

        el("routeAnalysisBody").innerHTML =
            rows.map(row => `
                <tr>
                    <td>${routeKey(row)}</td>
                    <td>${money(row.representative_total_fare)}</td>
                    <td>${money(row.baseline_total_fare)}</td>
                    <td>${number(row.route_index) === null ? "--" : Number(row.route_index).toFixed(2)}</td>
                    <td>${percent(row.fare_change_pct)}</td>
                    <td>${percent(row.base_fare_change_pct)}</td>
                    <td>${percent(row.taxes_change_pct)}</td>
                    <td>${percent(row.fees_change_pct)}</td>
                    <td>${row.lead_time_coverage_pct == null ? "--" : `${Number(row.lead_time_coverage_pct).toFixed(0)}%`}</td>
                </tr>
            `).join("") ||
            `<tr><td colspan="9">No comparable route history for the selected date.</td></tr>`;
    }

    function renderInsights(rows, latestDate, leadCurve) {
        const groups = groupedByDate(rows);

        const firstMedian = groups.length
            ? median(groups[0][1].map(row => row.total_fare))
            : null;

        const lastMedian = groups.length
            ? median(groups.at(-1)[1].map(row => row.total_fare))
            : null;

        const t1 = leadCurve.find(([lead]) => Number(lead) === 1)?.[1];
        const t45 = leadCurve.find(([lead]) => Number(lead) === 45)?.[1];

        const latestApi = apix.find(
            row => row.index_date === latestDate
        );

        const signals = [
            [
                "Period movement",
                percent(percentChange(lastMedian, firstMedian)),
                "Median observed fare from first to last selected collection date."
            ],
            [
                "T+45 vs T+1",
                percent(
                    t1 && t45
                        ? percentChange(median(t45), median(t1))
                        : null
                ),
                "Latest selected collection date."
            ],
            [
                "Latest APIx",
                latestApi ? Number(latestApi.apix).toFixed(2) : "--",
                latestApi?.baseline_date
                    ? `Fixed baseline: ${latestApi.baseline_date}`
                    : "Baseline not available."
            ],
            [
                "Coverage",
                latestApi?.weight_coverage_pct == null
                    ? "--"
                    : `${Number(latestApi.weight_coverage_pct).toFixed(1)}%`,
                "Configured route weight represented in the latest APIx."
            ]
        ];

        el("analysisInsights").innerHTML =
            signals.map(signal => `
                <div class="analysis-insight">
                    <strong>${signal[0]}</strong>
                    <span>${signal[1]}<br>${signal[2]}</span>
                </div>
            `).join("");
    }

    async function render() {
        const rows = filteredQuotes();
        const latestDate = (
            [...new Set(rows.map(row => row.collection_date))]
        ).sort().at(-1) || null;

        const selectedRoute = el("routeFilter").value;

        renderKpis(rows, latestDate);
        drawFareTrend(rows);
        drawApix();
        const leadCurve = latestDate
            ? drawLeadCurve(latestDate, selectedRoute)
            : [];
        drawComponents(rows);
        drawAirlines(rows);
        renderRouteTable(latestDate, selectedRoute);
        renderInsights(rows, latestDate, leadCurve);

        const latestApi = apix.at(-1);

        el("analysisBaseline").textContent =
            `Baseline ${latestApi?.baseline_date || "--"}`;

        el("analysisCoverage").textContent =
            latestApi?.weight_coverage_pct == null
                ? "Coverage --"
                : `Coverage ${Number(latestApi.weight_coverage_pct).toFixed(1)}%`;
    }

    function bindFilters() {
        [
            "fromDate",
            "toDate",
            "routeFilter",
            "airlineFilter",
            "sourceFilter",
            "leadFilter"
        ].forEach(id => {
            el(id).addEventListener("change", render);
        });
    }

    async function boot() {
        try {
            [
                quotes,
                apix,
                routes,
                leadHistory
            ] = await Promise.all([
                api.getAllQuotes(),
                api.getApixHistory(),
                api.getRouteHistory(),
                api.getLeadTimeHistory()
            ]);

            setupFilters();
            bindFilters();
            await render();
        } catch (error) {
            console.error("Analysis page error:", error);
            document.querySelector(".analysis-page").insertAdjacentHTML(
                "beforeend",
                `<div class="analysis-note">Unable to load analysis data. Check Supabase read policies and browser console.</div>`
            );
        }
    }

    boot();
})();
