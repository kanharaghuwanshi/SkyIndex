/* =========================================================
   SKYINDEX — FRONTEND DATA ACCESS LAYER

   Purpose:
   - Keep Supabase/database concerns outside dashboard rendering code.
   - Keep the dashboard independent of any one airline or source.
   - Support direct-airline adapters and SerpApi/Google Flights rows
     through the common `airline` + `source` fields.
   - Page large tables instead of relying on one implicit row limit.

   Security:
   - Only the Supabase publishable/anon key belongs in browser code.
   - Never put the service-role key or SerpApi key here.
========================================================= */

(() => {
    "use strict";

    const SUPABASE_URL =
        "https://rbjhymvifzsbkncsbeqf.supabase.co";

    const SUPABASE_PUBLISHABLE_KEY =
        "sb_publishable_glritkOuyWNczQbDF90Ubw_vYEJFm4e";

    const TABLES = Object.freeze({
        QUOTES: "airfare_quotes",
        APIX: "apix_history",
        ROUTE_HISTORY: "apix_route_history",
        LEADTIME_HISTORY: "apix_leadtime_history"
    });

    const PAGE_SIZE = 1000;

    const QUOTE_COLUMNS = [
        "collection_date",
        "origin",
        "destination",
        "airline",
        "flight_number",
        "travel_date",
        "lead_time",
        "departure_time",
        "arrival_time",
        "duration_minutes",
        "stops",
        "fare_class",
        "base_fare",
        "taxes",
        "udf",
        "fees",
        "convenience_fee",
        "service_fee",
        "other_charges",
        "total_fare",
        "currency",
        "availability",
        "source",
        "quote_key",
        "breakdown_match"
    ].join(",");

    const { createClient } = window.supabase || {};

    if (!createClient) {
        throw new Error(
            "Supabase client library was not loaded before data-access.js."
        );
    }

    const db = createClient(
        SUPABASE_URL,
        SUPABASE_PUBLISHABLE_KEY
    );

    async function fetchPaged(tableName, options = {}) {
        const {
            select = "*",
            orderColumn = null,
            ascending = false,
            filters = [],
            pageSize = PAGE_SIZE,
            maxRows = Number.POSITIVE_INFINITY
        } = options;

        const rows = [];
        let offset = 0;

        while (rows.length < maxRows) {
            const remaining = maxRows - rows.length;
            const take = Math.min(pageSize, remaining);

            let query = db
                .from(tableName)
                .select(select);

            for (const filter of filters) {
                query = filter(query);
            }

            if (orderColumn) {
                query = query.order(
                    orderColumn,
                    { ascending }
                );
            }

            query = query.range(
                offset,
                offset + take - 1
            );

            const { data, error } = await query;

            if (error) {
                throw error;
            }

            const page = data || [];
            rows.push(...page);

            if (page.length < take) {
                break;
            }

            offset += page.length;
        }

        return rows;
    }

    async function getLatestCollectionDate() {
        const { data, error } = await db
            .from(TABLES.QUOTES)
            .select("collection_date")
            .not("collection_date", "is", null)
            .order("collection_date", { ascending: false })
            .limit(1);

        if (error) {
            throw error;
        }

        return data?.[0]?.collection_date || null;
    }

    async function getQuotesForCollectionDate(collectionDate) {
        if (!collectionDate) {
            return [];
        }

        return fetchPaged(TABLES.QUOTES, {
            select: QUOTE_COLUMNS,
            orderColumn: "collection_date",
            ascending: false,
            filters: [
                query => query.eq(
                    "collection_date",
                    collectionDate
                ),
                query => query.not(
                    "total_fare",
                    "is",
                    null
                )
            ]
        });
    }

    async function getLatestQuoteSnapshot() {
        const collectionDate =
            await getLatestCollectionDate();

        const rows =
            await getQuotesForCollectionDate(
                collectionDate
            );

        return {
            collectionDate,
            rows
        };
    }

    async function getApixHistory() {
        return fetchPaged(TABLES.APIX, {
            // Current apix_history table persists the real index series.
            // Period change is derived in script.js from adjacent dates.
            select: [
                "index_date",
                "apix"
            ].join(","),
            orderColumn: "index_date",
            ascending: true
        });
    }

    async function getRouteHistory(collectionDate = null) {
        const filters = [];

        if (collectionDate) {
            filters.push(
                query => query.eq(
                    "index_date",
                    collectionDate
                )
            );
        }

        return fetchPaged(TABLES.ROUTE_HISTORY, {
            select: "*",
            orderColumn: "index_date",
            ascending: false,
            filters
        });
    }

    async function getLeadTimeHistory(collectionDate = null) {
        const filters = [];

        if (collectionDate) {
            filters.push(
                query => query.eq(
                    "index_date",
                    collectionDate
                )
            );
        }

        return fetchPaged(TABLES.LEADTIME_HISTORY, {
            select: "*",
            orderColumn: "index_date",
            ascending: false,
            filters
        });
    }

    async function getDashboardSnapshot() {
        const {
            collectionDate,
            rows
        } = await getLatestQuoteSnapshot();

        const [
            apixHistory,
            routeHistory,
            leadTimeHistory
        ] = await Promise.all([
            getApixHistory(),
            getRouteHistory(collectionDate),
            getLeadTimeHistory(collectionDate)
        ]);

        return {
            latestCollectionDate: collectionDate,
            quotes: rows,
            apixHistory,
            routeHistory,
            leadTimeHistory
        };
    }

    window.SkyIndexData = Object.freeze({
        tables: TABLES,
        getLatestCollectionDate,
        getQuotesForCollectionDate,
        getLatestQuoteSnapshot,
        getApixHistory,
        getRouteHistory,
        getLeadTimeHistory,
        getDashboardSnapshot
    });
})();
