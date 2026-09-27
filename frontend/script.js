/* =========================================================
   SKYINDEX — INDIAN AIRFARE PRICE INTELLIGENCE
   Frontend dashboard script

   IMPORTANT:
   - Existing Supabase data source is preserved.
   - Existing collection_date field is used throughout the dashboard.
   - Existing backend/data collection logic is not called from
     the browser and is therefore not changed here.
========================================================= */


/* =========================================================
   DATA ACCESS
========================================================= */

const dataApi = window.SkyIndexData;

if (!dataApi) {
    throw new Error(
        "SkyIndexData is unavailable. Ensure data-access.js loads before script.js."
    );
}


/* =========================================================
   CHART INSTANCES
========================================================= */

let apixChart = null;
let apixSparkline = null;
let routeChart = null;
let leadTimeChart = null;
let airlineChart = null;
let fareDistributionChart = null;
let volatilityChart = null;


/* =========================================================
   FRONTEND STATE
========================================================= */

let allQuotes = [];
let filteredQuotes = [];
let apixHistoryData = [];
let routeHistoryData = [];
let leadTimeHistoryData = [];
let latestCollectionDate = null;

let currentPage = 1;
const ROWS_PER_PAGE = 15;

let selectedApixPeriod = "all";


/* =========================================================
   SAFE DOM HELPERS
========================================================= */

function el(id) {
    return document.getElementById(id);
}

function setText(id, value) {
    const node = el(id);
    if (node) node.textContent = value;
}

function safeNumber(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
}

function dateValue(value) {
    if (!value) return 0;

    const time = new Date(value).getTime();

    return Number.isFinite(time)
        ? time
        : 0;
}

function formatCurrency(value) {

    const n = safeNumber(value);

    if (n === null) {
        return "--";
    }

    return `₹${n.toLocaleString(
        "en-IN",
        {
            maximumFractionDigits: 0
        }
    )}`;
}

function median(values) {

    if (
        !Array.isArray(values) ||
        values.length === 0
    ) {
        return null;
    }

    const sorted =
        values
            .map(Number)
            .filter(Number.isFinite)
            .sort(
                (a, b) =>
                    a - b
            );

    if (!sorted.length) {
        return null;
    }

    const middle =
        Math.floor(
            sorted.length / 2
        );

    return sorted.length % 2 === 0
        ? (
            sorted[middle - 1] +
            sorted[middle]
        ) / 2
        : sorted[middle];
}

function getValidFares(data) {

    return (data || [])
        .map(
            row =>
                safeNumber(
                    row.total_fare
                )
        )
        .filter(
            value =>
                value !== null &&
                value > 0
        );
}

function routeKey(row) {

    return `${row.origin ?? ""}-${row.destination ?? ""}`;
}

function routeLabel(row) {

    return `${row.origin ?? "-"} → ${row.destination ?? "-"}`;
}

function percentChange(
    current,
    previous
) {

    const a =
        safeNumber(current);

    const b =
        safeNumber(previous);

    if (
        a === null ||
        b === null ||
        b === 0
    ) {
        return null;
    }

    return (
        (a - b) /
        b
    ) * 100;
}


/* =========================================================
   APIx HISTORY
========================================================= */

async function loadApixHistory() {

    try {

        const data = await dataApi.getApixHistory();

        apixHistoryData =
            (data || [])
                .map(
                    row => ({
                        index_date: row.index_date,
                        apix: safeNumber(row.apix),
                        previous_apix: safeNumber(row.previous_apix),
                        change_value: safeNumber(row.change_value),
                        change_pct: safeNumber(row.change_pct),
                        calculation_status: row.calculation_status || null
                    })
                )
                .filter(
                    row => row.apix !== null
                );

        const firstBaselineRow =
            apixHistoryData.find(
                row => row.baseline_date
            );

        setText(
            "baselineMeta",
            firstBaselineRow?.baseline_date
                ? `Fixed baseline: ${firstBaselineRow.baseline_date}`
                : "Fixed baseline: awaiting APIx history"
        );

        if (!apixHistoryData.length) {

            setText("apix", "--");
            setText("apixDate", "Awaiting real index history");
            setText("apixChange", "--");

            renderApixChart([]);
            renderApixSparkline([]);

            return [];

        }

        const latest =
            apixHistoryData[
                apixHistoryData.length - 1
            ];

        const previous =
            apixHistoryData.length > 1
                ? apixHistoryData[
                    apixHistoryData.length - 2
                ]
                : null;

        setText(
            "apix",
            Number(latest.apix).toFixed(2)
        );

        setText(
            "apixDate",
            `Index date: ${latest.index_date}`
        );

        updateApixChange(
            latest.apix,
            previous ? previous.apix : null
        );

        renderApixChart(
            getApixPeriodData()
        );

        renderApixSparkline(
            apixHistoryData
        );

        return apixHistoryData;

    } catch (error) {

        console.error(
            "APIx history error:",
            error
        );

        setText(
            "apixDate",
            "APIx history unavailable"
        );

        renderApixChart([]);
        renderApixSparkline([]);

        return [];

    }

}


function updateApixChange(
    current,
    previous
) {

    const node =
        el("apixChange");


    if (!node) {
        return;
    }


    const change =
        percentChange(
            current,
            previous
        );


    if (
        change === null
    ) {

        node.className =
            "change-badge neutral";

        node.textContent =
            "--";

        return;

    }


    const direction =
        change > 0
            ? "positive"
            : change < 0
                ? "negative"
                : "neutral";


    const arrow =
        change > 0
            ? "▲"
            : change < 0
                ? "▼"
                : "→";


    node.className =
        `change-badge ${direction}`;


    node.textContent =
        `${arrow} ${Math.abs(
            change
        ).toFixed(2)}%`;

}


function getApixPeriodData() {

    if (
        selectedApixPeriod === "all"
    ) {

        return apixHistoryData;

    }


    const days =
        Number(
            selectedApixPeriod
        );


    if (
        !Number.isFinite(days)
    ) {

        return apixHistoryData;

    }


    const latest =
        apixHistoryData.length
            ? dateValue(
                apixHistoryData[
                    apixHistoryData.length - 1
                ].index_date
            )
            : Date.now();


    const cutoff =
        latest -
        days *
        24 *
        60 *
        60 *
        1000;


    return apixHistoryData.filter(
        row =>
            dateValue(
                row.index_date
            ) >= cutoff
    );

}


function renderApixSparkline(
    data
) {

    const canvas =
        el("apixSparkline");


    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {

        return;

    }


    if (apixSparkline) {

        apixSparkline.destroy();

    }


    const values =
        (data || [])
            .map(
                row =>
                    safeNumber(
                        row.apix
                    )
            )
            .filter(
                value =>
                    value !== null
            );


    apixSparkline =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels:
                        values.map(
                            (_, i) =>
                                i + 1
                        ),

                    datasets: [

                        {

                            data: values,

                            borderColor:
                                "#2874d8",

                            backgroundColor:
                                "rgba(40,116,216,0.07)",

                            fill: true,

                            tension: 0.4,

                            pointRadius: 0,

                            borderWidth: 2

                        }

                    ]

                },

                options: {

                    responsive: true,

                    maintainAspectRatio: false,

                    plugins: {

                        legend: {
                            display: false
                        },

                        tooltip: {
                            enabled: false
                        }

                    },

                    scales: {

                        x: {
                            display: false
                        },

                        y: {
                            display: false
                        }

                    }

                }

            }
        );

}


function renderApixChart(
    data
) {

    const canvas =
        el("apixChart");


    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {

        return;

    }


    if (apixChart) {

        apixChart.destroy();

    }


    const labels =
        (data || [])
            .map(
                row =>
                    row.index_date
            );


    const values =
        (data || [])
            .map(
                row =>
                    safeNumber(
                        row.apix
                    )
            );


    apixChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels,

                    datasets: [

                        {

                            label:
                                "APIx",

                            data: values,

                            tension:
                                0.34,

                            borderWidth:
                                3,

                            pointRadius:
                                2.5,

                            pointHoverRadius:
                                6,

                            fill: true,

                            backgroundColor:
                                "rgba(40,116,216,0.09)",

                            borderColor:
                                "#2874d8",

                            pointBackgroundColor:
                                "#2874d8",

                            spanGaps:
                                true

                        }

                    ]

                },

                options: {

                    responsive: true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },

                    plugins: {

                        legend: {

                            display:
                                false

                        },

                        tooltip: {

                            backgroundColor:
                                "#101a2d",

                            padding:
                                11,

                            cornerRadius:
                                8,

                            displayColors:
                                false,

                            callbacks: {

                                title:
                                    contexts => {

                                        const index =
                                            contexts[
                                                0
                                            ]?.dataIndex ??
                                            0;

                                        return (
                                            labels[index] ??
                                            ""
                                        );

                                    },

                                label:
                                    context =>
                                        `APIx: ${Number(
                                            context.raw
                                        ).toFixed(2)}`

                            }

                        }

                    },

                    scales: {

                        x: {

                            grid: {

                                display:
                                    false

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                maxTicksLimit:
                                    9,

                                font: {

                                    size:
                                        10

                                }

                            }

                        },

                        y: {

                            beginAtZero:
                                false,

                            grid: {

                                color:
                                    "rgba(20,40,70,0.06)"

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                font: {

                                    size:
                                        10

                                }

                            }

                        }

                    }

                }

            }
        );

}


/* =========================================================
   AIRFARE OBSERVATIONS
========================================================= */

async function loadQuotes() {

    try {

        const snapshot =
            await dataApi.getLatestQuoteSnapshot();

        latestCollectionDate =
            snapshot.collectionDate;

        allQuotes =
            snapshot.rows || [];

        if (!allQuotes.length) {

            filteredQuotes = [];

            showTableError(
                "No real airfare observations found for the latest collection date."
            );

            updateDashboardAnalytics([]);

            return;

        }

        initializeFilters(
            allQuotes
        );

        applyFilters();

    } catch (error) {

        console.error(
            "Quote loading error:",
            error
        );

        allQuotes = [];
        filteredQuotes = [];

        showTableError(
            "Unable to load the latest airfare observations."
        );

        updateDashboardAnalytics([]);

    }

}


function showTableError(
    message
) {

    const table =
        el("fareTable");


    if (!table) {
        return;
    }


    table.innerHTML = `
        <tr>
            <td
                colspan="8"
                style="
                    text-align:center;
                    padding:40px;
                    color:#8995a5;
                "
            >
                ${message}
            </td>
        </tr>
    `;


    setText(
        "tableSummary",
        message
    );


    setText(
        "showingText",
        "No observations"
    );

}


/* =========================================================
   FILTER INITIALIZATION
========================================================= */

function initializeFilters(
    data
) {

    const routeFilter =
        el("routeFilter");


    const airlineFilter =
        el("airlineFilter");

    const sourceFilter =
        el("sourceFilter");


    if (
        !routeFilter ||
        !airlineFilter
    ) {

        return;

    }


    const currentRoute =
        routeFilter.value;


    const currentAirline =
        airlineFilter.value;


    const routes =
        [
            ...new Set(
                (data || [])
                    .map(
                        routeKey
                    )
                    .filter(
                        value =>
                            value !== "-"
                    )
            )
        ]
        .sort();


    routeFilter.innerHTML =
        `
            <option value="">
                All routes
            </option>
        `;


    routes.forEach(
        route => {

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                route;


            option.textContent =
                route;


            routeFilter.appendChild(
                option
            );

        }
    );


    if (
        routes.includes(
            currentRoute
        )
    ) {

        routeFilter.value =
            currentRoute;

    }


    const airlines =
        [
            ...new Set(
                (data || [])
                    .map(
                        row =>
                            row.airline
                    )
                    .filter(Boolean)
            )
        ]
        .sort();


    airlineFilter.innerHTML =
        `
            <option value="">
                All airlines
            </option>
        `;


    airlines.forEach(
        airline => {

            const option =
                document.createElement(
                    "option"
                );


            option.value =
                airline;


            option.textContent =
                airline;


            airlineFilter.appendChild(
                option
            );

        }
    );


    if (
        airlines.includes(
            currentAirline
        )
    ) {

        airlineFilter.value =
            currentAirline;

    }


    if (sourceFilter) {

        const currentSource =
            sourceFilter.value;

        const sources =
            [
                ...new Set(
                    (data || [])
                        .map(row => row.source)
                        .filter(Boolean)
                )
            ]
            .sort();

        sourceFilter.innerHTML = `
            <option value="">
                All sources
            </option>
        `;

        sources.forEach(
            source => {
                const option =
                    document.createElement(
                        "option"
                    );

                option.value =
                    source;

                option.textContent =
                    source;

                sourceFilter.appendChild(
                    option
                );
            }
        );

        if (sources.includes(currentSource)) {
            sourceFilter.value =
                currentSource;
        }

    }

}


/* =========================================================
   FILTERING
========================================================= */

function applyFilters() {

    const search =
        (
            el("searchInput")?.value ||
            ""
        )
        .toLowerCase()
        .trim();


    const route =
        el("routeFilter")?.value ||
        "";


    const airline =
        el("airlineFilter")?.value ||
        "";

    const source =
        el("sourceFilter")?.value ||
        "";


    const lead =
        el("leadFilter")?.value ||
        "";


    const date =
        el("dateFilter")?.value ||
        "";


    const minFareRaw =
        el("minFareFilter")?.value ||
        "";


    const maxFareRaw =
        el("maxFareFilter")?.value ||
        "";


    const minFare =
        minFareRaw === ""
            ? null
            : safeNumber(
                minFareRaw
            );


    const maxFare =
        maxFareRaw === ""
            ? null
            : safeNumber(
                maxFareRaw
            );


    filteredQuotes =
        (allQuotes || [])
            .filter(
                row => {

                    const currentRoute =
                        routeKey(
                            row
                        );


                    const fare =
                        safeNumber(
                            row.total_fare
                        );


                    /* SEARCH */

                    if (search) {

                        const searchable =
                            [
                                currentRoute,
                                row.origin,
                                row.destination,
                                row.airline,
                                row.source,
                                row.flight_number,
                                row.travel_date,
                                row.collection_date
                            ]
                            .filter(Boolean)
                            .join(" ")
                            .toLowerCase();


                        if (
                            !searchable.includes(
                                search
                            )
                        ) {

                            return false;

                        }

                    }


                    /* ROUTE */

                    if (
                        route &&
                        currentRoute !== route
                    ) {

                        return false;

                    }


                    /* AIRLINE */

                    if (
                        airline &&
                        row.airline !== airline
                    ) {

                        return false;

                    }


                    /* SOURCE */

                    if (
                        source &&
                        row.source !== source
                    ) {

                        return false;

                    }


                    /* LEAD TIME */

                    if (
                        lead &&
                        Number(
                            row.lead_time
                        ) !==
                        Number(
                            lead
                        )
                    ) {

                        return false;

                    }


                    /* TRAVEL DATE */

                    if (
                        date &&
                        row.travel_date !== date
                    ) {

                        return false;

                    }


                    /* MIN FARE */

                    if (
                        minFare !== null &&
                        (
                            fare === null ||
                            fare < minFare
                        )
                    ) {

                        return false;

                    }


                    /* MAX FARE */

                    if (
                        maxFare !== null &&
                        (
                            fare === null ||
                            fare > maxFare
                        )
                    ) {

                        return false;

                    }


                    return true;

                }
            );


    currentPage =
        1;


    updateFilterCount();

    renderFilterChips();

    updateDashboardAnalytics(
        filteredQuotes
    );

    updateTable();

}


function updateFilterCount() {

    let count =
        0;


    if (
        (
            el("searchInput")?.value ||
            ""
        ).trim()
    ) {

        count++;

    }


    if (
        el("routeFilter")?.value
    ) {

        count++;

    }


    if (
        el("airlineFilter")?.value
    ) {

        count++;

    }

    if (
        el("sourceFilter")?.value
    ) {

        count++;

    }


    if (
        el("leadFilter")?.value
    ) {

        count++;

    }


    if (
        el("dateFilter")?.value
    ) {

        count++;

    }


    if (
        (
            el("minFareFilter")?.value ||
            ""
        ).trim()
    ) {

        count++;

    }


    if (
        (
            el("maxFareFilter")?.value ||
            ""
        ).trim()
    ) {

        count++;

    }


    setText(
        "filterCount",
        `${count} filter${
            count === 1
                ? ""
                : "s"
        } active`
    );

}


function renderFilterChips() {

    const container =
        el("filterChips");


    if (!container) {
        return;
    }


    const chips =
        [];


    const search =
        (
            el("searchInput")?.value ||
            ""
        ).trim();


    const route =
        el("routeFilter")?.value ||
        "";


    const airline =
        el("airlineFilter")?.value ||
        "";

    const source =
        el("sourceFilter")?.value ||
        "";


    const lead =
        el("leadFilter")?.value ||
        "";


    const date =
        el("dateFilter")?.value ||
        "";


    const minFare =
        el("minFareFilter")?.value ||
        "";


    const maxFare =
        el("maxFareFilter")?.value ||
        "";


    if (search) {

        chips.push(
            {
                label:
                    `Search: ${search}`,

                action:
                    () =>
                        setValue(
                            "searchInput",
                            ""
                        )

            }
        );

    }


    if (route) {

        chips.push(
            {
                label:
                    route,

                action:
                    () =>
                        setValue(
                            "routeFilter",
                            ""
                        )

            }
        );

    }


    if (airline) {

        chips.push(
            {
                label:
                    airline,

                action:
                    () =>
                        setValue(
                            "airlineFilter",
                            ""
                        )

            }
        );

    }


    if (source) {

        chips.push(
            {
                label:
                    `Source: ${source}`,

                action:
                    () =>
                        setValue(
                            "sourceFilter",
                            ""
                        )

            }
        );

    }


    if (lead) {

        chips.push(
            {
                label:
                    `T+${lead}`,

                action:
                    () =>
                        setValue(
                            "leadFilter",
                            ""
                        )

            }
        );

    }


    if (date) {

        chips.push(
            {
                label:
                    `Travel: ${date}`,

                action:
                    () =>
                        setValue(
                            "dateFilter",
                            ""
                        )

            }
        );

    }


    if (minFare) {

        chips.push(
            {
                label:
                    `Min ${formatCurrency(
                        minFare
                    )}`,

                action:
                    () =>
                        setValue(
                            "minFareFilter",
                            ""
                        )

            }
        );

    }


    if (maxFare) {

        chips.push(
            {
                label:
                    `Max ${formatCurrency(
                        maxFare
                    )}`,

                action:
                    () =>
                        setValue(
                            "maxFareFilter",
                            ""
                        )

            }
        );

    }


    container.innerHTML =
        "";


    chips.forEach(
        chip => {

            const node =
                document.createElement(
                    "div"
                );


            node.className =
                "filter-chip";


            node.innerHTML = `
                <span>
                    ${escapeHtml(
                        chip.label
                    )}
                </span>

                <button
                    type="button"
                    aria-label="Remove filter"
                >
                    ×
                </button>
            `;


            node
                .querySelector(
                    "button"
                )
                .addEventListener(
                    "click",
                    () => {

                        chip.action();

                        applyFilters();

                    }
                );


            container.appendChild(
                node
            );

        }
    );

}


function setValue(
    id,
    value
) {

    const node =
        el(id);


    if (node) {

        node.value =
            value;

    }

}


function escapeHtml(
    value
) {

    return String(
        value
    )
    .replaceAll(
        "&",
        "&amp;"
    )
    .replaceAll(
        "<",
        "&lt;"
    )
    .replaceAll(
        ">",
        "&gt;"
    )
    .replaceAll(
        '"',
        "&quot;"
    )
    .replaceAll(
        "'",
        "&#039;"
    );

}


/* =========================================================
   ANALYTICS UPDATES
========================================================= */

function updateDashboardAnalytics(
    data
) {

    updateKPIs(
        data
    );


    updateMarketSnapshot(
        data
    );


    updateMarketMovers(
        data
    );


    updateCharts(
        data
    );


    renderRouteSnapshots(
        data
    );

}


/* =========================================================
   KPI UPDATES
========================================================= */

function updateKPIs(
    data
) {

    const fares =
        getValidFares(
            data
        );


    const routes =
        new Set(
            (data || [])
                .map(
                    routeKey
                )
                .filter(Boolean)
        );


    const airlines =
        new Set(
            (data || [])
                .map(
                    row =>
                        row.airline
                )
                .filter(Boolean)
        );


    const med =
        median(
            fares
        );


    const low =
        fares.length
            ? Math.min(
                ...fares
            )
            : null;


    const high =
        fares.length
            ? Math.max(
                ...fares
            )
            : null;


    setText(
        "medianFare",
        formatCurrency(
            med
        )
    );


    setText(
        "lowestFare",
        formatCurrency(
            low
        )
    );


    setText(
        "highestFare",
        formatCurrency(
            high
        )
    );


    setText(
        "routesCount",
        routes.size.toLocaleString(
            "en-IN"
        )
    );




    setText(
        "observationsCount",
        (data || [])
            .length
            .toLocaleString(
                "en-IN"
            )
    );


    setText(
        "medianFareSub",
        fares.length
            ? `${
                fares.length.toLocaleString(
                    "en-IN"
                )
            } valid fare observations`
            : "No valid fare observations"
    );

}


/* =========================================================
   MARKET SNAPSHOT
========================================================= */

function updateMarketSnapshot(
    data
) {

    const rows =
        data || [];


    const fares =
        getValidFares(
            rows
        );


    const routes =
        new Set(
            rows
                .map(
                    routeKey
                )
                .filter(Boolean)
        );


    const airlines =
        new Set(
            rows
                .map(
                    row =>
                        row.airline
                )
                .filter(Boolean)
        );


    const requiredFields =
        [

            "origin",

            "destination",

            "airline",

            "travel_date",

            "lead_time",

            "total_fare"

        ];


    let completeFieldCount =
        0;


    const totalFieldCount =
        rows.length *
        requiredFields.length;


    rows.forEach(
        row => {

            requiredFields.forEach(
                field => {

                    if (
                        row[field] !==
                            null &&
                        row[field] !==
                            undefined &&
                        row[field] !==
                            ""
                    ) {

                        completeFieldCount++;

                    }

                }
            );

        }
    );


    const completeness =
        totalFieldCount > 0
            ? (
                completeFieldCount /
                totalFieldCount
            ) * 100
            : 0;


    setText(
        "snapshotRoutes",
        routes.size.toLocaleString(
            "en-IN"
        )
    );


    setText(
        "snapshotAirlines",
        airlines.size.toLocaleString(
            "en-IN"
        )
    );


    setText(
        "snapshotValid",
        fares.length.toLocaleString(
            "en-IN"
        )
    );


    setText(
        "snapshotCompleteness",
        `${completeness.toFixed(1)}%`
    );


    const fill =
        el("qualityBarFill");


    if (fill) {

        fill.style.width =
            `${Math.max(
                0,
                Math.min(
                    100,
                    completeness
                )
            )}%`;

    }


    const status =
        el("dataStatus");


    if (status) {

        if (!rows.length) {

            status.className =
                "status-chip neutral";

            status.textContent =
                "No data";

        } else if (
            completeness >= 95
        ) {

            status.className =
                "status-chip positive";

            status.textContent =
                "High quality";

        } else if (
            completeness >= 85
        ) {

            status.className =
                "status-chip neutral";

            status.textContent =
                "Good quality";

        } else {

            status.className =
                "status-chip negative";

            status.textContent =
                "Needs review";

        }

    }


    const sources =
        new Set(
            rows
                .map(row => row.source)
                .filter(Boolean)
        );

    setText(
        "snapshotFootText",
        rows.length
            ? `${
                rows.length.toLocaleString(
                    "en-IN"
                )
            } rows · ${sources.size} source${sources.size === 1 ? "" : "s"}${
                latestCollectionDate
                    ? ` · collection ${latestCollectionDate}`
                    : ""
            }`
            : "No observations in the current filtered view"
    );

}


/* =========================================================
   MARKET MOVERS
========================================================= */

function updateMarketMovers(
    data
) {

    const grouped =
        groupRouteFares(
            data
        );


    const ranking =
        Object.entries(
            grouped
        )
        .map(
            ([route, fares]) => ({

                route,

                fare:
                    median(
                        fares
                    ),

                count:
                    fares.length

            })
        )
        .filter(
            item =>
                item.fare !== null
        )
        .sort(
            (a, b) =>
                b.fare - a.fare
        );


    const highNode =
        el("highestRouteMover");


    const lowNode =
        el("lowestRouteMover");


    if (
        !ranking.length
    ) {

        if (highNode) {

            highNode.className =
                "mover-row empty";

            highNode.textContent =
                "No route data";

        }


        if (lowNode) {

            lowNode.className =
                "mover-row empty";

            lowNode.textContent =
                "No route data";

        }


        return;

    }


    const highest =
        ranking[0];


    const lowest =
        ranking[
            ranking.length - 1
        ];


    if (highNode) {

        highNode.className =
            "mover-row";


        highNode.innerHTML = `
            <span class="mover-route">
                ${escapeHtml(
                    highest.route.replace(
                        "-",
                        " → "
                    )
                )}
            </span>

            <span class="mover-value">
                ${formatCurrency(
                    highest.fare
                )}
            </span>
        `;

    }


    if (lowNode) {

        lowNode.className =
            "mover-row";


        lowNode.innerHTML = `
            <span class="mover-route">
                ${escapeHtml(
                    lowest.route.replace(
                        "-",
                        " → "
                    )
                )}
            </span>

            <span class="mover-value">
                ${formatCurrency(
                    lowest.fare
                )}
            </span>
        `;

    }

}


function groupRouteFares(
    data
) {

    const grouped =
        {};


    (data || [])
        .forEach(
            row => {

                const fare =
                    safeNumber(
                        row.total_fare
                    );


                const key =
                    routeKey(
                        row
                    );


                if (
                    !key ||
                    fare === null ||
                    fare <= 0
                ) {

                    return;

                }


                if (
                    !grouped[key]
                ) {

                    grouped[key] =
                        [];

                }


                grouped[key].push(
                    fare
                );

            }
        );


    return grouped;

}


/* =========================================================
   ROUTE SNAPSHOTS
========================================================= */

function renderRouteSnapshots(
    data
) {

    const container =
        el("routeSnapshotGrid");


    if (!container) {
        return;
    }


    const grouped =
        groupRouteFares(
            data
        );


    const ranking =
        Object.entries(
            grouped
        )
        .map(
            ([route, fares]) => ({

                route,

                medianFare:
                    median(
                        fares
                    ),

                count:
                    fares.length

            })
        )
        .filter(
            row =>
                row.medianFare !== null
        )
        .sort(
            (a, b) =>
                b.medianFare -
                a.medianFare
        );


    container.innerHTML =
        "";


    if (
        !ranking.length
    ) {

        container.innerHTML = `
            <div
                class="route-snapshot-item"
                style="
                    cursor:default;
                    color:#8995a5;
                "
            >
                No route analytics available
                for the current filter set.
            </div>
        `;


        return;

    }


    ranking
        .slice(
            0,
            9
        )
        .forEach(
            item => {

                const node =
                    document.createElement(
                        "div"
                    );


                node.className =
                    "route-snapshot-item";


                node.innerHTML = `
                    <div class="route-snapshot-route">
                        ${escapeHtml(
                            item.route.replace(
                                "-",
                                " → "
                            )
                        )}
                    </div>

                    <div class="route-snapshot-value">
                        ${formatCurrency(
                            item.medianFare
                        )}
                    </div>

                    <div class="route-snapshot-meta">

                        <span>
                            ${
                                item.count.toLocaleString(
                                    "en-IN"
                                )
                            }
                            obs.
                        </span>

                        <span>
                            Open →
                        </span>

                    </div>
                `;


                node.addEventListener(
                    "click",
                    () =>
                        openRouteModal(
                            item.route
                        )
                );


                container.appendChild(
                    node
                );

            }
        );

}


/* =========================================================
   CHART UPDATES
========================================================= */

function updateCharts(
    data
) {

    renderRouteChart(
        data
    );


    renderLeadTimeChart(
        data
    );


    renderAirlineChart(
        data
    );


    renderFareDistributionChart(
        data
    );


    renderVolatilityChart(
        data
    );

}


/* =========================================================
   ROUTE CHART
========================================================= */

function renderRouteChart(
    data
) {

    const canvas =
        el("routeChart");


    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {

        return;

    }


    if (routeChart) {

        routeChart.destroy();

    }


    const grouped =
        groupRouteFares(
            data
        );


    const ranking =
        Object.entries(
            grouped
        )
        .map(
            ([route, fares]) => ({

                route,

                fare:
                    median(
                        fares
                    )

            })
        )
        .filter(
            item =>
                item.fare !== null
        )
        .sort(
            (a, b) =>
                b.fare - a.fare
        );


    routeChart =
        new Chart(
            canvas,
            {

                type: "bar",

                data: {

                    labels:
                        ranking.map(
                            item =>
                                item.route
                        ),

                    datasets: [

                        {

                            label:
                                "Median Fare (₹)",

                            data:
                                ranking.map(
                                    item =>
                                        item.fare
                                ),

                            backgroundColor:
                                "rgba(40,116,216,0.78)",

                            hoverBackgroundColor:
                                "#2874d8",

                            borderRadius:
                                6,

                            borderSkipped:
                                false

                        }

                    ]

                },

                options: {

                    indexAxis:
                        "y",

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },

                    plugins: {

                        legend: {

                            display:
                                false

                        },

                        tooltip: {

                            backgroundColor:
                                "#101a2d",

                            padding:
                                10,

                            cornerRadius:
                                8,

                            displayColors:
                                false,

                            callbacks: {

                                label:
                                    context =>
                                        `Median fare: ${formatCurrency(
                                            context.raw
                                        )}`

                            }

                        }

                    },

                    scales: {

                        x: {

                            beginAtZero:
                                true,

                            grid: {

                                color:
                                    "rgba(20,40,70,0.06)"

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                callback:
                                    value =>
                                        formatCurrency(
                                            value
                                        )

                            }

                        },

                        y: {

                            grid: {

                                display:
                                    false

                            },

                            ticks: {

                                color:
                                    "#56657a",

                                font: {

                                    size:
                                        10,

                                    weight:
                                        "600"

                                }

                            }

                        }

                    },

                    onClick:
                        (
                            _event,
                            elements
                        ) => {

                            const item =
                                elements[0];


                            if (!item) {
                                return;
                            }


                            const route =
                                ranking[
                                    item.index
                                ]?.route;


                            if (route) {

                                openRouteModal(
                                    route
                                );

                            }

                        }

                }

            }
        );

}


/* =========================================================
   LEAD TIME CHART
========================================================= */

function renderLeadTimeChart(
    data
) {

    const canvas =
        el("leadTimeChart");


    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {

        return;

    }


    if (leadTimeChart) {

        leadTimeChart.destroy();

    }


    const leadTimes =
        [
            1,
            7,
            15,
            30,
            45
        ];


    const values =
        leadTimes.map(
            lead => {

                const fares =
                    (data || [])
                        .filter(
                            row =>
                                Number(
                                    row.lead_time
                                ) === lead
                        )
                        .map(
                            row =>
                                safeNumber(
                                    row.total_fare
                                )
                        )
                        .filter(
                            value =>
                                value !== null &&
                                value > 0
                        );


                return median(
                    fares
                );

            }
        );


    leadTimeChart =
        new Chart(
            canvas,
            {

                type:
                    "line",

                data: {

                    labels:
                        leadTimes.map(
                            lead =>
                                `T+${lead}`
                        ),

                    datasets: [

                        {

                            label:
                                "Median Fare (₹)",

                            data:
                                values,

                            tension:
                                0.36,

                            borderWidth:
                                3,

                            pointRadius:
                                5,

                            pointHoverRadius:
                                7,

                            borderColor:
                                "#2874d8",

                            backgroundColor:
                                "rgba(40,116,216,0.08)",

                            pointBackgroundColor:
                                "#2874d8",

                            fill:
                                true,

                            spanGaps:
                                true

                        }

                    ]

                },

                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },

                    plugins: {

                        legend: {

                            display:
                                false

                        },

                        tooltip: {

                            backgroundColor:
                                "#101a2d",

                            padding:
                                10,

                            cornerRadius:
                                8,

                            displayColors:
                                false,

                            callbacks: {

                                label:
                                    context =>

                                        context.raw === null

                                            ? "No observations"

                                            : `Median fare: ${formatCurrency(
                                                context.raw
                                            )}`

                            }

                        }

                    },

                    scales: {

                        x: {

                            grid: {

                                display:
                                    false

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                font: {

                                    size:
                                        10,

                                    weight:
                                        "650"

                                }

                            }

                        },

                        y: {

                            beginAtZero:
                                false,

                            grid: {

                                color:
                                    "rgba(20,40,70,0.06)"

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                callback:
                                    value =>
                                        formatCurrency(
                                            value
                                        )

                            }

                        }

                    }

                }

            }
        );

}


/* =========================================================
   AIRLINE CHART
========================================================= */

function renderAirlineChart(
    data
) {

    const canvas =
        el("airlineChart");


    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {

        return;

    }


    if (airlineChart) {

        airlineChart.destroy();

    }


    const grouped =
        {};


    (data || [])
        .forEach(
            row => {

                const airline =
                    row.airline;


                const fare =
                    safeNumber(
                        row.total_fare
                    );


                if (
                    !airline ||
                    fare === null ||
                    fare <= 0
                ) {

                    return;

                }


                if (
                    !grouped[airline]
                ) {

                    grouped[airline] =
                        [];

                }


                grouped[airline].push(
                    fare
                );

            }
        );


    const ranking =
        Object.entries(
            grouped
        )
        .map(
            ([airline, fares]) => ({

                airline,

                fare:
                    median(
                        fares
                    ),

                count:
                    fares.length

            })
        )
        .filter(
            item =>
                item.fare !== null
        )
        .sort(
            (a, b) =>
                a.fare -
                b.fare
        );


    airlineChart =
        new Chart(
            canvas,
            {

                type:
                    "bar",

                data: {

                    labels:
                        ranking.map(
                            item =>
                                item.airline
                        ),

                    datasets: [

                        {

                            label:
                                "Median Fare (₹)",

                            data:
                                ranking.map(
                                    item =>
                                        item.fare
                                ),

                            backgroundColor:
                                "rgba(40,116,216,0.72)",

                            hoverBackgroundColor:
                                "#2874d8",

                            borderRadius:
                                6,

                            borderSkipped:
                                false

                        }

                    ]

                },

                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    plugins: {

                        legend: {

                            display:
                                false

                        },

                        tooltip: {

                            backgroundColor:
                                "#101a2d",

                            padding:
                                10,

                            cornerRadius:
                                8,

                            displayColors:
                                false,

                            callbacks: {

                                afterLabel:
                                    context => {

                                        const item =
                                            ranking[
                                                context.dataIndex
                                            ];


                                        return (
                                            `Observations: ${
                                                item?.count ??
                                                0
                                            }`
                                        );

                                    },

                                label:
                                    context =>
                                        `Median fare: ${formatCurrency(
                                            context.raw
                                        )}`

                            }

                        }

                    },

                    scales: {

                        x: {

                            grid: {

                                display:
                                    false

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                font: {

                                    size:
                                        10

                                }

                            }

                        },

                        y: {

                            beginAtZero:
                                true,

                            grid: {

                                color:
                                    "rgba(20,40,70,0.06)"

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                callback:
                                    value =>
                                        formatCurrency(
                                            value
                                        )

                            }

                        }

                    }

                }

            }
        );

}


/* =========================================================
   FARE DISTRIBUTION
========================================================= */

function renderFareDistributionChart(
    data
) {

    const canvas =
        el("fareDistributionChart");


    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {

        return;

    }


    if (
        fareDistributionChart
    ) {

        fareDistributionChart.destroy();

    }


    const fares =
        getValidFares(
            data
        );


    if (
        !fares.length
    ) {

        fareDistributionChart =
            null;

        return;

    }


    const min =
        Math.min(
            ...fares
        );


    const max =
        Math.max(
            ...fares
        );


    const binCount =
        Math.min(
            10,
            Math.max(
                5,
                Math.ceil(
                    Math.sqrt(
                        fares.length
                    )
                )
            )
        );


    const range =
        max - min;


    const step =
        range === 0
            ? 1
            : range /
                binCount;


    const bins =
        Array.from(
            {
                length:
                    binCount
            },
            (
                _,
                i
            ) => ({

                start:
                    min +
                    i *
                    step,

                end:
                    i ===
                    binCount - 1
                        ? max
                        : min +
                            (
                                i + 1
                            ) *
                            step,

                count:
                    0

            })
        );


    fares.forEach(
        fare => {

            const index =
                range === 0
                    ? 0
                    : Math.min(
                        binCount - 1,
                        Math.floor(
                            (
                                fare -
                                min
                            ) /
                            step
                        )
                    );


            bins[
                index
            ].count++;

        }
    );


    fareDistributionChart =
        new Chart(
            canvas,
            {

                type:
                    "bar",

                data: {

                    labels:
                        bins.map(
                            bin =>
                                `${
                                    formatShortCurrency(
                                        bin.start
                                    )
                                }–${
                                    formatShortCurrency(
                                        bin.end
                                    )
                                }`
                        ),

                    datasets: [

                        {

                            label:
                                "Observations",

                            data:
                                bins.map(
                                    bin =>
                                        bin.count
                                ),

                            backgroundColor:
                                "rgba(40,116,216,0.68)",

                            hoverBackgroundColor:
                                "#2874d8",

                            borderRadius:
                                5,

                            borderSkipped:
                                false

                        }

                    ]

                },

                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    plugins: {

                        legend: {

                            display:
                                false

                        },

                        tooltip: {

                            backgroundColor:
                                "#101a2d",

                            padding:
                                10,

                            cornerRadius:
                                8,

                            callbacks: {

                                label:
                                    context =>
                                        `${
                                            context.raw.toLocaleString(
                                                "en-IN"
                                            )
                                        } observations`

                            }

                        }

                    },

                    scales: {

                        x: {

                            grid: {

                                display:
                                    false

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                maxRotation:
                                    35,

                                minRotation:
                                    35

                            }

                        },

                        y: {

                            beginAtZero:
                                true,

                            grid: {

                                color:
                                    "rgba(20,40,70,0.06)"

                            },

                            ticks: {

                                color:
                                    "#8491a3"

                            }

                        }

                    }

                }

            }
        );

}


function formatShortCurrency(
    value
) {

    const n =
        safeNumber(
            value
        );


    if (n === null) {

        return "--";

    }


    if (n >= 1000) {

        return `₹${
            Math.round(
                n / 1000
            )
        }k`;

    }


    return `₹${
        Math.round(
            n
        )
    }`;

}


/* =========================================================
   ROUTE VOLATILITY
========================================================= */

function renderVolatilityChart(
    data
) {

    const canvas =
        el("volatilityChart");


    if (
        !canvas ||
        typeof Chart === "undefined"
    ) {

        return;

    }


    if (volatilityChart) {

        volatilityChart.destroy();

    }


    const grouped =
        groupRouteFares(
            data
        );


    const rows =
        Object.entries(
            grouped
        )
        .map(
            ([route, fares]) => {

                const med =
                    median(
                        fares
                    );


                const avg =
                    fares.length
                        ? fares.reduce(
                            (
                                sum,
                                value
                            ) =>
                                sum +
                                value,
                            0
                        ) /
                        fares.length
                        : null;


                if (
                    med === null ||
                    avg === null
                ) {

                    return null;

                }


                const variance =
                    fares.reduce(
                        (
                            sum,
                            value
                        ) =>
                            sum +
                            Math.pow(
                                value -
                                avg,
                                2
                            ),
                        0
                    ) /
                    fares.length;


                const std =
                    Math.sqrt(
                        variance
                    );


                const cv =
                    avg
                        ? (
                            std /
                            avg
                        ) *
                        100
                        : 0;


                return {

                    route,

                    volatility:
                        cv

                };

            }
        )
        .filter(Boolean)
        .sort(
            (a, b) =>
                b.volatility -
                a.volatility
        );


    volatilityChart =
        new Chart(
            canvas,
            {

                type:
                    "bar",

                data: {

                    labels:
                        rows.map(
                            row =>
                                row.route
                        ),

                    datasets: [

                        {

                            label:
                                "Coefficient of variation (%)",

                            data:
                                rows.map(
                                    row =>
                                        row.volatility
                                ),

                            backgroundColor:
                                "rgba(54,92,132,0.65)",

                            hoverBackgroundColor:
                                "#365c84",

                            borderRadius:
                                5,

                            borderSkipped:
                                false

                        }

                    ]

                },

                options: {

                    indexAxis:
                        "y",

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,

                    plugins: {

                        legend: {

                            display:
                                false

                        },

                        tooltip: {

                            backgroundColor:
                                "#101a2d",

                            padding:
                                10,

                            cornerRadius:
                                8,

                            displayColors:
                                false,

                            callbacks: {

                                label:
                                    context =>
                                        `Volatility: ${
                                            Number(
                                                context.raw
                                            ).toFixed(
                                                1
                                            )
                                        }%`

                            }

                        }

                    },

                    scales: {

                        x: {

                            beginAtZero:
                                true,

                            grid: {

                                color:
                                    "rgba(20,40,70,0.06)"

                            },

                            ticks: {

                                color:
                                    "#8491a3",

                                callback:
                                    value =>
                                        `${value}%`

                            }

                        },

                        y: {

                            grid: {

                                display:
                                    false

                            },

                            ticks: {

                                color:
                                    "#56657a",

                                font: {

                                    size:
                                        10

                                }

                            }

                        }

                    }

                }

            }
        );

}


/* =========================================================
   CLEAR CHARTS
========================================================= */

function clearCharts() {

    [

        routeChart,

        leadTimeChart,

        airlineChart,

        fareDistributionChart,

        volatilityChart

    ]
    .forEach(
        chart => {

            if (chart) {

                chart.destroy();

            }

        }
    );


    routeChart =
        null;


    leadTimeChart =
        null;


    airlineChart =
        null;


    fareDistributionChart =
        null;


    volatilityChart =
        null;

}


/* =========================================================
   TABLE SORTING
========================================================= */

function sortQuotes(
    data
) {

    const sort =
        el("sortSelect")?.value ||
        "latest";


    const sorted =
        [...(
            data || []
        )];


    switch (
        sort
    ) {


        case "fare-low":

            sorted.sort(
                (a, b) =>
                    Number(
                        a.total_fare ||
                        0
                    ) -
                    Number(
                        b.total_fare ||
                        0
                    )
            );

            break;


        case "fare-high":

            sorted.sort(
                (a, b) =>
                    Number(
                        b.total_fare ||
                        0
                    ) -
                    Number(
                        a.total_fare ||
                        0
                    )
            );

            break;


        case "lead-low":

            sorted.sort(
                (a, b) =>
                    Number(
                        a.lead_time ||
                        0
                    ) -
                    Number(
                        b.lead_time ||
                        0
                    )
            );

            break;


        case "lead-high":

            sorted.sort(
                (a, b) =>
                    Number(
                        b.lead_time ||
                        0
                    ) -
                    Number(
                        a.lead_time ||
                        0
                    )
            );

            break;


        case "route":

            sorted.sort(
                (a, b) =>
                    routeKey(
                        a
                    ).localeCompare(
                        routeKey(
                            b
                        )
                    )
            );

            break;


        case "airline":

            sorted.sort(
                (a, b) =>
                    String(
                        a.airline ||
                        ""
                    ).localeCompare(
                        String(
                            b.airline ||
                            ""
                        )
                    )
            );

            break;


        case "latest":

        default:

            sorted.sort(
                (a, b) =>
                    dateValue(
                        b.collection_date
                    ) -
                    dateValue(
                        a.collection_date
                    )
            );

            break;

    }


    return sorted;

}


/* =========================================================
   TABLE RENDERING
========================================================= */

function updateTable() {

    const table =
        el("fareTable");


    if (!table) {

        return;

    }


    const sorted =
        sortQuotes(
            filteredQuotes
        );


    const total =
        sorted.length;


    const totalPages =
        Math.max(
            1,
            Math.ceil(
                total /
                ROWS_PER_PAGE
            )
        );


    if (
        currentPage >
        totalPages
    ) {

        currentPage =
            totalPages;

    }


    const start =
        (
            currentPage -
            1
        ) *
        ROWS_PER_PAGE;


    const rows =
        sorted.slice(
            start,
            start +
            ROWS_PER_PAGE
        );


    table.innerHTML =
        "";


    if (
        !rows.length
    ) {

        table.innerHTML = `
            <tr>
                <td
                    colspan="8"
                    style="
                        text-align:center;
                        padding:40px;
                        color:#8995a5;
                    "
                >
                    No observations match
                    the selected filters.
                </td>
            </tr>
        `;

    }


    rows.forEach(
        row => {

            const tr =
                document.createElement(
                    "tr"
                );


            tr.style.cursor =
                "pointer";


            tr.innerHTML = `
                <td>
                    ${escapeHtml(
                        row.collection_date ??
                        "-"
                    )}
                </td>

                <td>
                    <span class="route-badge">
                        ${escapeHtml(
                            routeLabel(
                                row
                            )
                        )}
                    </span>
                </td>

                <td>
                    <span class="source-badge">
                        ${escapeHtml(
                            row.source ??
                            "-"
                        )}
                    </span>
                </td>

                <td>
                    <span class="airline-name">
                        ${escapeHtml(
                            row.airline ??
                            "-"
                        )}
                    </span>
                </td>

                <td>
                    ${escapeHtml(
                        row.flight_number ??
                        "-"
                    )}
                </td>

                <td>
                    ${escapeHtml(
                        row.travel_date ??
                        "-"
                    )}
                </td>

                <td>
                    <span class="lead-badge">
                        T+${escapeHtml(
                            row.lead_time ??
                            "-"
                        )}
                    </span>
                </td>

                <td>
                    ${formatCurrency(
                        row.total_fare
                    )}
                </td>
            `;


            tr.addEventListener(
                "click",
                () =>
                    openRouteModal(
                        routeKey(
                            row
                        )
                    )
            );


            table.appendChild(
                tr
            );

        }
    );


    if (
        total === 0
    ) {

        setText(
            "showingText",
            "No observations"
        );


        setText(
            "tableSummary",
            "No matching observations"
        );

    } else {

        setText(
            "showingText",
            `Showing ${
                start + 1
            }–${
                Math.min(
                    start +
                    ROWS_PER_PAGE,
                    total
                )
            } of ${
                total.toLocaleString(
                    "en-IN"
                )
            } observations`
        );


        setText(
            "tableSummary",
            `${
                total.toLocaleString(
                    "en-IN"
                )
            } matching observations`
        );

    }


    setText(
        "pageInfo",
        `Page ${
            currentPage
        } of ${
            totalPages
        }`
    );


    const prev =
        el("prevPage");


    const next =
        el("nextPage");


    if (prev) {

        prev.disabled =
            currentPage <=
            1;

    }


    if (next) {

        next.disabled =
            currentPage >=
            totalPages;

    }

}


/* =========================================================
   ROUTE DETAIL MODAL
========================================================= */

function openRouteModal(
    route
) {

    const data =
        allQuotes.filter(
            row =>
                routeKey(
                    row
                ) === route
        );


    if (
        !data.length
    ) {

        return;

    }


    const fares =
        getValidFares(
            data
        );


    setText(
        "routeModalTitle",
        route.replace(
            "-",
            " → "
        )
    );


    setText(
        "modalMedianFare",
        formatCurrency(
            median(
                fares
            )
        )
    );


    setText(
        "modalLowestFare",
        formatCurrency(
            fares.length
                ? Math.min(
                    ...fares
                )
                : null
        )
    );


    setText(
        "modalHighestFare",
        formatCurrency(
            fares.length
                ? Math.max(
                    ...fares
                )
                : null
        )
    );


    setText(
        "modalObservations",
        data.length.toLocaleString(
            "en-IN"
        )
    );


    const leadGrid =
        el("modalLeadGrid");


    if (leadGrid) {

        leadGrid.innerHTML =
            "";


        [

            1,
            7,
            15,
            30,
            45

        ]
        .forEach(
            lead => {

                const values =
                    data
                        .filter(
                            row =>
                                Number(
                                    row.lead_time
                                ) === lead
                        )
                        .map(
                            row =>
                                safeNumber(
                                    row.total_fare
                                )
                        )
                        .filter(
                            value =>
                                value !== null &&
                                value > 0
                        );


                const node =
                    document.createElement(
                        "div"
                    );


                node.className =
                    "modal-lead";


                node.innerHTML = `
                    <span>
                        T+${lead}
                    </span>

                    <strong>
                        ${formatCurrency(
                            median(
                                values
                            )
                        )}
                    </strong>
                `;


                leadGrid.appendChild(
                    node
                );

            }
        );

    }


    const airlineList =
        el("modalAirlineList");


    if (airlineList) {

        const grouped =
            {};


        data.forEach(
            row => {

                const name =
                    row.airline;


                const fare =
                    safeNumber(
                        row.total_fare
                    );


                if (
                    !name ||
                    fare === null ||
                    fare <= 0
                ) {

                    return;

                }


                if (
                    !grouped[name]
                ) {

                    grouped[name] =
                        [];

                }


                grouped[name].push(
                    fare
                );

            }
        );


        const ranked =
            Object.entries(
                grouped
            )
            .map(
                ([airline, values]) => ({

                    airline,

                    fare:
                        median(
                            values
                        ),

                    count:
                        values.length

                })
            )
            .filter(
                row =>
                    row.fare !== null
            )
            .sort(
                (a, b) =>
                    a.fare -
                    b.fare
            );


        airlineList.innerHTML =
            ranked.length

                ? ranked
                    .map(
                        item => `
                            <div class="modal-list-row">

                                <strong>
                                    ${escapeHtml(
                                        item.airline
                                    )}
                                </strong>

                                <span>
                                    ${formatCurrency(
                                        item.fare
                                    )}
                                    ·
                                    ${item.count}
                                    obs.
                                </span>

                            </div>
                        `
                    )
                    .join("")

                : `
                    <div class="modal-list-row">

                        <strong>
                            No airline data
                        </strong>

                        <span>
                            --
                        </span>

                    </div>
                `;

    }


    openModal(
        "routeModal"
    );

}


/* =========================================================
   MODAL HELPERS
========================================================= */

function openModal(
    id
) {

    const node =
        el(id);


    if (!node) {
        return;
    }


    node.classList.add(
        "open"
    );


    node.setAttribute(
        "aria-hidden",
        "false"
    );


    document.body.style.overflow =
        "hidden";

}


function closeModal(
    id
) {

    const node =
        el(id);


    if (!node) {
        return;
    }


    node.classList.remove(
        "open"
    );


    node.setAttribute(
        "aria-hidden",
        "true"
    );


    document.body.style.overflow =
        "";

}


/* =========================================================
   MODAL EVENTS
========================================================= */

function setupModalEvents() {

    document
        .querySelectorAll(
            "[data-close-modal]"
        )
        .forEach(
            button => {

                button.addEventListener(
                    "click",
                    () =>
                        closeModal(
                            button.getAttribute(
                                "data-close-modal"
                            )
                        )
                );

            }
        );


    document
        .querySelectorAll(
            ".modal-backdrop"
        )
        .forEach(
            backdrop => {

                backdrop.addEventListener(
                    "click",
                    event => {

                        if (
                            event.target ===
                            backdrop
                        ) {

                            closeModal(
                                backdrop.id
                            );

                        }

                    }
                );

            }
        );


    document.addEventListener(
        "keydown",
        event => {

            if (
                event.key !==
                "Escape"
            ) {

                return;

            }


            document
                .querySelectorAll(
                    ".modal-backdrop.open"
                )
                .forEach(
                    node =>
                        closeModal(
                            node.id
                        )
                );

        }
    );

}


/* =========================================================
   APIx PERIOD BUTTONS
========================================================= */

function setupPeriodButtons() {

    document
        .querySelectorAll(
            ".period-button"
        )
        .forEach(
            button => {

                button.addEventListener(
                    "click",
                    () => {

                        document
                            .querySelectorAll(
                                ".period-button"
                            )
                            .forEach(
                                node =>
                                    node.classList.remove(
                                        "active"
                                    )
                            );


                        button.classList.add(
                            "active"
                        );


                        selectedApixPeriod =
                            button.dataset.period ||
                            "all";


                        renderApixChart(
                            getApixPeriodData()
                        );

                    }
                );

            }
        );

}


/* =========================================================
   RESET FILTERS
========================================================= */

function resetFilters() {

    setValue(
        "searchInput",
        ""
    );


    setValue(
        "routeFilter",
        ""
    );


    setValue(
        "airlineFilter",
        ""
    );

    setValue(
        "sourceFilter",
        ""
    );


    setValue(
        "leadFilter",
        ""
    );


    setValue(
        "dateFilter",
        ""
    );


    setValue(
        "minFareFilter",
        ""
    );


    setValue(
        "maxFareFilter",
        ""
    );


    setValue(
        "sortSelect",
        "latest"
    );


    currentPage =
        1;


    applyFilters();

}


/* =========================================================
   DASHBOARD EVENTS
========================================================= */

function setupDashboardEvents() {

    const filterInputs =
        [

            [
                "searchInput",
                "input"
            ],

            [
                "routeFilter",
                "change"
            ],

            [
                "airlineFilter",
                "change"
            ],

            [
                "sourceFilter",
                "change"
            ],

            [
                "leadFilter",
                "change"
            ],

            [
                "dateFilter",
                "change"
            ],

            [
                "minFareFilter",
                "input"
            ],

            [
                "maxFareFilter",
                "input"
            ]

        ];


    filterInputs.forEach(
        (
            [
                id,
                eventName
            ]
        ) => {

            const node =
                el(id);


            if (node) {

                node.addEventListener(
                    eventName,
                    applyFilters
                );

            }

        }
    );


    const sort =
        el("sortSelect");


    if (sort) {

        sort.addEventListener(
            "change",
            updateTable
        );

    }


    const reset =
        el("resetFilters");


    if (reset) {

        reset.addEventListener(
            "click",
            resetFilters
        );

    }


    const prev =
        el("prevPage");


    if (prev) {

        prev.addEventListener(
            "click",
            () => {

                if (
                    currentPage >
                    1
                ) {

                    currentPage--;

                    updateTable();

                }

            }
        );

    }


    const next =
        el("nextPage");


    if (next) {

        next.addEventListener(
            "click",
            () => {

                const totalPages =
                    Math.max(
                        1,
                        Math.ceil(
                            filteredQuotes.length /
                            ROWS_PER_PAGE
                        )
                    );


                if (
                    currentPage <
                    totalPages
                ) {

                    currentPage++;

                    updateTable();

                }

            }
        );

    }


    const methodologyTop =
        el(
            "methodologyButton"
        );


    const methodologyBottom =
        el(
            "methodologyButtonBottom"
        );


    if (methodologyTop) {

        methodologyTop.addEventListener(
            "click",
            () =>
                openModal(
                    "methodologyModal"
                )
        );

    }


    if (methodologyBottom) {

        methodologyBottom.addEventListener(
            "click",
            () =>
                openModal(
                    "methodologyModal"
                )
        );

    }


    setupPeriodButtons();

    setupModalEvents();

}


/* =========================================================
   REFRESH DASHBOARD
========================================================= */

async function refreshDashboard() {

    try {

        const [
            ,
            ,
            analytics
        ] = await Promise.all([
            loadApixHistory(),
            loadQuotes(),
            dataApi.getDashboardSnapshot()
        ]);

        latestCollectionDate =
            analytics.latestCollectionDate ||
            latestCollectionDate;

        routeHistoryData =
            analytics.routeHistory || [];

        leadTimeHistoryData =
            analytics.leadTimeHistory || [];


    } catch (error) {

        console.error(
            "Dashboard refresh error:",
            error
        );

    }


    setText(
        "lastUpdated",
        `Last updated: ${
            new Date().toLocaleString(
                "en-IN"
            )
        }`
    );

}


/* =========================================================
   INITIALIZE
========================================================= */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        setupDashboardEvents();

        refreshDashboard();

    }
);


/* =========================================================
   AUTO REFRESH
========================================================= */

setInterval(
    refreshDashboard,
    60 * 1000
);