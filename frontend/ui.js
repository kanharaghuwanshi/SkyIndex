/* =========================================================
   SKYINDEX — SHARED UI BEHAVIOUR
   Presentation-only helpers shared by all three pages:
   - responsive navigation menu
   - chart "information" popovers (accessible disclosure pattern)
   - chart loading / empty state helper
   - Chart.js presentation defaults (fonts, tooltip, grid)

   This file contains NO data access, NO calculations and NO
   filtering logic. It never touches Supabase or SkyIndexData.
========================================================= */

(() => {
    "use strict";

    const doc = document;
    const root = doc.documentElement;

    root.classList.add("js");

    const reducedMotion =
        window.matchMedia &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;


    /* =====================================================
       CHART.JS PRESENTATION DEFAULTS
       (colours, fonts, tooltip, grid — never datasets)
    ===================================================== */

    function applyChartTheme() {
        if (typeof window.Chart === "undefined") {
            return;
        }

        const defaults = window.Chart.defaults;

        defaults.font.family =
            'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif';
        defaults.font.size = 12;
        defaults.color = "#5f6f86";
        defaults.borderColor = "rgba(20, 40, 70, 0.08)";

        if (reducedMotion) {
            defaults.animation = false;
        } else {
            defaults.animation.duration = 350;
        }

        const legend = defaults.plugins.legend;
        legend.labels.usePointStyle = true;
        legend.labels.boxWidth = 8;
        legend.labels.boxHeight = 8;
        legend.labels.padding = 16;
        legend.position = "bottom";

        const tooltip = defaults.plugins.tooltip;
        tooltip.backgroundColor = "#0b2447";
        tooltip.titleColor = "#ffffff";
        tooltip.bodyColor = "#dbe5f3";
        tooltip.padding = 10;
        tooltip.cornerRadius = 6;
        tooltip.boxPadding = 4;
        tooltip.titleFont = { weight: "600", size: 12 };
        tooltip.bodyFont = { size: 12 };
    }

    applyChartTheme();


    /* =====================================================
       CHART STATE HELPER (loading / empty)
       Usage: SkyIndexUI.setChartState("routeChart", "empty")
       States: "ready" | "empty" | "loading"
    ===================================================== */

    function setChartState(canvasId, state, message) {
        const canvas = doc.getElementById(canvasId);
        const box = canvas ? canvas.closest(".chart-box") : null;

        if (!box) {
            return;
        }

        box.classList.toggle("is-empty", state === "empty");
        box.classList.toggle("is-loading", state === "loading");

        let note = box.querySelector(".chart-state");

        if (state === "ready") {
            if (note) {
                note.hidden = true;
            }
            return;
        }

        if (!note) {
            note = doc.createElement("div");
            note.className = "chart-state";
            note.setAttribute("role", "status");
            box.appendChild(note);
        }

        note.hidden = false;
        note.textContent =
            message ||
            (state === "loading"
                ? "Loading…"
                : "No observations for the current selection.");
    }


    /* =====================================================
       RESPONSIVE NAVIGATION
    ===================================================== */

    function initNavigation() {
        const toggle = doc.querySelector(".nav-toggle");
        const nav = doc.getElementById("siteNav");

        if (!toggle || !nav) {
            return;
        }

        function setOpen(open, returnFocus) {
            nav.classList.toggle("open", open);
            toggle.setAttribute("aria-expanded", String(open));
            toggle.setAttribute(
                "aria-label",
                open ? "Close navigation menu" : "Open navigation menu"
            );

            if (!open && returnFocus) {
                toggle.focus();
            }
        }

        toggle.addEventListener("click", () => {
            setOpen(!nav.classList.contains("open"), false);
        });

        nav.addEventListener("click", event => {
            if (event.target.closest("a, button")) {
                setOpen(false, false);
            }
        });

        doc.addEventListener("click", event => {
            if (
                nav.classList.contains("open") &&
                !nav.contains(event.target) &&
                !toggle.contains(event.target)
            ) {
                setOpen(false, false);
            }
        });

        doc.addEventListener("keydown", event => {
            if (event.key === "Escape" && nav.classList.contains("open")) {
                setOpen(false, true);
            }
        });

        window.matchMedia("(min-width: 901px)").addEventListener("change", event => {
            if (event.matches) {
                setOpen(false, false);
            }
        });
    }


    /* =====================================================
       CHART INFORMATION POPOVERS
       Markup:
         <span class="info">
           <button class="info-btn" aria-expanded="false" aria-controls="id">…</button>
           <div class="info-pop" id="id" hidden>…</div>
         </span>
       Non-modal disclosure: works with keyboard, touch and mouse,
       never requires hover, and does not sit over the chart canvas.
    ===================================================== */

    function placePopover(pop) {
        pop.style.left = "";

        const margin = 12;
        const viewport = doc.documentElement.clientWidth;
        const rect = pop.getBoundingClientRect();

        let shift = 0;

        if (rect.right > viewport - margin) {
            shift = viewport - margin - rect.right;
        }

        if (rect.left + shift < margin) {
            shift = margin - rect.left;
        }

        if (shift !== 0) {
            const current = parseFloat(getComputedStyle(pop).left) || 0;
            pop.style.left = `${current + shift}px`;
        }
    }

    function initInfoPopovers() {
        const buttons = [...doc.querySelectorAll(".info-btn")];

        if (!buttons.length) {
            return;
        }

        function panelFor(button) {
            return doc.getElementById(button.getAttribute("aria-controls"));
        }

        function close(button, returnFocus) {
            const pop = panelFor(button);

            button.setAttribute("aria-expanded", "false");

            if (pop) {
                pop.hidden = true;
                pop.style.left = "";
            }

            if (returnFocus) {
                button.focus();
            }
        }

        function closeAll(exceptButton) {
            buttons.forEach(button => {
                if (button !== exceptButton) {
                    close(button, false);
                }
            });
        }

        buttons.forEach(button => {
            button.addEventListener("click", event => {
                event.stopPropagation();

                const pop = panelFor(button);
                const willOpen = button.getAttribute("aria-expanded") !== "true";

                closeAll(button);

                if (!pop) {
                    return;
                }

                if (willOpen) {
                    button.setAttribute("aria-expanded", "true");
                    pop.hidden = false;
                    placePopover(pop);
                } else {
                    close(button, false);
                }
            });
        });

        doc.addEventListener("click", event => {
            if (!event.target.closest(".info")) {
                closeAll(null);
            }
        });

        doc.addEventListener("keydown", event => {
            if (event.key !== "Escape") {
                return;
            }

            const openButton = buttons.find(
                button => button.getAttribute("aria-expanded") === "true"
            );

            if (openButton) {
                close(openButton, true);
            }
        });

        window.addEventListener("resize", () => closeAll(null));
    }


    /* =====================================================
       INIT
    ===================================================== */

    function initLoadingStates() {
        doc.querySelectorAll(".chart-box.is-loading canvas[id]").forEach(canvas => {
            setChartState(canvas.id, "loading");
        });
    }

    function init() {
        initLoadingStates();
        initNavigation();
        initInfoPopovers();
    }

    if (doc.readyState === "loading") {
        doc.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }

    window.SkyIndexUI = Object.freeze({
        setChartState
    });
})();
