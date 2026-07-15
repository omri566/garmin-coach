/* Make the floating coach button draggable, and remember where you put it.
 *
 * The button (#gc-coach-fab) is also the Popover target that opens the tips, so
 * we distinguish a TAP (open tips) from a DRAG (reposition). Getting this right
 * on touch matters: a finger tap always jitters a few pixels, so we only begin a
 * drag once the pointer has clearly moved (DRAG_THRESH), and we only swallow the
 * click that follows a *real* drag. A clean tap always falls through to the
 * button's click → the Dash callback opens the tips. Pointer events (mouse+touch).
 */
(function () {
  var DRAG_THRESH = 12;    // px of movement before a press becomes a drag
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

    var startX, startY, baseLeft, baseTop, pointerId;
    var pressing = false;   // pointer is down on the button
    var dragging = false;   // movement passed the threshold — now repositioning

    fab.addEventListener("pointerdown", function (e) {
      if (e.button !== undefined && e.button !== 0) return;
      pressing = true; dragging = false; pointerId = e.pointerId;
      startX = e.clientX; startY = e.clientY;
      var r = dock.getBoundingClientRect();
      baseLeft = r.left; baseTop = r.top;
      // Do NOT capture the pointer yet — capturing on a plain tap can eat the
      // click on some touch browsers. Capture only once a drag actually starts.
    });

    fab.addEventListener("pointermove", function (e) {
      if (!pressing) return;
      var dx = e.clientX - startX, dy = e.clientY - startY;
      if (!dragging) {
        if (Math.hypot(dx, dy) < DRAG_THRESH) return;   // still a tap so far
        dragging = true;
        try { fab.setPointerCapture(pointerId); } catch (x) {}
      }
      applyPos(dock,
        clamp(baseLeft + dx, window.innerWidth - dock.offsetWidth),
        clamp(baseTop + dy, window.innerHeight - dock.offsetHeight));
    });

    function end() {
      if (!pressing) return;
      pressing = false;
      if (dragging) {
        try { fab.releasePointerCapture(pointerId); } catch (x) {}
        var r = dock.getBoundingClientRect();
        try { localStorage.setItem(KEY, JSON.stringify({ left: r.left, top: r.top })); } catch (x) {}
        fab.dataset.suppressClick = "1";           // this press was a drag, not a tap
        setTimeout(function () { delete fab.dataset.suppressClick; }, 400);  // safety
      }
      dragging = false;
    }
    fab.addEventListener("pointerup", end);
    fab.addEventListener("pointercancel", end);

    // Capture phase: only kill the click that immediately follows a real drag.
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
