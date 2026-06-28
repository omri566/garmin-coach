/* Native drag-and-drop for the plan week board.
   Cards are draggable; day columns are drop targets. On drop we DON'T move the
   DOM node ourselves — we just report (sessionKey -> targetDate) to a dcc.Store
   via set_props, and let Dash re-render the board authoritatively. This avoids
   the React/SortableJS DOM-desync class of bugs. Drops are constrained to the
   same week the card belongs to. */
(function () {
  let dragKey = null;
  let dragWeek = null;

  function clearHover() {
    document.querySelectorAll(".plan-daycol.drop-hover")
      .forEach((c) => c.classList.remove("drop-hover"));
  }

  document.addEventListener("dragstart", function (e) {
    const card = e.target.closest && e.target.closest('.plan-card[draggable="true"]');
    if (!card) return;
    dragKey = card.getAttribute("data-key");
    dragWeek = card.getAttribute("data-week");
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", dragKey); } catch (_) {}
    card.classList.add("dragging");
  });

  document.addEventListener("dragend", function (e) {
    const card = e.target.closest && e.target.closest(".plan-card");
    if (card) card.classList.remove("dragging");
    clearHover();
    dragKey = null;
    dragWeek = null;
  });

  document.addEventListener("dragover", function (e) {
    if (dragKey === null) return;
    const col = e.target.closest && e.target.closest('.plan-daycol[data-editable="1"]');
    if (!col || col.getAttribute("data-week") !== dragWeek) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (!col.classList.contains("drop-hover")) {
      clearHover();
      col.classList.add("drop-hover");
    }
  });

  document.addEventListener("drop", function (e) {
    if (dragKey === null) return;
    const col = e.target.closest && e.target.closest('.plan-daycol[data-editable="1"]');
    if (!col || col.getAttribute("data-week") !== dragWeek) return;
    e.preventDefault();
    const key = dragKey;
    const date = col.getAttribute("data-date");
    clearHover();
    dragKey = null;
    dragWeek = null;
    if (window.dash_clientside && window.dash_clientside.set_props) {
      window.dash_clientside.set_props("plan-dnd-store",
        { data: { key: key, date: date, ts: Date.now() } });
    }
  });
})();
