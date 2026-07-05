/* Smooth single-week carousel for the plan.
   All weeks are rendered side-by-side in #plan-week-track; the arrows just slide
   the track with a CSS transform (no server round-trip) and set the viewport
   height to the active week so it animates smoothly without empty space or
   clipping. Callback functions live on the dash_clientside.gcplan namespace so
   Dash resolves them reliably (inline function strings can misbehave). */
(function () {
  function apply(idx) {
    var track = document.getElementById("plan-week-track");
    var port = document.getElementById("plan-week-body");
    if (!track || !port || !track.children.length) return;
    idx = Math.max(0, Math.min(track.children.length - 1, idx | 0));
    track.dataset.idx = idx;

    var slide = track.children[idx];
    var h = slide.getBoundingClientRect().height;
    track.style.transform = "translateX(" + (-idx * 100) + "%)";
    // While the Coach tab is hidden (display:none) the slide measures 0 — leave
    // the height auto until it's visible (re-applied on tab show / nav).
    if (h <= 0) return;
    var first = !port.dataset.gcInit;
    if (first) port.style.transition = "none";
    port.style.height = h + "px";
    if (first) {
      void port.offsetHeight;
      port.style.transition = "";
      port.dataset.gcInit = "1";
    }
  }

  function applySoon(idx) {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { apply(idx); });
    });
  }

  window.gcApplyWeek = apply;
  window.addEventListener("resize", function () {
    var track = document.getElementById("plan-week-track");
    if (track && track.dataset.idx != null) apply(parseInt(track.dataset.idx, 10));
  });

  window.dash_clientside = window.dash_clientside || {};
  window.dash_clientside.gcplan = {
    // Arrow click → slide + resize, entirely client-side.
    nav: function (prevN, nextN, data) {
      data = data || { idx: 0, n: 1, np: 0, nn: 0 };
      var idx = data.idx | 0, n = (data.n | 0) || 1, np = data.np | 0, nn = data.nn | 0;
      if ((prevN || 0) > np) idx = Math.max(0, idx - 1);
      else if ((nextN || 0) > nn) idx = Math.min(n - 1, idx + 1);
      apply(idx);
      return { idx: idx, n: n, np: (prevN || 0), nn: (nextN || 0) };
    },
    // Track (re-)rendered: initial load and after an edit.
    reapply: function (_children, data) {
      applySoon(data && data.idx ? data.idx : 0);
      return window.dash_clientside.no_update;
    },
    // Coach tab became visible → the viewport can finally be measured.
    onTab: function (style, data) {
      if (!(style && style.display === "none")) {
        applySoon(data && data.idx ? data.idx : 0);
      }
      return window.dash_clientside.no_update;
    },
  };
})();
