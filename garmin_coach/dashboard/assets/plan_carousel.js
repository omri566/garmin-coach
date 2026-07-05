/* Smooth single-week carousel for the plan.
   All weeks are rendered side-by-side in #plan-week-track; the arrows just slide
   the track with a CSS transform (no server round-trip) and set the viewport
   height to the active week so it animates smoothly and never leaves empty space
   or clips a taller week. */
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
    if (first) port.style.transition = "none"; // no settle animation on first paint
    port.style.height = h + "px";
    if (first) {
      void port.offsetHeight; // flush, then re-enable the height transition
      port.style.transition = "";
      port.dataset.gcInit = "1";
    }
  }
  window.gcApplyWeek = apply;

  // Keep the height correct if the window is resized while a week is shown.
  window.addEventListener("resize", function () {
    var track = document.getElementById("plan-week-track");
    if (track && track.dataset.idx != null) apply(parseInt(track.dataset.idx, 10));
  });
})();
