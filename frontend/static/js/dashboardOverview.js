'use strict';

/**
 * dashboardOverview.js — v3 (dynamic auto-route overview)
 *
 * Mendukung slot dinamis: ov_ts_line, ov_scatter, ov_pie, ov_bar,
 * ov_histogram, ov_boxplot — dengan toggle drop-down otomatis.
 */

var OverviewDashboard = (function () {
    var data     = null;
    var rendered = new Set();

    var PLOTLY_CFG = {
        responsive     : true,
        displayModeBar : false,
        displaylogo    : false,
        scrollZoom     : false,
    };

    // ── State management ─────────────────────────────────────────────────────
    var VIZ_STATE_KEY = 'ds_viz_state';

    function _saveVizState(category, chartType, colX, colY) {
        try {
            sessionStorage.setItem(VIZ_STATE_KEY, JSON.stringify({
                category  : category  || null,
                chartType : chartType || null,
                colX      : colX      || null,
                colY      : colY      || null,
                ts        : Date.now(),
            }));
        } catch (e) {}
    }

    function readVizState() {
        try {
            var raw = sessionStorage.getItem(VIZ_STATE_KEY);
            if (!raw) return null;
            var state = JSON.parse(raw);
            if (Date.now() - (state.ts || 0) > 5 * 60 * 1000) {
                sessionStorage.removeItem(VIZ_STATE_KEY);
                return null;
            }
            return state;
        } catch (e) {
            return null;
        }
    }

    function clearVizState() {
        try { sessionStorage.removeItem(VIZ_STATE_KEY); } catch (e) {}
    }

    // ── Layout patch ──────────────────────────────────────────────────────────
    function getLayoutPatch() {
        var dark = document.body.getAttribute('data-theme') === 'dark';
        return {
            paper_bgcolor : 'rgba(0,0,0,0)',
            plot_bgcolor  : 'rgba(0,0,0,0)',
            font          : {
                color  : dark ? '#c8d8f0' : '#2b3674',
                family : 'Inter, sans-serif',
                size   : 11,
            },
            margin    : { l: 44, r: 16, t: 38, b: 38 },
            hoverlabel: {
                bgcolor    : dark ? 'rgba(10,18,48,0.93)' : 'rgba(255,255,255,0.93)',
                bordercolor: dark ? 'rgba(100,160,235,0.45)' : 'rgba(0,0,0,0.12)',
                font       : { color: dark ? '#e8f4fc' : '#1F2937', size: 12 },
            },
        };
    }

    // ── Binary decode ──────────────────────────────────────────────────────────
    function _b64ToUint8(b64) {
        var bin = atob(b64);
        var u8  = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
        return u8;
    }

    function _decodeBinaryField(field) {
        if (!field || typeof field !== 'object' || !field.bdata) return field;
        var dtype = field.dtype || 'f8';
        var u8    = _b64ToUint8(field.bdata);
        var buf   = u8.buffer;
        var off   = u8.byteOffset;
        var len   = u8.byteLength;
        var arr;
        if      (dtype === 'f8') arr = new Float64Array(buf, off, len / 8);
        else if (dtype === 'f4') arr = new Float32Array(buf, off, len / 4);
        else if (dtype === 'i4') arr = new Int32Array  (buf, off, len / 4);
        else if (dtype === 'i2') arr = new Int16Array  (buf, off, len / 2);
        else if (dtype === 'u4') arr = new Uint32Array (buf, off, len / 4);
        else if (dtype === 'u1') arr = new Uint8Array  (buf, off, len);
        else                     arr = new Float64Array(buf, off, len / 8);
        return Array.from(arr);
    }

    function _decodeTrace(trace) {
        if (!trace || typeof trace !== 'object') return trace;
        var decoded = Object.assign({}, trace);
        ['x', 'y', 'z', 'values', 'labels', 'ids',
         'open', 'high', 'low', 'close', 'lat', 'lon'].forEach(function (f) {
            if (decoded[f] && typeof decoded[f] === 'object' && decoded[f].bdata) {
                decoded[f] = _decodeBinaryField(decoded[f]);
            }
        });
        if (decoded.marker && typeof decoded.marker === 'object') {
            decoded.marker = Object.assign({}, decoded.marker);
            ['size', 'color'].forEach(function(k) {
                if (decoded.marker[k] && typeof decoded.marker[k] === 'object' && decoded.marker[k].bdata) {
                    decoded.marker[k] = _decodeBinaryField(decoded.marker[k]);
                }
            });
        }
        if ((decoded.type === 'parcoords' || decoded.type === 'splom') &&
             Array.isArray(decoded.dimensions)) {
            decoded.dimensions = decoded.dimensions.map(function (dim) {
                if (!dim || typeof dim !== 'object') return dim;
                var d = Object.assign({}, dim);
                if (d.values && typeof d.values === 'object' && d.values.bdata) {
                    d.values = _decodeBinaryField(d.values);
                }
                return d;
            });
        }
        if (decoded.line && typeof decoded.line === 'object') {
            decoded.line = Object.assign({}, decoded.line);
            if (decoded.line.color && typeof decoded.line.color === 'object' && decoded.line.color.bdata) {
                decoded.line.color = _decodeBinaryField(decoded.line.color);
            }
        }
        return decoded;
    }

    function _decodeChartData(chartObj) {
        if (!chartObj || !Array.isArray(chartObj.data)) return chartObj;
        return Object.assign({}, chartObj, {
            data: chartObj.data.map(_decodeTrace),
        });
    }

    // ── Draw single slot ──────────────────────────────────────────────────────
    function drawSlot(slotId, chartJson, force) {
        if (!chartJson || typeof Plotly === 'undefined') {
            if (typeof Plotly === 'undefined' && typeof showToast === 'function') {
                showToast(typeof I18N !== 'undefined' ? I18N.t('ov_plotly_unavailable') : 'Plotly library is not available.', 'error');
            }
            return;
        }
        var el = document.getElementById(slotId);
        if (!el) return;

        if (!force && rendered.has(slotId)) {
            try { Plotly.Plots.resize(el); } catch (e) {}
            return;
        }

        var decoded = _decodeChartData(chartJson);
        var baseLayout = Object.assign({}, decoded.layout || {});
        // Strip fixed dimensions agar mengikuti container
        delete baseLayout.width;
        delete baseLayout.height;
        var layout  = Object.assign({}, baseLayout, getLayoutPatch(), {autosize: true});

        try { Plotly.purge(el); } catch (e) {}
        el.innerHTML = '';

        Plotly.react(el, decoded.data || [], layout, PLOTLY_CFG)
            .then(function () { rendered.add(slotId); })
            .catch(function (err) {
                console.error('[Overview] Plotly error on', slotId, ':', err);
                // Tampilkan pesan error di slot
                if (el) {
                    el.innerHTML = '<div style="padding:12px;color:var(--text-muted);font-size:13px;text-align:center;">' + (typeof I18N !== 'undefined' ? I18N.t('ov_viz_load_failed') : 'Failed to load visualization.') + '</div>';
                }
            });
    }

    function renderAll(force) {
        if (!data || !data.slots) return;
        Object.keys(data.slots).forEach(function (key) {
            var slot = data.slots[key];
            if (slot && slot.visible && slot.chart) {
                drawSlot(key, slot.chart, !!force);
            }
        });
    }

    // ── Toggle dropdowns ─────────────────────────────────────────────────────

    function bindToggles() {
        if (!data || !data.toggle_data) return;
        Object.keys(data.toggle_data).forEach(function (slotId) {
            var toggle = data.toggle_data[slotId];
            if (!toggle || !toggle.charts) return;
            var select = document.getElementById('toggle-' + slotId);
            if (!select) return;
            console.log('[Overview] bindToggles:', slotId, 'options:', toggle.options, 'has insights:', !!toggle.insights, 'insight keys:', toggle.insights ? Object.keys(toggle.insights) : 'N/A');
            select.addEventListener('change', function () {
                var col   = select.value;
                var chart = toggle.charts[col];
                var title = (toggle.titles || {})[col];
                console.log('[Overview] toggle change:', slotId, 'col:', col, 'has chart:', !!chart, 'has title:', !!title);
                if (chart) {
                    rendered.delete(slotId);
                    drawSlot(slotId, chart, true);
                    var titleEl = document.getElementById(slotId + '-title');
                    if (titleEl && title) titleEl.textContent = title;
                    var insightEl = document.getElementById(slotId + '-insight');
                    var slotInsights = (data.slots[slotId] || {}).all_insights || {};
                    var insights = (toggle.insights || slotInsights)[col];
                    console.log('[Overview] insight data:', slotId, 'col:', col, 'insights:', insights ? insights.length + ' items' : 'undefined', 'el:', !!insightEl, 'toggle_insights:', !!toggle.insights, 'slotInsights keys:', Object.keys(slotInsights));
                    if (insightEl) {
                        var label = typeof I18N !== 'undefined' ? I18N.t('ov_smart_insight') : 'Smart Insight';
                        var html = '<div class="ov-smart-insight-label"><i class="fas fa-brain"></i> ' + label + '</div>';
                        if (insights && insights.length > 0) {
                            insights.slice(0, 2).forEach(function (ins) {
                                html += '<div class="ov-smart-insight-item"><i class="fas ' + (ins.icon || 'fa-circle') + '"></i> ' + (ins.text || '') + '</div>';
                            });
                        } else {
                            var fallback = typeof I18N !== 'undefined' ? I18N.t('viz_dataset_incompatible') : 'No insights available.';
                            html += '<div class="ov-smart-insight-item"><i class="fas fa-brain"></i> ' + fallback + '</div>';
                        }
                        insightEl.innerHTML = html;
                    }
                }
            });
        });
    }

    // ── Click navigation ──────────────────────────────────────────────────────
    function goToVisualizations(tab, subTab) {
        if (tab === 'timeseries') {
            if (typeof switchTab === 'function') switchTab('timeseries');
            setTimeout(function () {
                if (typeof switchTsTab === 'function') switchTsTab(subTab || 'overview');
            }, 90);
            return;
        }
        if (typeof openVizCategory === 'function') {
            openVizCategory(subTab || 'numerical');
        } else if (typeof switchTab === 'function') {
            switchTab('visualizations');
        }
    }

    function bindVizNavigation() {
        document.querySelectorAll('.ov-chart-slot[data-viz-tab]').forEach(function (el) {
            el.addEventListener('click', function (e) {
                if (e.target.closest('.ov-toggle-wrap')) return;
                goToVisualizations(el.getAttribute('data-viz-tab'), el.getAttribute('data-viz-sub'));
            });
        });
    }

    function bindPreviewNavigation() {
        document.querySelectorAll('.ov-preview-card[data-sidebar], .ov-stats-card[data-sidebar]').forEach(function (el) {
            el.addEventListener('click', function (e) {
                if (e.target.closest('.ov-preview-table-wrap, .ov-stats-table-wrap')) return;
                var tab = el.getAttribute('data-sidebar');
                if (typeof switchTab === 'function') switchTab(tab);
            });
        });
    }

    // ── Public API ────────────────────────────────────────────────────────────

    function init(overviewPayload) {
        data = overviewPayload || null;
        if (!data) return;
        bindToggles();
        bindVizNavigation();
        bindPreviewNavigation();
        var overviewTab = document.getElementById('tab-overview');
        if (overviewTab && overviewTab.classList.contains('active-tab')) {
            setTimeout(function () {
                renderAll();
            }, 200);
        }
    }

    function onTabShow() {
        setTimeout(function () {
            bindVizNavigation();
            bindPreviewNavigation();
            renderAll();
        }, 120);
    }

    function onResize() {
        rendered.forEach(function (slotId) {
            var el = document.getElementById(slotId);
            if (el && el._fullLayout && typeof Plotly !== 'undefined') {
                try { Plotly.Plots.resize(el); } catch (e) {}
            }
        });
    }

    return {
        init              : init,
        onTabShow         : onTabShow,
        onResize          : onResize,
        renderAll         : renderAll,
        bindToggles       : bindToggles,
        bindVizNavigation : bindVizNavigation,
        goToVisualizations: goToVisualizations,
        readVizState      : readVizState,
        clearVizState     : clearVizState,
        saveVizState      : _saveVizState,
    };
})();