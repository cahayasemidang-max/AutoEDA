/* ============================================================
   DS Generator — script.js  (Fixed)
   ============================================================ */
'use strict';

/* ─── TAB SWITCHING ─────────────────────────────────────────── */
function switchTab(tabName) {
    /* Hide all */
    document.querySelectorAll('.tab-content').forEach(function (el) {
        el.style.display = 'none';
        el.classList.remove('active-tab');
    });

    /* Show target */
    var target = document.getElementById('tab-' + tabName);
    if (target) {
        target.style.display = 'block';
        target.classList.add('active-tab');
    }

    /* Update nav active state */
    document.querySelectorAll('.nav-item, .nav-sub-item').forEach(function (li) {
        li.classList.remove('active');
    });

    /* Mark correct sidebar item active */
    var menuMap = {
        overview    : 'menu-overview',
        upload      : 'menu-upload',
        preview     : 'menu-preview',
        cleaning    : 'menu-cleaning',
        numerical   : 'menu-numerical',
        categorical  : 'menu-categorical',
        advanced    : 'menu-advanced',
        visualizations: 'menu-visualizations',
        timeseries  : 'menu-timeseries',
        insights    : 'menu-insights',
        reporting   : 'menu-reporting',
        ai          : 'menu-ai',
    };
    var menuId = menuMap[tabName];
    if (menuId) {
        var menuEl = document.getElementById(menuId);
        if (menuEl) menuEl.classList.add('active');
    }

    /* Auto-open relevant accordion */
    var accMap = {
        numerical   : 'acc-stats',
        categorical  : 'acc-stats',
        advanced    : 'acc-stats',
    };
    if (accMap[tabName]) {
        var accBody = document.getElementById(accMap[tabName]);
        if (accBody && !accBody.classList.contains('open')) {
            accBody.classList.add('open');
            var trigger = accBody.previousElementSibling;
            if (trigger) trigger.classList.add('open');
        }
    }

    /* Scroll content to top */
    var cc = document.querySelector('.content-container');
    if (cc) cc.scrollTop = 0;

    /* Trigger tab-specific hooks */
    if (tabName === 'visualizations') {
        setTimeout(function () {
            if (typeof VizMaster !== 'undefined') VizMaster.onTabShow();
        }, 80);
    }
    if (tabName === 'overview') {
        setTimeout(function () {
            if (typeof OverviewDashboard !== 'undefined') OverviewDashboard.onTabShow();
        }, 80);
    }

    /* Adjust DataTable columns now that tab is visible */
    setTimeout(function () {
        var tbl = $('.tab-content.active-tab table.dataTable');
        if (tbl.length && $.fn.DataTable) {
            tbl.each(function () {
                if ($.fn.DataTable.isDataTable(this)) $(this).DataTable().columns.adjust();
            });
        }
    }, 100);
}

/* ─── PERSISTENT THEME CONTROLLER ──────────────────────────── */
function initThemeToggle() {
    var btn  = document.getElementById('theme-toggle');
    var icon = document.getElementById('theme-icon');
    if (!btn) return;

    var saved = localStorage.getItem('ds-theme');
    if (saved === 'dark') {
        applyTheme(true, icon);
    } else if (saved === 'light') {
        applyTheme(false, icon);
    } else {
        /* Default: system preference */
        var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyTheme(prefersDark, icon);
        localStorage.setItem('ds-theme', prefersDark ? 'dark' : 'light');
    }

    btn.addEventListener('click', function () {
        var isDark = document.body.classList.contains('dark-theme');
        applyTheme(!isDark, icon);
        localStorage.setItem('ds-theme', !isDark ? 'dark' : 'light');
    });
}

function applyTheme(dark, icon) {
    document.body.classList.toggle('dark-theme', dark);
    document.body.classList.toggle('light-theme', !dark);
    /* Backward compat: keep data-theme attribute for legacy selectors */
    document.body.setAttribute('data-theme', dark ? 'dark' : 'light');
    if (!icon) icon = document.getElementById('theme-icon');
    if (icon) {
        icon.className = 'fas ' + (dark ? 'fa-sun' : 'fa-moon');
        icon.setAttribute('title', dark ? I18N.t('theme_switch_light') : I18N.t('theme_switch_dark'));
    }
    /* Re-theme Plotly charts */
    setTimeout(function () {
        if (typeof Plotly === 'undefined') return;
        var fontColor = dark ? '#CBD5E1' : '#6B7280';
        var gridColor = dark ? 'rgba(255,255,255,0.06)' : '#E5E7EB';
        document.querySelectorAll('[id^="plot-"],[id^="ov-"]').forEach(function (el) {
            if (el._fullData) {
                Plotly.relayout(el, {
                    paper_bgcolor: 'rgba(0,0,0,0)',
                    plot_bgcolor : 'rgba(0,0,0,0)',
                    'font.color' : fontColor,
                    'xaxis.gridcolor'    : gridColor,
                    'yaxis.gridcolor'    : gridColor,
                    'xaxis.zerolinecolor': gridColor,
                    'yaxis.zerolinecolor': gridColor,
                });
            }
        });
    }, 80);
}

/* ─── TEAM MODAL ─────────────────────────────────────────────── */
function initTeamModal() {
    var openBtn  = document.getElementById('team-profile-btn');
    var modal    = document.getElementById('team-modal');
    var closeBtn = document.getElementById('close-modal');
    if (!openBtn || !modal) return;

    openBtn.addEventListener('click', function () {
        modal.style.display = 'flex';
    });

    function closeModal() { modal.style.display = 'none'; }
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.style.display === 'flex') closeModal();
    });
}

/* ─── LANGUAGE HANDLER (delegates to I18N) ──────────────────── */
function initLanguageSelector() {
    if (typeof I18N === 'undefined') return;

    /* Apply data-translate backward compat for current language */
    document.querySelectorAll('[data-translate]').forEach(function (el) {
        var key = el.getAttribute('data-translate');
        var translated = I18N.t(key);
        if (translated !== key) el.innerHTML = translated;
    });
}


/* ─── DATATABLES ─────────────────────────────────────────────── */
function initDataTables() {
    if (typeof $ === 'undefined' || typeof $.fn.DataTable === 'undefined') return;
    $('table.data-table').each(function () {
        if (!$.fn.DataTable.isDataTable(this)) {
            $(this).DataTable({
                pageLength : 10,
                lengthMenu: [
                  [10, 25, 50, 100, -1],
                  [10, 25, 50, 100, I18N.t('dt_all')]
                ],
                responsive : false,
                scrollX    : true,
                dom        : '<"dt-top"Bf>rt<"dt-bot"lip>',
                buttons    : [
                    { extend:'csvHtml5',   text:'<i class="fas fa-file-csv"></i> ' + I18N.t('dt_csv'),   className:'dt-btn' },
                    { extend:'excelHtml5', text:'<i class="fas fa-file-excel"></i> ' + I18N.t('dt_excel'), className:'dt-btn' },
                    { extend:'pdfHtml5',   text:'<i class="fas fa-file-pdf"></i> ' + I18N.t('dt_pdf'),   className:'dt-btn',
                      orientation:'landscape', pageSize:'A4' },
                ],
                language: {
                    search: '<i class="fas fa-search"></i>',
                    searchPlaceholder: I18N.t('dt_filter'),
                    lengthMenu: I18N.t('dt_show_rows'),
                    info: I18N.t('dt_showing'),
                    paginate: { previous:'‹', next:'›' },
                },
            });
        }
    });
}

/* ─── AI CHAT ────────────────────────────────────────────────── */
function sendAIMessage() {
    var input = document.getElementById('ai-input');
    if (!input) return;
    var msg = input.value.trim();
    if (!msg) return;

    appendChatMsg(msg, 'user');
    input.value = '';

    var typingEl = appendChatMsg(typeof I18N !== 'undefined' ? I18N.t('ai_typing') : 'Typing...', 'bot', true);
    var ctx = window.datasetContext || '';

    fetch('/api/ai-chat', {
        method  : 'POST',
        headers : { 'Content-Type': 'application/json' },
        body    : JSON.stringify({ message: msg, context: ctx }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        var bubble = typingEl.querySelector('.chat-bubble');
        bubble.innerHTML = data.reply || (typeof I18N !== 'undefined' ? I18N.t('ai_no_resp') : 'No response from server.');
        bubble.classList.remove('typing');
    })
    .catch(function () {
        var bubble = typingEl.querySelector('.chat-bubble');
        bubble.innerHTML = I18N.t('ai_fail');
        bubble.classList.remove('typing');
    });
}

function appendChatMsg(text, role, typing) {
    typing = typing || false;
    var container = document.getElementById('chat-messages');
    if (!container) return null;

    var div = document.createElement('div');
    div.className = 'chat-msg ' + role;
    div.innerHTML =
        '<div class="chat-avatar"><i class="fas fa-' + (role === 'bot' ? 'robot' : 'user') + '"></i></div>' +
        '<div class="chat-bubble' + (typing ? ' typing' : '') + '">' + text + '</div>';
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div;
}

function initAIChat() {
    var input = document.getElementById('ai-input');
    if (!input) return;
    input.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') sendAIMessage();
    });
}

/* ─── INJECT DT STYLES ───────────────────────────────────────── */
function injectDTStyles() {
    if (document.getElementById('dt-custom-styles')) return;
    var style = document.createElement('style');
    style.id  = 'dt-custom-styles';
    style.textContent = [
        '.dt-top{display:flex;align-items:center;gap:10px;padding:12px 16px;flex-wrap:wrap;}',
        '.dt-bot{display:flex;align-items:center;justify-content:space-between;padding:10px 16px;flex-wrap:wrap;gap:8px;}',
        '.dt-btn{background:var(--blue-light)!important;color:var(--blue)!important;',
        'border:1px solid var(--blue)!important;border-radius:8px!important;',
        'padding:6px 12px!important;font-size:.78rem!important;font-weight:600!important;',
        'cursor:pointer!important;transition:.2s!important;}',
        '.dt-btn:hover{background:var(--blue)!important;color:#fff!important;}',
        '.dataTables_filter input{border:1px solid var(--border);border-radius:8px;',
        'padding:6px 10px;background:var(--bg);color:var(--text);font-size:.85rem;',
        'outline:none;margin-left:4px;}',
        '.dataTables_filter input:focus{border-color:var(--blue);}',
        '.dataTables_paginate .paginate_button{padding:4px 10px!important;',
        'border-radius:6px!important;font-size:.8rem!important;color:var(--text)!important;cursor:pointer;}',
        '.dataTables_paginate .paginate_button.current{background:var(--blue)!important;',
        'color:#fff!important;border:none!important;}',
        '.dataTables_paginate .paginate_button:hover:not(.current){background:var(--blue-light)!important;',
        'color:var(--blue)!important;border:none!important;}',
        '.dataTables_info{font-size:.78rem;color:var(--muted);}',
    ].join('');
    document.head.appendChild(style);
}

/* ─── MOBILE SIDEBAR ────────────────────────────────────────── */
function initMobileSidebar() {
    if (window.innerWidth > 900) return;
    var sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    document.querySelectorAll('.nav-item > a, .nav-sub-item > a').forEach(function (link) {
        link.addEventListener('click', function () {
            sidebar.classList.remove('mobile-open');
        });
    });
}

/* ─── MAIN INIT ──────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
    injectDTStyles();
    initThemeToggle();
    initLanguageSelector();
    initTeamModal();
    initAIChat();
    initMobileSidebar();

    if (typeof $ !== 'undefined') {
        $(document).ready(function () { initDataTables(); });
    } else {
        setTimeout(initDataTables, 800);
    }

    /* Ensure overview tab is active on first load */
    var firstActive = document.querySelector('.tab-content.active-tab');
    if (!firstActive) {
        var overview = document.getElementById('tab-overview');
        if (overview) {
            overview.style.display = 'block';
            overview.classList.add('active-tab');
        }
    }

    /* Trigger visible chart renders after DOM settles */
    setTimeout(function () {
        if (typeof renderVisibleCharts === 'function') renderVisibleCharts();
    }, 400);
});

/**
 * dashboardOverview.js
 * Render & interaksi tab Dashboard Overview (grid KPI + 6 chart slots).
 */
'use strict';

var OverviewDashboard = (function () {
    var data = null;
    var rendered = new Set();

    var PLOTLY_CFG = {
        responsive: true,
        displayModeBar: false,
        displaylogo: false,
        scrollZoom: false,
    };

    function getLayoutPatch() {
        var dark = document.body.classList.contains('dark-theme');
        var patch = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: dark ? '#CBD5E1' : '#6B7280', family: 'Inter, sans-serif', size: 11 },
            margin: { l: 40, r: 16, t: 36, b: 36 },
            hoverlabel: {
                bgcolor: dark ? 'rgba(15,23,42,0.93)' : 'rgba(255,255,255,0.93)',
                bordercolor: dark ? 'rgba(100,160,235,0.45)' : 'rgba(0,0,0,0.1)',
                font: { color: dark ? '#e8f4fc' : '#1F2937', size: 12 },
            },
        };
        if (!dark) patch.template = 'plotly_white';
        return patch;
    }

    function drawSlot(slotId, chartJson, force) {
        if (!chartJson || typeof Plotly === 'undefined') return;
        var el = document.getElementById(slotId);
        if (!el) return;
        if (!force && rendered.has(slotId)) {
            Plotly.Plots.resize(el);
            return;
        }
        var layout = Object.assign({}, chartJson.layout || {}, getLayoutPatch());
        Plotly.react(el, chartJson.data || [], layout, PLOTLY_CFG).then(function () {
            rendered.add(slotId);
        }).catch(function (err) {
            console.warn('[Overview] Chart render failed:', slotId, err);
        });
    }

    function renderAll() {
        if (!data || !data.slots) return;

        Object.keys(data.slots).forEach(function (key) {
            var slot = data.slots[key];
            if (slot && slot.visible && slot.chart) {
                drawSlot(key, slot.chart, false);
            }
        });
    }

    function bindToggles() {
        if (!data || !data.toggle_data) return;

        Object.keys(data.toggle_data).forEach(function (slotId) {
            var toggle = data.toggle_data[slotId];
            var select = document.getElementById('toggle-' + slotId);
            if (!select || !toggle.charts) return;

            select.addEventListener('change', function () {
                var col = select.value;
                var chart = toggle.charts[col];
                if (chart) {
                    rendered.delete(slotId);
                    drawSlot(slotId, chart, true);
                }
            });
        });
    }

    function bindVizNavigation() {
        document.querySelectorAll('.ov-chart-slot[data-viz-tab]').forEach(function (el) {
            el.addEventListener('click', function (e) {
                if (e.target.closest('.ov-toggle-wrap')) return;
                goToVisualizations(el.getAttribute('data-viz-tab'), el.getAttribute('data-viz-sub'));
            });
        });
    }

    function goToVisualizations(tab, subTab) {
        if (tab === 'timeseries') {
            if (typeof switchTab === 'function') switchTab('timeseries');
            setTimeout(function () {
                if (typeof switchTsTab === 'function') switchTsTab('line');
            }, 90);
            return;
        }
        if (typeof openVizCategory === 'function') {
            openVizCategory(subTab || 'numerical');
        } else if (typeof switchTab === 'function') {
            switchTab('visualizations');
        }
    }

    function init(overviewPayload) {
        data = overviewPayload || null;
        if (!data) return;

        bindToggles();
        bindVizNavigation();

        var overviewTab = document.getElementById('tab-overview');
        if (overviewTab && overviewTab.classList.contains('active-tab')) {
            setTimeout(renderAll, 200);
        }
    }

    function onTabShow() {
        setTimeout(renderAll, 120);
    }

    function onResize() {
        rendered.forEach(function (slotId) {
            var el = document.getElementById(slotId);
            if (el && el._fullLayout) Plotly.Plots.resize(el);
        });
    }

    return {
        init: init,
        onTabShow: onTabShow,
        onResize: onResize,
        goToVisualizations: goToVisualizations,
        renderAll: renderAll,
    };
})();

/* Global hook untuk onclick di template */
function goToVisualizations(tab, subTab) {
    OverviewDashboard.goToVisualizations(tab, subTab);
}

// Sidebar accordion fix for Visualizations & Descriptive Statistics
// Purpose: provide toggleAccordion(accId) and ensure submenu elements are shown/hidden.

(function () {
  'use strict';

  function toggleAccordion(accId) {
    try { console.log('[sidebarAccordionFix] toggleAccordion:', accId); } catch(e) {}

    // 1) Accordion markup (recommended)
    var item = document.getElementById(accId) || document.querySelector('.nav-accordion-item#' + CSS.escape(accId));
    try { console.log('[sideba rAccordionFix] item found?', !!item, 'accId=', accId); } catch(e) {}

    if (item) {
      item.classList.toggle('open');
      var body = item.querySelector('.nav-accordion-body');
      if (body) {
        // Ensure clickable: override inline display
        var isOpen = item.classList.contains('open');
        body.style.display = isOpen ? 'block' : 'none';
        var innerLis = body.querySelectorAll('li');
        innerLis.forEach(function (li) {
          li.style.display = isOpen ? '' : 'none';
        });
      }
      return true;
    }

    // 2) Fallback: try toggling nested submenu container
    var any = document.querySelector('[onclick="toggleAccordion(\'' + accId + '\')"], [onclick="toggleAccordion(\"' + accId + '\")"]');
    if (!any) return false;

    var parent = any.closest('li');
    if (parent) {
      var target = parent.querySelector('.nav-accordion-body') || parent.querySelector('.sub-menu') || parent.querySelector('ul');
      if (target) {
        var show = getComputedStyle(target).display === 'none';
        target.style.display = show ? 'block' : 'none';
        return true;
      }
    }

    return false;
  }

  window.toggleAccordion = toggleAccordion;
})();

