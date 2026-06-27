// Sidebar accordion fix for Visualizations & Descriptive Statistics
// Purpose: provide toggleAccordion(accId) and ensure submenu elements are shown/hidden.

(function () {
  'use strict';

  // Polyfill CSS.escape for older browsers
  if (!CSS.escape) {
    CSS.escape = function(value) {
      if (typeof value !== 'string') {
        value = String(value);
      }
      var length = value.length;
      var result = '';
      for (var i = 0; i < length; i++) {
        var ch = value.charAt(i);
        var code = value.charCodeAt(i);
        // Alpanumeric stays as-is
        if ((code >= 0x30 && code <= 0x39) || // 0-9
            (code >= 0x41 && code <= 0x5A) || // A-Z
            (code >= 0x61 && code <= 0x7A)) {  // a-z
          result += ch;
        } else {
          result += '\\' + code.toString(16) + ' ';
        }
      }
      return result;
    };
  }

  function toggleAccordion(accId) {
    var item = null;
    try {
      item = document.getElementById(accId);
    } catch(e) {}
    if (!item) {
      try {
        item = document.querySelector('.nav-accordion-item#' + CSS.escape(accId));
      } catch(e) {}
    }

    if (item) {
      item.classList.toggle('open');
      var body = null;
      try {
        body = item.querySelector('.nav-accordion-body');
      } catch(e) {}
      if (body) {
        var isOpen = item.classList.contains('open');
        body.style.display = isOpen ? 'block' : 'none';
        var innerLis = body.querySelectorAll('li');
        innerLis.forEach(function (li) {
          li.style.display = isOpen ? '' : 'none';
        });
      }
      return true;
    }

    // 2) Fallback: try toggling nested submenu container by finding the trigger button
    var any = null;
    try {
      any = document.querySelector('[onclick*="' + accId + '"]');
    } catch(e) {}
    if (!any) return false;

    var parent = null;
    try {
      parent = any.closest('li');
    } catch(e) {}
    if (parent) {
      var target = null;
      try {
        target = parent.querySelector('.nav-accordion-body') || parent.querySelector('.sub-menu') || parent.querySelector('ul');
      } catch(e) {}
      if (target) {
        var show = false;
        try {
          show = getComputedStyle(target).display === 'none';
        } catch(e) {
          show = target.style.display === 'none';
        }
        target.style.display = show ? 'block' : 'none';
        return true;
      }
    }

    return false;
  }

  window.toggleAccordion = toggleAccordion;
})();
