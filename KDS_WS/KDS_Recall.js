const wsHost = window.location.hostname;
const ws = new WebSocket(`ws://${wsHost}:9998`);
const recallContainer = document.getElementById("recall-container");

// ------------------ WebSocket Setup ------------------
ws.onopen = () => {
  const kdsName = localStorage.getItem("kds_name") || "NONE";
  ws.send(JSON.stringify({ action: "init_kds_recall", kds_name: kdsName }));
};

// ------------------ Render Tickets ------------------
function renderRecallTickets(tickets) {
  recallContainer.innerHTML = "";

  tickets.forEach((ticket) => {
    const ticketEl = document.createElement("div");
    ticketEl.classList.add("ticket");

    // ---------- Ticket Header with checkbox on RIGHT ----------
    const header = document.createElement("div");
    header.classList.add("ticket-header");

    header.innerHTML = `
      <div class="ticket-info">#${ticket.kot_no} | ${ticket.bill_type} ${ticket.table_no}</div>
      <div class="ticket-select">
        <input type="checkbox" class="select-all" />
      </div>
    `;
    ticketEl.appendChild(header);

    // ---------- Ticket Items ----------
    const itemsDiv = document.createElement("div");
    itemsDiv.classList.add("ticket-items");
    ticket.items.forEach((item) => {
      const itemDiv = document.createElement("div");
      itemDiv.classList.add("ticket-item");
      // If item.status === "ready", add class for green bg
      let itemBg = "#f8d7da"; // default red/pending
      if (item.status === "Delivered") itemBg = "#cce5ff"; // blue for delivered
      else if (item.status === "Ready")
        itemBg = "#d4edda"; // green like KDS_DEL
      else if (Number(item.ready_status) === 1) itemBg = "#fff3cd"; // yellow for partial

      itemDiv.style.background = itemBg;

      itemDiv.innerHTML = `
        <div class="item-name">${item.name}</div>
        <div class="item-qty">${item.qty}</div>
        <input type="checkbox" class="item-check"
          data-kot="${ticket.kot_no}"
          data-bill="${ticket.bill_no}"
          data-icode="${item.i_code}" />
      `;
      itemsDiv.appendChild(itemDiv);
    });

    ticketEl.appendChild(itemsDiv);

    // ---------- Recall Button ----------
    const recallBtn = document.createElement("button");
    recallBtn.textContent = "Recall Selected";
    recallBtn.onclick = () => {
      const selected = itemsDiv.querySelectorAll(".item-check:checked");
      if (selected.length === 0) return;
      showPopup("Items Recalled", 3000);
      selected.forEach((cb) => {
        ws.send(
          JSON.stringify({
            action: "recall_item",
            kot_no: cb.dataset.kot,
            bill_no: cb.dataset.bill,
            i_code: cb.dataset.icode,
          })
        );
      });
    };
    ticketEl.appendChild(recallBtn);

    // ---------- Checkbox Logic ----------
    header.querySelector(".select-all").onclick = (e) => {
      const checked = e.target.checked;
      itemsDiv.querySelectorAll(".item-check").forEach((cb) => {
        cb.checked = checked;
      });
    };

    recallContainer.appendChild(ticketEl);
  });
}

// ==================== 7. UI Helpers ====================
let popupTimer = null;
function showPopup(text, duration = 3000) {
  let popup = document.getElementById("kds-popup");
  if (!popup) {
    popup = document.createElement("div");
    popup.id = "kds-popup";
    document.body.appendChild(popup);
  }
  popup.textContent = text;
  popup.classList.add("visible");

  if (popupTimer) clearTimeout(popupTimer);
  popupTimer = setTimeout(() => {
    popup.classList.remove("visible");
    popupTimer = null;
  }, duration);
}

// ------------------ WebSocket Messages ------------------
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  // Always update tickets if delivered_tickets received
  if (data.delivered_tickets) {
    renderRecallTickets(data.delivered_tickets);
  }
};

// ------------------ Auto-Reconnect if WS Closes ------------------
ws.onclose = () => {
  console.warn("WebSocket closed. Reconnecting in 3s...");
  setTimeout(() => location.reload(), 3000);
};
