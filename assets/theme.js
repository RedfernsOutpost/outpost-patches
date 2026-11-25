/* Light or dark. Loaded in every page's <head>, before anything is drawn, so a saved choice
   never flashes the other theme first. With no saved choice the page follows the device
   setting (prefers-color-scheme, in site.css). The header button saves a choice in this
   browser only (localStorage), and storage that's blocked or full is simply skipped. */
(function () {
  var KEY = "theme";
  var root = document.documentElement;

  function saved() {
    try {
      var t = localStorage.getItem(KEY);
      return t === "light" || t === "dark" ? t : null;
    } catch (err) {
      return null;
    }
  }

  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  function current() {
    return root.dataset.theme || (media && media.matches ? "light" : "dark");
  }

  var choice = saved();
  if (choice) root.dataset.theme = choice;

  var SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/></svg>';
  var MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.6A8.5 8.5 0 0 1 9.4 3.5a8.5 8.5 0 1 0 11.1 11.1z"/></svg>';

  function label(button) {
    var next = current() === "light" ? "dark" : "light";
    button.innerHTML = next === "light" ? SUN : MOON; // fixed icons above, never page data
    button.setAttribute("aria-label", "Switch to " + next + " mode");
    button.title = "Switch to " + next + " mode";
  }

  function addButton() {
    var bar = document.querySelector(".topbar .wrap");
    if (!bar || bar.querySelector(".theme-toggle")) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "theme-toggle";
    label(button);
    button.addEventListener("click", function () {
      var next = current() === "light" ? "dark" : "light";
      root.dataset.theme = next;
      try {
        localStorage.setItem(KEY, next);
      } catch (err) {
        /* private mode or storage off: the change still applies to this page */
      }
      label(button);
    });
    if (media && media.addEventListener) {
      media.addEventListener("change", function () { label(button); });
    }
    bar.appendChild(button);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", addButton);
  else addButton();
})();
