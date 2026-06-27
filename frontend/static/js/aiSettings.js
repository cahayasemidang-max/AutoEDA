/* ============================================================
   DS Generator — aiSettings.js
   Dashboard Settings & AI Interpretation functionality
   ============================================================ */

/* ─── DASHBOARD SETTINGS MODAL ────────────────────────────── */

function openSettingsModal() {
    var modal = document.getElementById('settingsModal');
    if (modal) {
        modal.classList.add('open');
        loadDashboardSettings();
    }
}

function closeSettingsModal() {
    var modal = document.getElementById('settingsModal');
    if (modal) modal.classList.remove('open');
}

function loadDashboardSettings() {
    var lang = localStorage.getItem('ds-lang') || 'en';
    var theme = localStorage.getItem('ds-theme') || 'system';

    var langSelect = document.getElementById('settings-language');
    var themeSelect = document.getElementById('settings-theme');

    if (langSelect) langSelect.value = lang;
    if (themeSelect) themeSelect.value = theme;
}

function saveDashboardSettings() {
    var langSelect = document.getElementById('settings-language');
    var themeSelect = document.getElementById('settings-theme');

    var lang = langSelect ? langSelect.value : 'en';
    var theme = themeSelect ? themeSelect.value : 'system';

    localStorage.setItem('ds-lang', lang);
    localStorage.setItem('ds-theme', theme);

    applyThemeSetting(theme);
    applyLanguageSetting(lang);

    if (typeof showToast === 'function') {
        showToast('Dashboard settings saved.', 'success');
    }
    closeSettingsModal();
}

function applyThemeSetting(theme) {
    var isDark;
    if (theme === 'dark') {
        isDark = true;
    } else if (theme === 'light') {
        isDark = false;
    } else {
        isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    }
    document.body.classList.toggle('dark-theme', isDark);
    var icon = document.getElementById('theme-icon');
    if (icon) {
        icon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    }
}

function applyLanguageSetting(lang) {
    if (typeof window._insightsRender === 'function') {
        window._insightsRender('id');
    }
}

/* Close modal on overlay click & Escape */
document.addEventListener('DOMContentLoaded', function () {
    var modal = document.getElementById('settingsModal');
    if (modal) {
        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeSettingsModal();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.classList.contains('open')) {
                closeSettingsModal();
            }
        });
    }
});

/* ─── INTERPRETATION AUTO-GENERATE ───────────────────────── */

var _interpretationGenerated = false;

function autoGenerateInterpretation() {
    var filename = getFileName();
    if (!filename) return;
    var resultEl = document.getElementById('interpretation-result');
    if (resultEl && resultEl.style.display === 'block') return;

    // Check for pre-loaded data before making API call
    var preloadedScript = document.getElementById('ai-interpretation-data');
    if (preloadedScript) {
        try {
            var preloaded = JSON.parse(preloadedScript.textContent || preloadedScript.innerText);
            if (preloaded && typeof preloaded === 'object' && preloaded.summary) {
                var emptyState = document.getElementById('interpretation-empty');
                var loadingState = document.getElementById('interpretation-loading');
                if (emptyState) emptyState.style.display = 'none';
                if (loadingState) loadingState.style.display = 'none';
                renderInterpretationResult(preloaded);
                if (resultEl) resultEl.style.display = 'block';
                _interpretationGenerated = true;
                return;
            }
        } catch(e) { /* ignore */ }
    }

    generateInterpretation();
}

function generateInterpretation() {
    var filename = getFileName();
    if (!filename) {
        if (typeof showToast === 'function') showToast('No active dataset.', 'error');
        return;
    }

    var emptyState = document.getElementById('interpretation-empty');
    var loadingState = document.getElementById('interpretation-loading');
    var resultState = document.getElementById('interpretation-result');
    var quotaState = document.getElementById('interpretation-quota');

    if (emptyState) emptyState.style.display = 'none';
    if (resultState) resultState.style.display = 'none';
    if (quotaState) quotaState.style.display = 'none';
    if (loadingState) loadingState.style.display = 'flex';

    // Check for pre-loaded AI interpretation data (e.g. in exported HTML report)
    var preloadedScript = document.getElementById('ai-interpretation-data');
    if (preloadedScript) {
        try {
            var preloaded = JSON.parse(preloadedScript.textContent || preloadedScript.innerText);
            if (preloaded && typeof preloaded === 'object' && preloaded.summary) {
                if (loadingState) loadingState.style.display = 'none';
                renderInterpretationResult(preloaded);
                if (resultState) resultState.style.display = 'block';
                _interpretationGenerated = true;
                return;
            }
        } catch(e) { /* ignore parse errors */ }
    }

    var lang = 'id';

    fetch('/api/interpretation/' + encodeURIComponent(filename) + '?lang=' + lang, {
        method: 'POST',
    })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (loadingState) loadingState.style.display = 'none';

            if (data.ok && data.data) {
                renderInterpretationResult(data.data);
                if (resultState) resultState.style.display = 'block';
                _interpretationGenerated = true;
            } else if (data.error === 'no_api_key') {
                if (emptyState) emptyState.style.display = 'flex';
                if (typeof showToast === 'function') {
                    showToast('AI API key not configured. Check your .env file.', 'warning');
                }
            } else if (data.error === 'quota_exceeded') {
                if (quotaState) {
                    var msgEl = document.getElementById('interpretation-quota-message');
                    var resetEl = document.getElementById('interpretation-quota-reset');
                    if (msgEl) msgEl.textContent = data.message || 'Kuota gratis harian telah habis.';
                    if (resetEl && data.reset_in_seconds) {
                        var hours = Math.floor(data.reset_in_seconds / 3600);
                        var minutes = Math.floor((data.reset_in_seconds % 3600) / 60);
                        resetEl.textContent = 'Reset dalam ' + hours + ' jam ' + minutes + ' menit';
                    }
                    quotaState.style.display = 'flex';
                }
                if (typeof showToast === 'function') {
                    showToast('Kuota gratis harian Gemini habis. Coba lagi nanti.', 'warning');
                }
            } else {
                if (emptyState) emptyState.style.display = 'flex';
                if (typeof showToast === 'function') {
                    showToast(data.error || 'Failed to generate interpretation.', 'error');
                }
            }
        })
        .catch(function (err) {
            if (loadingState) loadingState.style.display = 'none';
            if (emptyState) emptyState.style.display = 'flex';
            if (typeof showToast === 'function') {
                showToast('Network error: ' + err.message, 'error');
            }
        });
}

function _fmt(text) {
    return (text || '').replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
}

function renderInterpretationResult(data) {
    var summaryEl = document.getElementById('interpretation-summary-text');
    var findingsEl = document.getElementById('interpretation-findings-list');
    var recommendationsEl = document.getElementById('interpretation-recommendations-list');
    var conclusionEl = document.getElementById('interpretation-conclusion-text');

    if (summaryEl) summaryEl.innerHTML = _fmt(data.summary);
    if (conclusionEl) conclusionEl.innerHTML = _fmt(data.conclusion);

    if (findingsEl) {
        findingsEl.innerHTML = '';
        if (data.key_findings && data.key_findings.length > 0) {
            data.key_findings.forEach(function (f) {
                var li = document.createElement('li');
                li.innerHTML = _fmt(f);
                findingsEl.appendChild(li);
            });
        }
    }

    if (recommendationsEl) {
        recommendationsEl.innerHTML = '';
        if (data.recommendations && data.recommendations.length > 0) {
            data.recommendations.forEach(function (r) {
                var li = document.createElement('li');
                li.innerHTML = _fmt(r);
                recommendationsEl.appendChild(li);
            });
        }
    }
}

function getFileName() {
    if (typeof vizMeta !== 'undefined' && vizMeta.filename) return vizMeta.filename;
    return null;
}
