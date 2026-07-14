/* Make the floating coach button draggable, and remember where you put it.
 *
 * The button (#gc-coach-fab) is also the Popover target that opens the tips, so
 * we distinguish a tap (open tips) from a drag (reposition): once the pointer
 * moves past a small threshold we treat it as a drag, move the dock
 * (#gc-coach-dock), persist the spot to localStorage, and swallow the click that
 * follows so the tips don't pop open. Uses pointer events (mouse + touch). */
(function () {
  var THRESH = 6;          // px of movement before it counts as a drag
  var KEY = "gc-coach-pos";

  function applyPos(dock, left, top) {
    dock.style.left = left + "px";
    dock.style.top = top + "px";
    dock.style.right = "auto";
    dock.style.bottom = "auto";
  }

  function clamp(v, max) { return Math.max(4, Math.min(v, max - 4)); }

  function init() {
    var dock = document.getElementById("gc-coach-dock");
    var fab = document.getElementById("gc-coach-fab");
    if (!dock || !fab || dock.dataset.dragInit) return;
    dock.dataset.dragInit = "1";

    try {
      var saved = JSON.parse(localStorage.getItem(KEY) || "null");
      if (saved && typeof saved.left === "number") applyPos(dock, saved.left, saved.top);
    } catch (e) { /* ignore bad storage */ }

    var startX, startY, baseLeft, baseTop, dragging = false, moved = false;

    fab.addEventListener("pointerdown", function (e) {
      if (e.button !== undefined && e.button !== 0) return;
      dragging = true; moved = false;
      startX = e.clientX; startY = e.clientY;
      var r = dock.getBoundingClientRect();
      baseLeft = r.left; baseTop = r.top;
      try { fab.setPointerCapture(e.pointerId); } catch (x) {}
    });

    fab.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var dx = e.clientX - startX, dy = e.clientY - startY;
      if (!moved && Math.hypot(dx, dy) < THRESH) return;
      moved = true;
      applyPos(dock,
        clamp(baseLeft + dx, window.innerWidth - dock.offsetWidth),
        clamp(baseTop + dy, window.innerHeight - dock.offsetHeight));
    });

    function end(e) {
      if (!dragging) return;
      dragging = false;
      try { fab.releasePointerCapture(e.pointerId); } catch (x) {}
      if (moved) {
        var r = dock.getBoundingClientRect();
        try { localStorage.setItem(KEY, JSON.stringify({ left: r.left, top: r.top })); } catch (x) {}
        fab.dataset.suppressClick = "1";   // don't open tips after a drag
      }
    }
    fab.addEventListener("pointerup", end);
    fab.addEventListener("pointercancel", end);

    // Capture-phase: kill the post-drag click before React's onClick sees it.
    fab.addEventListener("click", function (e) {
      if (fab.dataset.suppressClick) {
        e.stopImmediatePropagation();
        e.preventDefault();
        delete fab.dataset.suppressClick;
      }
    }, true);
  }

  // Dash mounts the layout asynchronously — poll until the button exists.
  var iv = setInterval(function () {
    if (document.getElementById("gc-coach-fab")) { clearInterval(iv); init(); }
  }, 300);
  document.addEventListener("DOMContentLoaded", init);
})();
