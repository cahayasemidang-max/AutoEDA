/* ============================================================
   DS Generator — timeSeriesControls.js
   Time Series column/granularity dynamic controls
   ============================================================ */
(function () {
  'use strict';

  function reloadTimeSeries() {
    var dtCol  = document.getElementById('ts-categorical-dim')?.value;
    var numCol = document.getElementById('ts-numerical-val')?.value;
    var freq   = document.getElementById('ts-freq-select')?.value;
    var theme  = document.body.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';

    var filename = window.vizMeta?.filename;
    if (!filename) return;

    // Validasi: butuh minimal satu kolom tanggal dan satu kolom numerik
    if (!dtCol && !numCol) {
      showToast(I18N.t('ts_select_both'), 'warning');
      return;
    }
    if (!dtCol) {
      showToast(I18N.t('ts_select_date_first'), 'warning');
      return;
    }
    if (!numCol) {
      showToast(I18N.t('ts_select_numeric_first'), 'warning');
      return;
    }

    var url = '/api/ts-charts/' + encodeURIComponent(filename)
      + '?dt_col=' + encodeURIComponent(dtCol || '')
      + '&num_col=' + encodeURIComponent(numCol || '')
      + '&freq=' + encodeURIComponent(freq || '')
      + '&theme=' + theme
      + '&chart_type=ts_combined&dim_type=datetime&dim_col=' + encodeURIComponent(dtCol || '');

    showTsLoading(true);

    fetch(url)
      .then(function (r) {
        if (!r.ok) {
          throw new Error('Server returned ' + r.status + ': ' + r.statusText);
        }
        return r.json();
      })
      .then(function (data) {
        showTsLoading(false);
        if (!data.ok) {
          showToast(data.error || 'Failed to load Time Series', 'error');
          return;
        }
        if (data.chart) {
          var el = document.getElementById('plot-ts-line');
          if (el && typeof Plotly !== 'undefined') {
            var layout = Object.assign({}, data.chart.layout || {}, {
              paper_bgcolor: 'rgba(0,0,0,0)',
              plot_bgcolor: 'rgba(0,0,0,0)',
              autosize: true,
              margin: { l: 48, r: 20, t: 52, b: 48 }
            });
            Plotly.react(el, data.chart.data, layout, { responsive: true });
          }
        }
        if (data.meta) {
          updateTsCombinedKpis(data.meta);
        }
      })
      .catch(function (err) {
        showTsLoading(false);
        showToast(I18N.t('ts_load_error') + err.message, 'error');
        console.error(err);
      });
  }

  function showTsLoading(show) {
    var areas = document.querySelectorAll('#ts-line .chart-area');
    areas.forEach(function (el) {
      if (show) {
        el.style.opacity = '0.5';
        el.style.pointerEvents = 'none';
      } else {
        el.style.opacity = '1';
        el.style.pointerEvents = '';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    ['ts-categorical-dim', 'ts-numerical-val', 'ts-freq-select'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener('change', reloadTimeSeries);
    });
  });
})();
