/* 'Coach says' popup: tapping a topic chip swaps the single message in place.
 * Pure client-side (no server round-trip) — the messages are all present as
 * data-h / data-p on the chips, rendered when the popup opened. Event delegation
 * on document so it keeps working after Dash re-renders the popup body. */
(function () {
  document.addEventListener("click", function (e) {
    var chip = e.target.closest && e.target.closest(".gc-says-chip");
    if (!chip) return;
    var wrap = chip.closest("#gc-coach-says") || document;
    var chips = wrap.querySelectorAll(".gc-says-chip");
    for (var i = 0; i < chips.length; i++) chips[i].classList.remove("on");
    chip.classList.add("on");
    var h = wrap.querySelector("#gc-says-h");
    var p = wrap.querySelector("#gc-says-p");
    if (h) h.textContent = chip.getAttribute("data-h") || "";
    if (p) p.textContent = chip.getAttribute("data-p") || "";
  });
})();
