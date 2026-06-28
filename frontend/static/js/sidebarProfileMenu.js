(function () {
  'use strict';

  function init() {
    var btn = document.querySelector('.sp-menu-btn');
    var profile = document.querySelector('.sidebar-profile');
    if (!btn || !profile) return;

    var logoutUrl = btn.getAttribute('data-logout-url') || '/logout';
    var menu = document.createElement('div');
    menu.className = 'sp-dropdown';
    menu.innerHTML = '<a href="' + logoutUrl + '"><i class="fas fa-right-from-bracket"></i><span>Logout</span></a>';
    profile.appendChild(menu);

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      menu.classList.toggle('open');
    });

    document.addEventListener('click', function (e) {
      if (!menu.classList.contains('open')) return;
      if (!profile.contains(e.target)) {
        menu.classList.remove('open');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

