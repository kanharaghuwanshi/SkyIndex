(() => {
    "use strict";

    const api = window.SkyIndexData;
    let rows = [];
    let apix = [];

    function el(id) {
        return document.getElementById(id);
    }

    function number(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : null;
    }

    function money(value) {
        const n = number(value);
        return n === null
            ? "--"
            : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
    }

    function esc(value) {
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function routeKey(row) {
        return `${row.origin}-${row.destination}`;
    }

    function optionList(values, placeholder) {
        return `<option value="">${placeholder}</option>` +
            values.map(value =>
                `<option value="${esc(value)}">${esc(value)}</option>`
            ).join("");
    }

    function setupFilters() {
        const dates = [...new Set(
            rows.map(row => row.collection_date).filter(Boolean)
        )].sort();

        const routes = [...new Set(
            rows.map(routeKey)
        )].sort();

        const airlines = [...new Set(
            rows.map(row => row.airline).filter(Boolean)
        )].sort();

        const sources = [...new Set(
            rows.map(row => row.source).filter(Boolean)
        )].sort();

        const fareCodes = [...new Set(
            rows.map(row => row.fare_code).filter(Boolean)
        )].sort();

        el("collectionDate").value = dates.at(-1) || "";
        el("routeFilter").innerHTML = optionList(routes, "All routes");
        el("airlineFilter").innerHTML = optionList(airlines, "All airlines");
        el("sourceFilter").innerHTML = optionList(sources, "All sources");
        el("fareFilter").innerHTML = optionList(fareCodes, "All fare codes");

        el("explorerBaseline").textContent =
            apix.at(-1)?.baseline_date
                ? `Baseline ${apix.at(-1).baseline_date}`
                : "Baseline --";
    }

    function filtered() {
        const date = el("collectionDate").value;
        const route = el("routeFilter").value;
        const airline = el("airlineFilter").value;
        const source = el("sourceFilter").value;
        const lead = el("leadFilter").value;
        const fare = el("fareFilter").value;

        return rows.filter(row =>
            (!date || row.collection_date === date) &&
            (!route || routeKey(row) === route) &&
            (!airline || row.airline === airline) &&
            (!source || row.source === source) &&
            (!lead || Number(row.lead_time) === Number(lead)) &&
            (!fare || row.fare_code === fare)
        );
    }

    function render() {
        const data = filtered();

        el("rowCount").textContent =
            `${data.length.toLocaleString("en-IN")} rows`;

        el("explorerBody").innerHTML =
            data.map(row => `
                <tr>
                    <td>${esc(row.collection_date || "--")}</td>
                    <td>${esc(routeKey(row))}</td>
                    <td>${esc(row.airline || "--")}</td>
                    <td>${esc(row.source || "--")}</td>
                    <td class="mono">${esc(row.flight_number || "--")}</td>
                    <td>T+${esc(row.lead_time ?? "--")}</td>
                    <td>${esc(row.fare_code || "--")}</td>
                    <td class="num">${money(row.base_fare)}</td>
                    <td class="num">${money(row.taxes)}</td>
                    <td class="num">${money(row.udf)}</td>
                    <td class="num">${money(row.fees)}</td>
                    <td class="num">${money(row.other_charges)}</td>
                    <td class="num strong">${money(row.total_fare)}</td>
                    <td class="ctr">${row.breakdown_match === true ? "✓" : "--"}</td>
                </tr>
            `).join("") ||
            `<tr><td colspan="14" class="empty-cell">No matching observations for the selected filters.</td></tr>`;
    }

    async function boot() {
        try {
            [
                rows,
                apix
            ] = await Promise.all([
                api.getAllQuotes(),
                api.getApixHistory()
            ]);

            setupFilters();

            [
                "collectionDate",
                "routeFilter",
                "airlineFilter",
                "sourceFilter",
                "leadFilter",
                "fareFilter"
            ].forEach(id => {
                el(id).addEventListener("change", render);
            });

            render();
        } catch (error) {
            console.error("Explorer page error:", error);
            el("explorerBody").innerHTML =
                `<tr><td colspan="14" class="empty-cell">Unable to load observations. Check Supabase read policies and browser console.</td></tr>`;
        }
    }

    boot();
})();
