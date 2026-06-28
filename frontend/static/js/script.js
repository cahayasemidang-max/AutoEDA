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
        document.querySelectorAll('[id^="plot-"],[id^="ov-"],[id^="ts-"],[id="viz-master-plot"]').forEach(function (el) {
            if (el && (el._fullData || el._fullLayout)) {
                try {
                    Plotly.relayout(el, {
                        paper_bgcolor: 'rgba(0,0,0,0)',
                        plot_bgcolor : 'rgba(0,0,0,0)',
                        'font.color' : fontColor,
                        'xaxis.gridcolor'    : gridColor,
                        'yaxis.gridcolor'    : gridColor,
                        'xaxis.zerolinecolor': gridColor,
                        'yaxis.zerolinecolor': gridColor,
                    });
                } catch (e) {}
            }
        });
    }, 80);


    // Ensure tables reflow after theme change
    setTimeout(adjustResponsiveTables, 120);
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

/* ─── LANGUAGE SELECTOR ────────────────────────────────────────── */
var TRANSLATIONS = {
    en: {
        /* Topbar */
        title        : 'Descriptive Statistics Generator',
        desc         : 'Upload, analyze, visualize and get insights automatically',
        subtitle     : 'Descriptive Statistics',
        admin_role   : 'Data Science Team',
        /* Smart Insights tab */
        insights_title    : 'Smart Insights',
        insights_subtitle : 'Automated data-driven conclusions from your dataset.',
        /* Sidebar sections */
        nav_main     : 'MAIN',
        nav_data     : 'DATA',
        nav_stats    : 'STATISTICS',
        nav_viz      : 'VISUALIZATIONS',
        nav_ts       : 'TIME SERIES',
        nav_insights : 'INSIGHTS',
        nav_reporting: 'REPORTING',
        /* Sidebar items */
        nav_dashboard    : 'Dashboard',
        nav_upload       : 'Upload Data',
        nav_preview      : 'Data Preview',
        nav_cleaning     : 'Data Cleaning',
        nav_statistics   : 'Statistics',
        nav_numerical    : 'Numerical Stats',
        nav_categorical  : 'Categorical Stats',
        nav_advanced     : 'Advanced Stats',
        nav_visualizations: 'Visualizations',
        nav_timeseries   : 'Time Series',
        nav_ts_overview  : 'Overview Panel',
        nav_ts_line      : 'Line Chart',
        nav_ts_trend     : 'Trend Line',
        nav_ts_ma        : 'Moving Average',
        nav_ts_rolling   : 'Rolling Mean',
        nav_smart_insights: 'Smart Insights',
        nav_reporting_sys : 'Reporting System',
        nav_dl_pdf       : 'Download Report PDF',
        nav_dl_html      : 'Download HTML Dashboard',
        nav_exp_excel    : 'Export to Excel',
        nav_exp_csv      : 'Export to CSV',
        /* Data Cleaning */
        cleaning_desc    : 'Select operation, preview impact, then apply. All steps saved in history.',
        cleaning_ops     : 'Cleaning Operations',
        cleaning_subdesc : 'Select operation → Preview → Apply',
        /* Overview */
        ov_dashboard     : 'Dashboard',
        ov_go_viz        : 'Visualizations',
        ov_column        : 'Column:',
        /* Banner */
        banner_warning   : '⚠️ Warning: Data needs cleaning!',
        banner_clean_btn : 'Clean Now',
        banner_success   : '✅ Cleaning successful! Data is ready to use.',
        banner_viz_btn   : 'View Visualizations',
        /* Upload raw mode */
        ov_raw_warning   : '⚠️ Dataset detected as not clean (Raw Mode). Some visualizations are disabled until data is cleaned.',
        /* Data Quality */
        dq_report_title  : 'Data Quality Report',
        /* Placeholder */
        viz_placeholder  : 'Dataset is not compatible with this category.',
        viz_select_hint  : 'Select a category from the sidebar to start',
        /* TS */
        ts_date_col  : 'Date Column',
        ts_metric    : 'Metric',
        ts_frequency : 'Frequency',
        ts_datapoints: 'Data Points',
        ts_period    : 'Period',
        ts_no_datetime: 'Dataset does not have a valid datetime column.',
        /* AI Chat */
        ai_typing    : 'Typing...',
        ai_no_resp   : 'No response from server.',
        ai_fail      : '⚠️ Failed to connect to AI. Make sure ANTHROPIC_API_KEY is set.',
        sdi_title    : 'Dataset Info',
        sdi_filename : 'File:',
        sdi_filesize : 'Size:',
        sdi_uploaded : 'Uploaded:',
        /* Outlier badge */
        outlier_badge_msg   : 'Data is valid — no missing values, duplicates, or inconsistencies.',
        outlier_badge_suffix: 'detected (IQR). Data distribution is unique.',
        outlier_badge_btn   : 'Handle Outlier',
        /* Upload page */
        upload_title        : 'Upload Dataset',
        upload_subtitle     : 'Upload your data file to begin automatic exploratory analysis',
        upload_select_title : 'Select Your File',
        upload_select_desc  : 'Drag & drop or browse to upload. Max file size: 100 MB.',
        upload_drop_title   : 'Drag & drop your file here',
        upload_drop_desc    : 'Supported: .csv, .xlsx, .txt',
        upload_browse       : 'Browse File',
        upload_analyze      : 'Analyze Dataset',
        upload_analyzing    : 'Analyzing…',
        upload_secure       : 'Secure upload',
        upload_fast         : 'Auto-EDA in seconds',
        upload_max          : 'Max 100 MB',
        upload_tip_title    : 'Pro tip:',
        upload_tip_text     : 'For best results, ensure your CSV uses comma delimiters and the first row contains column headers. Datetime columns are auto-detected for time series analysis.',
        upload_recent_title : 'Recent Datasets',
        upload_recent_sub   : 'Click any previous dataset to instantly reload its analysis.',
        upload_search_ph    : 'Search datasets...',
        upload_empty_title  : 'No datasets yet',
        upload_empty_desc   : 'No datasets yet. Upload one to get started.',
        upload_badge        : 'Analyzed',
        upload_fi_name      : 'File Name',
        upload_fi_size      : 'File Size',
        upload_fi_format    : 'Format',
    },
    id: {
        /* Topbar */
        title        : 'Generator Statistik Deskriptif',
        desc         : 'Unggah, analisis, visualisasi, dan dapatkan wawasan secara otomatis',
        subtitle     : 'Statistik Deskriptif',
        admin_role   : 'Tim Ilmu Data',
        /* Smart Insights tab */
        insights_title    : 'Wawasan Cerdas',
        insights_subtitle : 'Kesimpulan otomatis berbasis data dari dataset Anda.',
        /* Sidebar sections */
        nav_main     : 'UTAMA',
        nav_data     : 'DATA',
        nav_stats    : 'STATISTIK',
        nav_viz      : 'VISUALISASI',
        nav_ts       : 'DERET WAKTU',
        nav_insights : 'WAWASAN',
        nav_reporting: 'PELAPORAN',
        /* Sidebar items */
        nav_dashboard    : 'Beranda',
        nav_upload       : 'Unggah Data',
        nav_preview      : 'Pratinjau Data',
        nav_cleaning     : 'Pembersihan Data',
        nav_statistics   : 'Statistik',
        nav_numerical    : 'Statistik Numerik',
        nav_categorical  : 'Statistik Kategorik',
        nav_advanced     : 'Statistik Lanjut',
        nav_visualizations: 'Visualisasi',
        nav_timeseries   : 'Deret Waktu',
        nav_ts_overview  : 'Panel Ikhtisar',
        nav_ts_line      : 'Grafik Garis',
        nav_ts_trend     : 'Garis Tren',
        nav_ts_ma        : 'Rata-rata Bergerak',
        nav_ts_rolling   : 'Rata-rata Bergulir',
        nav_smart_insights: 'Wawasan Cerdas',
        nav_reporting_sys : 'Sistem Pelaporan',
        nav_dl_pdf       : 'Unduh Laporan PDF',
        nav_dl_html      : 'Unduh Dashboard HTML',
        nav_exp_excel    : 'Ekspor ke Excel',
        nav_exp_csv      : 'Ekspor ke CSV',
        /* Data Cleaning */
        cleaning_desc    : 'Pilih operasi, preview dampak, lalu apply. Semua langkah tersimpan di history.',
        cleaning_ops     : 'Operasi Cleaning',
        cleaning_subdesc : 'Pilih operasi → Preview → Apply',
        /* Overview */
        ov_dashboard     : 'Beranda',
        ov_go_viz        : 'Visualisasi',
        ov_column        : 'Kolom:',
        /* Banner */
        banner_warning   : '⚠️ Data perlu di-cleaning!',
        banner_clean_btn : 'Bersihkan Sekarang',
        banner_success   : '✅ Berhasil melakukan cleaning! Data siap digunakan.',
        banner_viz_btn   : 'Lihat Visualisasi',
        /* Upload raw mode */
        ov_raw_warning   : '⚠️ Dataset terdeteksi belum bersih (Mode Raw). Beberapa visualisasi dinonaktifkan hingga data dibersihkan.',
        /* Data Quality */
        dq_report_title  : 'Laporan Kualitas Data',
        /* Placeholder */
        viz_placeholder  : 'Dataset tidak kompatibel untuk kategori ini.',
        viz_select_hint  : 'Pilih kategori dari sidebar untuk mulai',
        /* TS */
        ts_date_col  : 'Kolom Tanggal',
        ts_metric    : 'Metrik',
        ts_frequency : 'Frekuensi',
        ts_datapoints: 'Titik Data',
        ts_period    : 'Periode',
        ts_no_datetime: 'Dataset tidak memiliki kolom datetime yang valid.',
        /* AI Chat */
        ai_typing    : 'Sedang mengetik...',
        ai_no_resp   : 'Tidak ada respons dari server.',
        ai_fail      : '⚠️ Gagal terhubung ke AI. Pastikan ANTHROPIC_API_KEY sudah diset.',
        sdi_title    : 'Info Dataset',
        sdi_filename : 'File:',
        sdi_filesize : 'Ukuran:',
        sdi_uploaded : 'Diunggah:',
        /* Outlier badge */
        outlier_badge_msg   : 'Data sudah valid — tidak ada missing, duplikat, atau inkonsistensi.',
        outlier_badge_suffix: 'terdeteksi (IQR). Distribusi data bersifat unik.',
        outlier_badge_btn   : 'Tangani Outlier',
        /* Upload page */
        upload_title        : 'Unggah Dataset',
        upload_subtitle     : 'Unggah file data Anda untuk memulai analisis eksploratif otomatis',
        upload_select_title : 'Pilih File Anda',
        upload_select_desc  : 'Seret & lepas atau telusuri untuk mengunggah. Ukuran maks: 100 MB.',
        upload_drop_title   : 'Seret & lepas file Anda di sini',
        upload_drop_desc    : 'Didukung: .csv, .xlsx, .txt',
        upload_browse       : 'Telusuri File',
        upload_analyze      : 'Analisis Dataset',
        upload_analyzing    : 'Menganalisis…',
        upload_secure       : 'Unggah aman',
        upload_fast         : 'Auto-EDA dalam hitungan detik',
        upload_max          : 'Maks 100 MB',
        upload_tip_title    : 'Tips pro:',
        upload_tip_text     : 'Untuk hasil terbaik, pastikan CSV Anda menggunakan pemisah koma dan baris pertama berisi nama kolom. Kolom datetime akan terdeteksi otomatis untuk analisis deret waktu.',
        upload_recent_title : 'Dataset Terbaru',
        upload_recent_sub   : 'Klik dataset sebelumnya untuk memuat ulang analisisnya secara instan.',
        upload_search_ph    : 'Cari dataset...',
        upload_empty_title  : 'Belum ada dataset',
        upload_empty_desc   : 'Belum ada dataset. Unggah dataset pertama Anda untuk memulai.',
        upload_badge        : 'Dianalisis',
        upload_fi_name      : 'Nama File',
        upload_fi_size      : 'Ukuran File',
        upload_fi_format    : 'Format',
    },
};

function applyLanguage(lang) {
    document.body.setAttribute('data-lang', lang);
    var t = TRANSLATIONS[lang];
    if (!t) return;

    /* 1. data-translate attributes */
    document.querySelectorAll('[data-translate]').forEach(function (el) {
        var key = el.getAttribute('data-translate');
        if (t[key] !== undefined) el.textContent = t[key];
    });

    /* Apply data-translate backward compat for current language */
    document.querySelectorAll('[data-translate]').forEach(function (el) {
        var key = el.getAttribute('data-translate');
        var translated = (typeof I18N !== 'undefined' ? I18N.t(key) : key);
        if (translated !== key) el.innerHTML = translated;
    });

    /* 1b. data-translate-placeholder for input placeholders */
    document.querySelectorAll('[data-translate-placeholder]').forEach(function (el) {
        var key = el.getAttribute('data-translate-placeholder');
        if (t[key] !== undefined) el.setAttribute('placeholder', t[key]);
    });

    /* 2. Re-render insights in the selected language */
    if (typeof window._insightsRender === 'function') {
        window._insightsRender(lang);
    }
    if (typeof renderInsights === 'function') {
        renderInsights(lang);
    }
    if (typeof renderKeyFindings === 'function') {
        renderKeyFindings(lang);
    }

    /* 3. Sidebar section labels */
    var sectionMap = {
        'MAIN'         : t.nav_main,
        'DATA'         : t.nav_data,
        'STATISTICS'   : t.nav_stats,
        'VISUALIZATIONS': t.nav_viz,
        'TIME SERIES'  : t.nav_ts,
        'INSIGHTS'     : t.nav_insights,
        'REPORTING'    : t.nav_reporting,
    };
    document.querySelectorAll('.nav-section-label').forEach(function(el) {
        var txt = el.textContent.trim();
        if (sectionMap[txt]) el.textContent = sectionMap[txt];
    });

    /* 4. Sidebar nav items via data-translate-nav */
    var navMap = {
        'menu-overview'   : t.nav_dashboard,
        'menu-upload'     : t.nav_upload,
        'menu-preview'    : t.nav_preview,
        'menu-cleaning'   : t.nav_cleaning,
        'menu-stats-acc'  : t.nav_statistics,
        'menu-numerical'  : t.nav_numerical,
        'menu-categorical': t.nav_categorical,
        'menu-advanced'   : t.nav_advanced,
        'menu-visualizations': t.nav_visualizations,
        'menu-timeseries' : t.nav_timeseries,
        'menu-ts-overview': t.nav_ts_overview,
        'menu-ts-line'    : t.nav_ts_line,
        'menu-ts-trend'   : t.nav_ts_trend,
        'menu-ts-ma'      : t.nav_ts_ma,
        'menu-ts-rolling' : t.nav_ts_rolling,
        'menu-insights'   : t.nav_smart_insights,
        'menu-reporting'  : t.nav_reporting_sys,
        'menu-report-pdf' : t.nav_dl_pdf,
        'menu-report-html': t.nav_dl_html,
        'menu-export-excel': t.nav_exp_excel,
        'menu-export-csv' : t.nav_exp_csv,
    };
    Object.keys(navMap).forEach(function(id) {
        var el = document.getElementById(id);
        if (!el || !navMap[id]) return;
        var labelEl = el.querySelector('.nav-label');
        if (labelEl) labelEl.textContent = navMap[id];
    });

    localStorage.setItem('ds-lang', lang);

    /* Keep selector in sync */
    var sel = document.getElementById('lang-selector');
    if (sel) sel.value = lang;
}

function initLanguageSelector() {
    var sel = document.getElementById('lang-selector');
    if (!sel) return;
    var saved = localStorage.getItem('ds-lang') || 'en';
    sel.value = saved;
    applyLanguage(saved);
    sel.addEventListener('change', function () { applyLanguage(sel.value); });
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
                autoWidth  : false,
                deferRender: true,
                drawCallback: function () {
                    this.api().columns.adjust();
                },
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
    adjustResponsiveTables();
}

function adjustResponsiveTables() {
    document.querySelectorAll('.table-scroll-wrapper table, table.data-table, table.simple-table').forEach(function (table) {
        table.style.tableLayout = 'auto';
        table.style.width = 'max-content';
        table.style.minWidth = '100%';
    });

    if (typeof $ !== 'undefined' && $.fn && $.fn.DataTable) {
        $.fn.dataTable.tables({ visible: true, api: true }).columns.adjust();
    }
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
        adjustResponsiveTables();
    }, 400);
});

window.addEventListener('resize', function () {
    clearTimeout(window.__dsTableResizeTimer);
    window.__dsTableResizeTimer = setTimeout(adjustResponsiveTables, 160);
});

// (removed duplicate dashboardOverview.js block from script.js; now loaded via dashboardOverview.js file)

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

