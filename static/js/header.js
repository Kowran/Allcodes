/* Mobile hamburger menu (header) */
(function () {
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  ready(function () {
    var toggle = document.querySelector('.menu-toggle');
    var menuId = toggle && toggle.getAttribute('aria-controls');
    var menu = menuId ? document.getElementById(menuId) : null;
    var backdrop = document.querySelector('[data-menu-backdrop]');

    if (!toggle || !menu) return;

    function isOpen() {
      return document.body.classList.contains('menu-open');
    }

    function setExpanded(val) {
      toggle.setAttribute('aria-expanded', val ? 'true' : 'false');
    }

    function openMenu() {
      document.body.classList.add('menu-open');
      setExpanded(true);

      // Move focus inside the drawer (nice for accessibility)
      var focusable = menu.querySelector('a, button, select, input, [tabindex]:not([tabindex="-1"])');
      if (focusable && typeof focusable.focus === 'function') {
        focusable.focus();
      }
    }

    function closeMenu() {
      document.body.classList.remove('menu-open');
      setExpanded(false);

      // Return focus to the toggle button
      if (typeof toggle.focus === 'function') {
        toggle.focus();
      }
    }

    toggle.addEventListener('click', function () {
      if (isOpen()) closeMenu();
      else openMenu();
    });

    if (backdrop) {
      backdrop.addEventListener('click', closeMenu);
    }

    // Close on ESC
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) {
        closeMenu();
      }
    });

    // Close when clicking a link inside the menu
    menu.addEventListener('click', function (e) {
      var target = e.target;
      if (!target) return;

      // If a link was clicked, close (useful if you later add internal links)
      var link = target.closest && target.closest('a');
      if (link) {
        closeMenu();
      }
    });

    // If we resize to desktop, ensure the drawer state is reset
    if (window.matchMedia) {
      var mq = window.matchMedia('(max-width: 600px)');
      var onChange = function (ev) {
        if (!ev.matches) {
          // leaving mobile breakpoint
          document.body.classList.remove('menu-open');
          setExpanded(false);
        }
      };

      if (typeof mq.addEventListener === 'function') {
        mq.addEventListener('change', onChange);
      } else if (typeof mq.addListener === 'function') {
        mq.addListener(onChange);
      }
    }
  });
})();
