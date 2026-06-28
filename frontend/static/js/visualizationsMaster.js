'use strict';

/**
 * visualizationsMaster.js — v2 (with state management)
 *
 * Perubahan:
 *  - onTabShow() membaca sessionStorage (ditulis oleh dashboardOverview.js)
 *    untuk langsung membuka category + chartType + col yang sesuai.
 *  - openCategory(cat, chartType, colX, colY) menerima col opsional.
 *  - Dropdown chart type (bukan tombol next/prev).
 *  - Checkbox dropdown untuk compare category.
 */

var VizMaster = (function () {

    var meta  = {};
    var state = {
        category   : 'numerical',
        chartType  : null,
        chartIndex : 0,
        colX       : null,
        colY       : null,
        colZ       : null,
        loading    : false,
    };

    var _activeController = null;
    var _pendingOpen      = false;

    var CHART_TYPES = {
        numerical   : ['histogram', 'boxplot', 'density', 'qq', 'violin'],
        categorical : ['bar', 'pie', 'count', 'pareto'],
        bivariate   : ['scatter', 'heatmap', 'scatter_matrix', 'regression_plot', 'bubble_chart'],
        catnum      : ['box_cat_num', 'violin_cat_num', 'grouped_bar', 'strip_plot'],
        compare     : ['violin_compare', 'grouped_bar_compare', 'parallel_coords'],
        heatmap_all : ['heatmap_all'],
    };

    function getChartLabels() {
        return {
            histogram           : I18N.t('viz_histogram'),
            boxplot             : I18N.t('viz_boxplot'),
            density             : I18N.t('viz_kde'),
            qq                  : I18N.t('viz_qq'),
            violin              : I18N.t('viz_violin'),
            bar                 : I18N.t('viz_bar'),
            pie                 : I18N.t('viz_pie'),
            count               : I18N.t('viz_countplot'),
            pareto              : I18N.t('viz_pareto'),
            scatter             : I18N.t('viz_scatter'),
            heatmap             : I18N.t('viz_heatmap'),
            scatter_matrix      : I18N.t('viz_pairplot'),
            regression_plot     : I18N.t('viz_regression_plot'),
            bubble_chart        : I18N.t('viz_bubble_chart'),
            box_cat_num         : I18N.t('viz_box_cat_num'),
            violin_cat_num      : I18N.t('viz_violin_cat_num'),
            grouped_bar         : I18N.t('viz_grouped_bar'),
            strip_plot          : I18N.t('viz_strip_plot'),
            violin_compare      : I18N.t('viz_violin_compare'),
            grouped_bar_compare : I18N.t('viz_grouped_bar_compare'),
            parallel_coords     : I18N.t('viz_parallel_coords'),
            heatmap_all         : I18N.t('viz_heatmap_all'),
        };
    }

    var CATEGORY_CONFIG = {
        numerical   : { needsX: 'num',       needsY: false, needsZ: false },
        categorical : { needsX: 'cat',       needsY: false, needsZ: false },
        bivariate   : { needsX: 'num',       needsY: 'num', needsZ: 'num' },
        catnum      : { needsX: 'all',       needsY: 'all', needsZ: false },
        compare     : { needsX: 'multi-num', needsY: false, needsZ: false },
        heatmap_all : { needsX: false,       needsY: false, needsZ: false },
    };

    var NO_DROPDOWN_CHARTS = {
        heatmap        : true,
        scatter_matrix : true,
        heatmap_all    : true,
    };

    var VIZ_STATE_KEY = 'ds_viz_state';

    function $$(id) { return document.getElementById(id); }

    // ── State management helpers ──────────────────────────────────────────────

    function _readAndClearState() {
        try {
            var raw = sessionStorage.getItem(VIZ_STATE_KEY);
            if (!raw) return null;
            var s = JSON.parse(raw);
            // Expire setelah 5 menit
            if (Date.now() - (s.ts || 0) > 5 * 60 * 1000) {
                sessionStorage.removeItem(VIZ_STATE_KEY);
                return null;
            }
            sessionStorage.removeItem(VIZ_STATE_KEY);
            return s;
        } catch (e) { return null; }
    }

    // ── Binary decode ─────────────────────────────────────────────────────────
    function _decodeBinaryField(field) {
        if (!field || typeof field !== 'object' || !field.bdata) return field;
        var dtype  = field.dtype || 'f8';
        var binary = atob(field.bdata);
        var len    = binary.length;
        var buf    = new ArrayBuffer(len);
        var view   = new Uint8Array(buf);
        for (var i = 0; i < len; i++) view[i] = binary.charCodeAt(i);
        var arr;
        if      (dtype === 'f8')  arr = new Float64Array(buf);
        else if (dtype === 'f4')  arr = new Float32Array(buf);
        else if (dtype === 'i4')  arr = new Int32Array(buf);
        else if (dtype === 'i2')  arr = new Int16Array(buf);
        else if (dtype === 'i1')  arr = new Int8Array(buf);
        else if (dtype === 'u4')  arr = new Uint32Array(buf);
        else if (dtype === 'u2')  arr = new Uint16Array(buf);
        else if (dtype === 'u1')  arr = new Uint8Array(buf);
        else                      arr = new Float64Array(buf);
        return Array.from(arr);
    }

    function _decodeTrace(trace) {
        if (!trace || typeof trace !== 'object') return trace;
        var decoded = Object.assign({}, trace);
        ['x','y','z','values','labels','ids','open','high','low','close','lat','lon'].forEach(function(f) {
            if (decoded[f] && typeof decoded[f] === 'object' && decoded[f].bdata) {
                decoded[f] = _decodeBinaryField(decoded[f]);
            }
        });
        if (decoded.marker && typeof decoded.marker === 'object') {
            decoded.marker = Object.assign({}, decoded.marker);
            ['size','color'].forEach(function(k) {
                if (decoded.marker[k] && typeof decoded.marker[k] === 'object' && decoded.marker[k].bdata) {
                    decoded.marker[k] = _decodeBinaryField(decoded.marker[k]);
                }
            });
        }
        if ((decoded.type === 'parcoords' || decoded.type === 'splom') && Array.isArray(decoded.dimensions)) {
            decoded.dimensions = decoded.dimensions.map(function(dim) {
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
        return Object.assign({}, chartObj, { data: chartObj.data.map(_decodeTrace) });
    }

    // ── Availability ──────────────────────────────────────────────────────────
    function isAvailable(category) {
        var n = (meta.num_cols || []).length;
        var c = (meta.cat_cols || []).length;
        return { numerical: n>=1, categorical: c>=1, bivariate: n>=2, catnum: n>=1&&c>=1, compare: n>=2, heatmap_all: n+c>=2 }[category] !== false;
    }

    function defaultX(cat) {
        var cfg = CATEGORY_CONFIG[cat] || {};
        if (cfg.needsX === 'cat')       return (meta.cat_cols||[])[0] || null;
        if (cfg.needsX === 'all')       return (meta.cat_cols||[])[0] || (meta.num_cols||[])[0] || null;
        if (cfg.needsX === 'multi-num') return (meta.num_cols||[]).join(',');
        return (meta.num_cols||[])[0] || null;
    }
    function defaultY(cat) {
        var nums = meta.num_cols || [];
        if (cat === 'catnum')    return nums[0] || null;
        if (cat === 'bivariate') return nums[1] || nums[0] || null;
        return null;
    }
    function defaultZ() {
        var nums = meta.num_cols || [];
        return nums[2] || nums[1] || nums[0] || null;
    }

    // ── Chart type dropdown ───────────────────────────────────────────────────
    function _buildChartTypeDropdown() {
        var sel = $$('viz-chart-type-select');
        if (!sel) return;
        var types = CHART_TYPES[state.category] || [];
        sel.innerHTML = '';
        types.forEach(function(t) {
            var opt = document.createElement('option');
            opt.value = t; opt.textContent = getChartLabels()[t] || t;
            sel.appendChild(opt);
        });
        sel.value = state.chartType || (types[0] || '');
        var footer = document.querySelector('.viz-master-footer');
        if (footer) footer.style.display = 'none';
    }

    function _syncChartTypeDropdown() {
        var sel = $$('viz-chart-type-select');
        if (!sel) return;
        var exists = Array.from(sel.options).some(function(o){ return o.value === state.chartType; });
        if (!exists) _buildChartTypeDropdown();
        sel.value = state.chartType || '';
    }

    // ── Checkbox dropdown untuk compare ──────────────────────────────────────
    function _buildCheckboxDropdown(wrapEl, cols, selectedArr) {
        if (!wrapEl) return;
        var existing = wrapEl.querySelector('.viz-cb-dropdown');
        if (existing) existing.remove();

        var container = document.createElement('div');
        container.className = 'viz-cb-dropdown';
        container.style.cssText = 'position:relative;display:inline-block;';

        var btn = document.createElement('button');
        btn.type = 'button';
        btn.style.cssText = [
            'display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:8px;',
            'border:1px solid rgba(255,255,255,0.12);background:#172254;color:#c8d8f0;',
            'font-size:0.78rem;font-weight:600;cursor:pointer;white-space:nowrap;',
            'font-family:inherit;min-width:110px;transition:border-color .2s;',
        ].join('');

        function _updateLabel() {
            var sel = selectedArr.filter(function(c){ return cols.indexOf(c) >= 0; });
            btn.innerHTML = (sel.length === cols.length ? I18N.t('viz_all_variables') : sel.length + ' ' + I18N.t('viz_variables_selected')) +
                ' <i class="fas fa-chevron-down" style="font-size:.65rem;opacity:.7;"></i>';
        }
        _updateLabel();

        var panel = document.createElement('div');
        panel.style.cssText = [
            'display:none;position:absolute;top:calc(100% + 4px);left:0;z-index:9999;',
            'min-width:180px;max-height:240px;overflow-y:auto;',
            'background:#1a2660;border:1px solid rgba(255,255,255,0.12);',
            'border-radius:10px;padding:8px 4px;box-shadow:0 8px 24px rgba(0,0,0,.4);',
            'scrollbar-width:thin;',
        ].join('');

        // Select all / clear row
        var actRow = document.createElement('div');
        actRow.style.cssText = 'display:flex;gap:6px;padding:4px 8px 8px;border-bottom:1px solid rgba(255,255,255,.1);margin-bottom:4px;';
        var btnAll = document.createElement('button');
        var btnClr = document.createElement('button');
        var _bs = 'flex:1;padding:3px 0;font-size:.7rem;font-weight:700;border-radius:6px;cursor:pointer;border:1px solid rgba(255,255,255,.1);font-family:inherit;';
        btnAll.type='button'; btnAll.textContent=I18N.t('viz_select_all'); btnAll.style.cssText=_bs+'background:#4364f7;color:#fff;';
        btnClr.type='button'; btnClr.textContent=I18N.t('viz_clear'); btnClr.style.cssText=_bs+'background:transparent;color:#8899bb;';
        actRow.appendChild(btnAll); actRow.appendChild(btnClr);
        panel.appendChild(actRow);

        cols.forEach(function(col) {
            var row = document.createElement('label');
            row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:5px 10px;cursor:pointer;border-radius:6px;font-size:.78rem;color:#c8d8f0;';
            row.onmouseover = function(){ row.style.background='rgba(126,169,255,0.1)'; };
            row.onmouseout  = function(){ row.style.background=''; };
            var cb = document.createElement('input');
            cb.type='checkbox'; cb.value=col;
            cb.style.cssText='accent-color:#4364f7;width:14px;height:14px;cursor:pointer;';
            cb.checked = selectedArr.indexOf(col) >= 0;
            cb.addEventListener('change', function() {
                if (cb.checked) { if (selectedArr.indexOf(col)<0) selectedArr.push(col); }
                else {
                    var idx = selectedArr.indexOf(col);
                    if (idx>=0) selectedArr.splice(idx,1);
                }
                if (selectedArr.length===0) { cb.checked=true; selectedArr.push(col); }
                state.colX = selectedArr.join(',');
                _updateLabel(); fetchAndRender();
            });
            row.appendChild(cb); row.appendChild(document.createTextNode(col));
            panel.appendChild(row);
        });

        btnAll.addEventListener('click', function(e) {
            e.stopPropagation();
            selectedArr.length=0; cols.forEach(function(c){ selectedArr.push(c); });
            panel.querySelectorAll('input[type=checkbox]').forEach(function(cb){ cb.checked=true; });
            state.colX=selectedArr.join(','); _updateLabel(); fetchAndRender();
        });
        btnClr.addEventListener('click', function(e) {
            e.stopPropagation();
            selectedArr.length=0; selectedArr.push(cols[0]);
            panel.querySelectorAll('input[type=checkbox]').forEach(function(cb){ cb.checked=(cb.value===cols[0]); });
            state.colX=selectedArr.join(','); _updateLabel(); fetchAndRender();
        });

        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var open = panel.style.display!=='none';
            document.querySelectorAll('.viz-cb-panel-inner').forEach(function(p){ p.style.display='none'; });
            panel.style.display = open ? 'none' : 'block';
            btn.style.borderColor = open ? '' : '#4364f7';
        });
        document.addEventListener('click', function(){ panel.style.display='none'; btn.style.borderColor=''; });
        panel.addEventListener('click', function(e){ e.stopPropagation(); });

        container.appendChild(btn); container.appendChild(panel);
        wrapEl.appendChild(container);
    }

    // ── Populate dropdowns ────────────────────────────────────────────────────
    function populateDropdowns(forceColX, forceColY) {
        var cfg  = CATEGORY_CONFIG[state.category] || {};
        var ct   = state.chartType;
        var noDD = NO_DROPDOWN_CHARTS[ct] || false;

        var wrapX = $$('viz-dd-x-wrap');
        var wrapY = $$('viz-dd-y-wrap');
        var wrapZ = $$('viz-dd-z-wrap');
        var selX  = $$('viz-col-x');
        var selY  = $$('viz-col-y');
        var selZ  = $$('viz-col-z');
        if (!selX) return;

        var isMultiNum = (cfg.needsX === 'multi-num');
        var showX = !!(cfg.needsX) && !noDD;
        var showY = !!(cfg.needsY) && !noDD;
        var showZ = !!(cfg.needsZ) && (ct === 'bubble_chart');

        if (wrapX) wrapX.style.display = showX ? 'flex' : 'none';
        if (wrapY) wrapY.style.display = showY ? 'flex' : 'none';
        if (wrapZ) wrapZ.style.display = showZ ? 'flex' : 'none';

        var labelX = wrapX ? wrapX.querySelector('label') : null;
        var labelY = wrapY ? wrapY.querySelector('label') : null;

        function fill(sel, cols, selected) {
            sel.multiple=false; sel.size=1; sel.innerHTML='';
            (cols||[]).forEach(function(c) {
                var opt = document.createElement('option');
                opt.value=c; opt.textContent=c;
                if (c===selected) opt.selected=true;
                sel.appendChild(opt);
            });
        }

        // X dropdown
        if (showX && selX) {
            if (isMultiNum) {
                selX.style.display='none'; selX.multiple=false;
                if (labelX) labelX.textContent=I18N.t('viz_select_column');
                var allNums = meta.num_cols||[];

                // Jika ada forceColX (dari state), gunakan itu
                var selectedCols;
                if (forceColX && forceColX.indexOf(',') >= 0) {
                    selectedCols = forceColX.split(',').map(function(s){ return s.trim(); }).filter(Boolean);
                } else if (state.colX && state.colX.indexOf(',') >= 0) {
                    selectedCols = state.colX.split(',').map(function(s){ return s.trim(); }).filter(Boolean);
                } else {
                    selectedCols = allNums.slice();
                }
                if (!selectedCols.length) selectedCols = allNums.slice();
                state.colX = selectedCols.join(',');
                _buildCheckboxDropdown(wrapX, allNums, selectedCols);
            } else if (cfg.needsX === 'all') {
                if (labelX) labelX.textContent=I18N.t('viz_select_x');
                var allCols = (meta.cat_cols||[]).concat(meta.num_cols||[]);
                var targetX = forceColX || state.colX;
                if (!targetX || allCols.indexOf(targetX)<0) targetX = (meta.cat_cols||[])[0]||allCols[0]||null;
                state.colX = targetX;
                fill(selX, allCols, state.colX);
            } else {
                if (labelX) labelX.textContent=I18N.t('viz_select_x');
                var colsX = cfg.needsX==='cat' ? (meta.cat_cols||[]) : (meta.num_cols||[]);
                var targetX2 = forceColX || state.colX;
                if (!targetX2 || colsX.indexOf(targetX2)<0) targetX2 = colsX[0]||null;
                state.colX = targetX2;
                fill(selX, colsX, state.colX);
            }
        }

        // Y dropdown
        if (showY && selY) {
            if (cfg.needsY === 'all') {
                if (labelY) labelY.textContent=I18N.t('viz_select_y');
                var allColsY = (meta.cat_cols||[]).concat(meta.num_cols||[]);
                var targetY = forceColY || state.colY;
                if (!targetY || allColsY.indexOf(targetY)<0) targetY = (meta.num_cols||[])[0]||allColsY[0]||null;
                state.colY = targetY;
                fill(selY, allColsY, state.colY);
            } else {
                if (labelY) labelY.textContent=I18N.t('viz_select_y');
                var colsY = meta.num_cols||[];
                var targetY2 = forceColY || state.colY;
                if (!targetY2 || colsY.indexOf(targetY2)<0) targetY2 = defaultY(state.category);
                state.colY = targetY2;
                fill(selY, colsY, state.colY);
            }
        }

        // Z dropdown
        if (showZ && selZ) {
            var colsZ = meta.num_cols||[];
            if (!state.colZ || colsZ.indexOf(state.colZ)<0) state.colZ = defaultZ();
            fill(selZ, colsZ, state.colZ);
        }
    }

    // ── KPI row ───────────────────────────────────────────────────────────────
    function renderKpis(kpis) {
        var row = $$('viz-kpi-row');
        if (!row) return;
        row.innerHTML = '';
        (kpis||[]).slice(0,5).forEach(function(k) {
            var card = document.createElement('div');
            card.className = 'viz-kpi-card';
            card.innerHTML =
                '<div class="viz-kpi-icon"><i class="fas '+(k.icon||'fa-chart-bar')+'"></i></div>' +
                '<div class="viz-kpi-body">' +
                '<span class="viz-kpi-val">'+k.value+'</span>' +
                '<span class="viz-kpi-lbl">'+k.label+'</span>' +
                '</div>';
            row.appendChild(card);
        });
    }

    // ── Insights ───────────────────────────────────────────────────────────────
    function renderInsights(insights) {
        var container = $$('viz-insight');
        var items = $$('viz-insight-items');
        if (!container || !items) return;
        if (!insights || insights.length === 0) {
            container.style.display = 'none';
            return;
        }
        items.innerHTML = '';
        insights.slice(0, 3).forEach(function(ins) {
            var item = document.createElement('div');
            item.className = 'ov-smart-insight-item';
            item.innerHTML = '<i class="fas ' + (ins.icon || 'fa-brain') + '"></i> ' + (ins.text || '');
            items.appendChild(item);
        });
        container.style.display = 'block';
    }

    function updateLabel() {
        var titles = { numerical:I18N.t('viz_numerical'), categorical:I18N.t('viz_categorical'), bivariate:I18N.t('viz_bivariate'), catnum:I18N.t('viz_catnum'), compare:I18N.t('viz_compare'), heatmap_all:I18N.t('viz_heatmap_all') };
        var titleEl = $$('viz-category-title');
        if (titleEl) titleEl.textContent = titles[state.category] || I18N.t('viz_visualizations');
        // Hide legacy counter/label
        var ctr = $$('viz-chart-counter');
        var lbl = $$('viz-chart-type-label');
        if (ctr) ctr.style.display='none';
        if (lbl) lbl.style.display='none';
    }

    // ── Placeholder / show chart ──────────────────────────────────────────────
    function showPlaceholder(msg, needType) {
        var ph   = $$('viz-placeholder');
        var mc   = $$('viz-master-chart');
        if (ph) {
            ph.style.display='flex';
            var inner = ph.querySelector('.viz-placeholder-inner');
            if (inner) {
                var iconEl = inner.querySelector('i');
                var pEl    = inner.querySelector('p');
                if (iconEl) {
                    if (needType === 'numerical') {
                        iconEl.className = 'fas fa-hashtag';
                        iconEl.style.color = 'rgba(255,206,32,.45)';
                    } else if (needType === 'categorical') {
                        iconEl.className = 'fas fa-font';
                        iconEl.style.color = 'rgba(134,140,255,.45)';
                    } else {
                        iconEl.className = 'fas fa-chart-area';
                        iconEl.style.color = 'rgba(126,169,255,.35)';
                    }
                }
                if (pEl) {
                    if (needType) {
                        var typeLabel = needType === 'numerical' ? 'Numerik' : 'Kategorikal';
                        pEl.innerHTML = '<strong style="display:block;margin-bottom:6px;color:var(--text);font-size:.95rem;">' +
                            (msg || (typeof I18N !== 'undefined' ? I18N.t('viz_placeholder') : 'Tipe data tidak cocok')) + '</strong>' +
                            '<span style="color:var(--muted);">Silakan pilih variabel <strong style="color:var(--blue);">' + typeLabel + '</strong> yang sesuai untuk visualisasi ini.</span>';
                    } else {
                        pEl.textContent = msg || (typeof I18N !== 'undefined' ? I18N.t('viz_placeholder') : 'Dataset tidak kompatibel.');
                    }
                }
            }
        }
        if (mc) mc.style.display='none';
        var kr = $$('viz-kpi-row'); if (kr) kr.innerHTML='';
        var ins = $$('viz-insight'); if (ins) ins.style.display='none';
    }
    function showChart() {
        var ph=$$('viz-placeholder'); var mc=$$('viz-master-chart');
        if (ph) ph.style.display='none'; if (mc) mc.style.display='block';
    }
    function setLoading(plotEl) {
        if (!plotEl) return;
        plotEl.innerHTML='<div class="viz-loading" style="display:flex;align-items:center;justify-content:center;height:100%;">'+
            '<i class="fas fa-spinner fa-spin" style="font-size:1.5rem;color:#7EA9FF;"></i>'+
            '<span style="font-size:.9rem;color:#7EA9FF;margin-left:10px;">'+I18N.t('viz_loading')+'</span></div>';
        var ins = $$('viz-insight'); if (ins) ins.style.display='none';
    }
    function setError(plotEl, msg) {
        if (!plotEl) return;
        plotEl.innerHTML='<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;'+
            'height:100%;padding:24px;text-align:center;">'+
            '<i class="fas fa-exclamation-circle" style="font-size:2rem;color:#ee5d50;margin-bottom:12px;"></i>'+
            '<p style="color:#ee5d50;margin-bottom:14px;font-size:.9rem;">'+(msg||I18N.t('viz_chart_load_failed'))+'</p>'+
            '<button onclick="VizMaster.retry()" style="padding:7px 18px;border-radius:8px;'+
            'border:1px solid rgba(126,169,255,.4);background:rgba(126,169,255,.12);'+
            'color:#c8d8f0;cursor:pointer;font-family:inherit;font-size:.8rem;">'+
            '<i class="fas fa-redo"></i> '+I18N.t('viz_retry')+'</button></div>';
    }

    // ── Render from pre-rendered data (offline HTML report) ────────────────
    function renderPrerendered(category, chartType) {
        // Only use pre-rendered data in offline HTML report (file:// protocol)
        if (window.location.protocol !== 'file:') return false;
        if (typeof vizPreRendered === 'undefined' || !vizPreRendered) return false;
        var catData = vizPreRendered[category];
        if (!catData || !catData[chartType]) return false;
        var data = catData[chartType];
        var plotEl = $$('viz-master-plot');
        if (!plotEl) return false;
        renderKpis(data.kpis || []);
        renderInsights(data.insights || []);
        state.chartType = chartType;
        state.chartIndex = data.chart_index || 0;
        updateLabel();
        _syncChartTypeDropdown();
        showChart();
        if (typeof Plotly === 'undefined') { setError(plotEl, I18N.t('viz_plotly_not_loaded')); return true; }
        if (!data.chart) { setError(plotEl, I18N.t('viz_chart_data_empty')); return true; }
        var chartDecoded = _decodeChartData(data.chart);
        try { Plotly.purge(plotEl); } catch(e) {}
        plotEl.innerHTML = '';
        var layout = Object.assign({}, chartDecoded.layout || {}, { autosize:true, margin:{l:54,r:24,t:56,b:52} });
        Plotly.newPlot(plotEl, chartDecoded.data || [], layout, {
            responsive:true, displayModeBar:true, displaylogo:false,
            modeBarButtonsToRemove:['lasso2d','select2d','autoScale2d'],
            toImageButtonOptions:{format:'png',scale:2},
        }).catch(function(err){ setError(plotEl, I18N.t('viz_rendering_error')+': '+err.message); });
        return true;
    }

    // ── Fetch and render ──────────────────────────────────────────────────────
    function fetchAndRender(isRetry) {
        if (!meta.filename) return;

        if (!isAvailable(state.category)) {
            var MSGS = {
                numerical:I18N.t('viz_req_numerical'),
                categorical:I18N.t('viz_req_categorical'),
                bivariate:I18N.t('viz_req_bivariate'),
                catnum:I18N.t('viz_req_catnum'),
                compare:I18N.t('viz_req_compare'),
                heatmap_all:I18N.t('viz_req_heatmap_all'),
            };
            var NEED = {
                numerical:'numerical', categorical:'categorical',
                bivariate:'numerical', catnum:'numerical', compare:'numerical',
            };
            showPlaceholder(MSGS[state.category]||(typeof I18N !== 'undefined' ? I18N.t('viz_dataset_incompatible') : 'Dataset tidak kompatibel.'), NEED[state.category]||null);
            return;
        }

        var types = CHART_TYPES[state.category]||[];
        if (!state.chartType || types.indexOf(state.chartType)<0) {
            state.chartType=types[0]; state.chartIndex=0;
        } else {
            state.chartIndex=types.indexOf(state.chartType);
        }

        // Use pre-rendered data if available (offline HTML report)
        if (renderPrerendered(state.category, state.chartType)) {
            state.loading = false;
            return;
        }

        _syncChartTypeDropdown();
        if (_activeController) try { _activeController.abort(); } catch(e) {}
        var controller=null, signal=undefined;
        if (typeof AbortController!=='undefined') {
            controller=new AbortController(); _activeController=controller; signal=controller.signal;
        }

        var params = new URLSearchParams({ category:state.category, chart_type:state.chartType });
        var currentTheme = localStorage.getItem('ds-theme') || 'dark';
        params.set('theme', currentTheme);
        var strictNoDD = (state.chartType==='heatmap'||state.chartType==='scatter_matrix'||state.chartType==='heatmap_all');
        if (state.colX && !strictNoDD) params.set('col_x', state.colX);
        if (state.colY && !strictNoDD && state.category!=='compare') params.set('col_y', state.colY);
        if (state.colZ && state.chartType==='bubble_chart') params.set('col_z', state.colZ);

        var url = '/api/viz-chart/'+encodeURIComponent(meta.filename)+'?'+params.toString();
        showChart();
        var plotEl = $$('viz-master-plot');
        setLoading(plotEl); state.loading=true;

        var tid = setTimeout(function(){ if(controller) try{ controller.abort(); }catch(e){} }, 25000);

        fetch(url, signal ? {signal:signal} : {})
            .then(function(r){ clearTimeout(tid); if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
            .then(function(data) {
                state.loading=false; _activeController=null;
                if (!data.ok) {
                    var catNeed = { numerical:'numerical', categorical:'categorical', bivariate:'numerical', catnum:'numerical', compare:'numerical' };
                    showPlaceholder(data.placeholder||(typeof I18N !== 'undefined' ? I18N.t('viz_chart_unavailable') : 'Grafik tidak tersedia.'), catNeed[state.category]||null);
                    renderKpis(data.kpis||[]); return;
                }
                renderKpis(data.kpis||[]);
                renderInsights(data.insights||[]);
                state.chartType  = data.chart_type  || state.chartType;
                state.chartIndex = data.chart_index != null ? data.chart_index : state.chartIndex;
                updateLabel(); _syncChartTypeDropdown();
                if (typeof Plotly==='undefined') { setError(plotEl,I18N.t('viz_plotly_not_loaded')); return; }
                if (!data.chart) { setError(plotEl,I18N.t('viz_chart_data_empty_server')); return; }
                var chartDecoded = _decodeChartData(data.chart);
                try { Plotly.purge(plotEl); } catch(e) {}
                plotEl.innerHTML='';
                var layout = Object.assign({}, chartDecoded.layout||{}, { autosize:true, margin:{l:54,r:24,t:56,b:52} });
                Plotly.newPlot(plotEl, chartDecoded.data||[], layout, {
                    responsive:true, displayModeBar:true, displaylogo:false,
                    modeBarButtonsToRemove:['lasso2d','select2d','autoScale2d'],
                    toImageButtonOptions:{format:'png',scale:2},
                }).catch(function(err){ setError(plotEl,I18N.t('viz_rendering_error')+': '+err.message); });
            })
            .catch(function(err) {
                clearTimeout(tid); state.loading=false; _activeController=null;
                if (err.name==='AbortError') return;
                if (!isRetry) { setTimeout(function(){ fetchAndRender(true); }, 900); return; }
                setError(plotEl, I18N.t('viz_chart_load_failed')+': '+(err.message||I18N.t('viz_unknown_error')));
            });
    }

    // ── Sidebar highlight ─────────────────────────────────────────────────────
    function highlightSidebar(category) {
        document.querySelectorAll('.nav-sub-item').forEach(function(li){ li.classList.remove('active'); });
        var MAP = { numerical:'menu-viz-num', categorical:'menu-viz-cat', bivariate:'menu-viz-biv', catnum:'menu-viz-catnum', compare:'menu-viz-compare', heatmap_all:'menu-viz-heatmap-all' };
        var el = document.getElementById(MAP[category]);
        if (el) el.classList.add('active');
        var accBody = document.getElementById('acc-viz');
        var accBtn  = document.getElementById('acc-viz-btn');
        if (accBody && !accBody.classList.contains('open')) {
            accBody.classList.add('open');
            if (accBtn) accBtn.classList.add('open');
        }
    }

    // ── Open category (public, accepts optional col params) ───────────────────
    function openCategory(category, chartType, colX, colY) {
        if (state.loading && _activeController) try { _activeController.abort(); } catch(e) {}
        state.category = category || 'numerical';
        var types = CHART_TYPES[state.category]||[];

        if (chartType && types.indexOf(chartType)>=0) {
            state.chartType=chartType; state.chartIndex=types.indexOf(chartType);
        } else {
            state.chartType=types[0]||null; state.chartIndex=0;
        }

        // Set col dari params atau default
        if (category === 'compare') {
            state.colX = colX || (meta.num_cols||[]).join(',');
            state.colY = null;
        } else {
            state.colX = colX || defaultX(state.category);
            state.colY = colY || defaultY(state.category);
        }
        state.colZ = defaultZ();

        _pendingOpen=true;
        setTimeout(function(){ _pendingOpen=false; }, 600);

        populateDropdowns(state.colX, state.colY);
        updateLabel();
        highlightSidebar(state.category);
        _buildChartTypeDropdown();
        fetchAndRender();
    }

    // ── Bind events ───────────────────────────────────────────────────────────
    function bindEvents() {
        var selX=$$('viz-col-x'), selY=$$('viz-col-y'), selZ=$$('viz-col-z'), selT=$$('viz-chart-type-select');
        if (selX) selX.addEventListener('change', function(){ if(!selX.multiple){ state.colX=selX.value; fetchAndRender(); } });
        if (selY) selY.addEventListener('change', function(){ state.colY=selY.value; fetchAndRender(); });
        if (selZ) selZ.addEventListener('change', function(){ state.colZ=selZ.value; fetchAndRender(); });
        if (selT) selT.addEventListener('change', function(){
            var types=CHART_TYPES[state.category]||[];
            state.chartType=selT.value; state.chartIndex=types.indexOf(selT.value);
            populateDropdowns(null, null); fetchAndRender();
        });
        var _rsz;
        window.addEventListener('resize', function(){
            clearTimeout(_rsz); _rsz=setTimeout(function(){
                var el=$$('viz-master-plot');
                if(el&&el._fullLayout&&typeof Plotly!=='undefined') Plotly.Plots.resize(el);
            }, 200);
        });
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    function init(vizMeta) {
        meta = vizMeta || {};
        bindEvents();
    }

    // ── onTabShow: baca state dari sessionStorage ─────────────────────────────
    function onTabShow() {
        if (!meta.filename) return;
        if (_pendingOpen) return;

        // Coba baca state yang disimpan dari klik chart di Overview
        var savedState = _readAndClearState();
        if (savedState && savedState.category) {
            openCategory(
                savedState.category,
                savedState.chartType || null,
                savedState.colX      || null,
                savedState.colY      || null
            );
            return;
        }

        // Tidak ada saved state — cek apakah plot sudah ada
        var plotEl  = $$('viz-master-plot');
        var hasPlot = plotEl && plotEl._fullLayout && plotEl.data && plotEl.data.length>0;
        if (!hasPlot) {
            openCategory(state.category||'numerical', state.chartType||null);
        } else if (plotEl && typeof Plotly!=='undefined') {
            Plotly.Plots.resize(plotEl);
        }
    }

    function retry() { fetchAndRender(false); }

    return { init:init, openCategory:openCategory, onTabShow:onTabShow, retry:retry };
})();

/* Global helper dipanggil dari dashboardOverview.js dan link sidebar */
function openVizCategory(cat, chartType, colX, colY) {
    VizMaster.openCategory(cat, chartType||null, colX||null, colY||null);
    if (typeof switchTab==='function') switchTab('visualizations');
}