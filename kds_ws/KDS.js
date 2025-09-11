// ==================== Constants & State ====================
const STATUS_MAP = ["Pending", "Ready", "Delivered"];
let tickets = [];
let filters = { Pending: true, Ready: true, Delivered: true };
let sortBy = "time";
let lastTicketIds = new Set();
let currentView = "KOT"; // "KOT" or "ITEM"

// ==================== Elements ====================
const ticketContainer = document.getElementById("tickets");
const foodSummaryEl = document.getElementById("food-summary");
const sound = document.getElementById("new-ticket-sound");

// ==================== Clock ====================
function startClock() {
  const clockEl = document.getElementById("clock");
  setInterval(() => {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString();
  }, 1000);
}
startClock();

// ==================== WebSocket ====================
const wsHost = window.location.hostname; // automatically gets IP on other PCs
const ws = new WebSocket(`ws://${wsHost}:9998`);
ws.onopen = () => console.log("✅ WS Connected");

ws.onmessage = (msg) => {
  const data = JSON.parse(msg.data);
  const ticketsData = data.tickets || [];
  const summaryData = data.summary || [];

  tickets = ticketsData;
  renderTickets();

  foodSummaryEl.innerHTML = summaryData
    .map(
      (item) =>
        `<div class="food-item">
           <span class="food-name">${item.name}</span>
           <span class="food-qty">${item.qty}</span>
         </div>`
    )
    .join("");

  const currentIds = new Set(ticketsData.map((t) => t.kot_no));
  const newTickets = ticketsData.filter((t) => !lastTicketIds.has(t.kot_no));
  if (newTickets.length > 0) {
    try {
      sound.play();
    } catch {}
  }
  lastTicketIds = currentIds;
};

// ==================== Filters ====================
document.querySelectorAll("#filter-checkboxes input").forEach((cb) => {
  cb.addEventListener("change", () => {
    filters[cb.value] = cb.checked;
    renderTickets();
  });
});

// ==================== Sorting ====================
document.getElementById("sort-time").addEventListener("click", () => {
  sortBy = "time";
  renderTickets();
});
document.getElementById("sort-table").addEventListener("click", () => {
  sortBy = "table";
  renderTickets();
});

// ==================== View Toggle ====================
document.getElementById("view-kot").addEventListener("click", () => {
  currentView = "KOT";
  document.getElementById("view-kot").classList.add("active");
  document.getElementById("view-item").classList.remove("active");
  renderTickets();
});
document.getElementById("view-item").addEventListener("click", () => {
  currentView = "ITEM";
  document.getElementById("view-item").classList.add("active");
  document.getElementById("view-kot").classList.remove("active");
  renderTickets();
});

// ==================== Render Tickets ====================
function renderTickets() {
  const sorted = [...tickets];

  if (sortBy === "time")
    sorted.sort((a, b) => new Date(a.created_on) - new Date(b.created_on));
  if (sortBy === "table") sorted.sort((a, b) => a.table_no - b.table_no);

  ticketContainer.innerHTML = "";

  sorted.forEach((ticket) => {
    const filteredItems = ticket.items.filter((it) => filters[it.status]);
    if (filteredItems.length === 0) return;

    // ITEM View: create separate tickets for each item
    const itemsToRender =
      currentView === "ITEM" ? filteredItems : [filteredItems];

    itemsToRender.forEach((itemArr) => {
      const ticketEl = document.createElement("div");
      ticketEl.className = "ticket";
      ticketEl.dataset.kot = ticket.kot_no;
      ticketEl.dataset.bill = ticket.bill_no ?? "";

      // Set ticket CSS based on ack_status
      const allAck = ticket.items.every((it) => it.ack_status === 1);
      ticketEl.id = allAck ? "ticket_accepted" : "ticket_new";

      // ITEM view: only show 1 item
      const itemsHtml = (currentView === "ITEM" ? [itemArr] : itemArr)
        .map((it) => {
          const commentText = it.comment || ticket.Comments || ""; // fetch item-level comment or KOT-level comment
          return `<div class="ticket-item">
                <div class="item-name">
                  ${it.name}
                  ${
                    commentText
                      ? `<span class="item-comment">${
                          commentText === "spicy" ? "🌶🌶" : commentText
                        }</span>`
                      : ""
                  }
                </div>
                <div>${it.qty}</div>
                <div class="item-status" onclick="toggleItem('${
                  ticket.kot_no
                }','${ticket.bill_no}','${it.i_code}')">
                  ${
                    it.status === "Pending"
                      ? "⏳"
                      : it.status === "Ready"
                      ? "✅"
                      : "📦"
                  }
                </div>
              </div>`;
        })
        .join("");

      ticketEl.innerHTML = `
        <div class="ticket-header">
          <div>#${ticket.kot_no} | Tbl ${ticket.table_no}</div>
          <div class="ticket-timer">00:00</div>
        </div>
        <div class="ticket-items">${itemsHtml}</div>
      `;

      ticketContainer.appendChild(ticketEl);

      // ==================== Ticket Click for ACK ====================
      ticketEl.addEventListener("click", (e) => {
        if (e.target.classList.contains("item-status")) return; // skip item clicks

        ticket.items.forEach((it) => (it.ack_status = 1));
        ticketEl.id = "ticket_accepted"; // update CSS immediately

        ws.send(
          JSON.stringify({
            action: "ack_ticket",
            kot_no: ticket.kot_no,
            bill_no: ticket.bill_no ?? "",
          })
        );
      });

      const timerEl = ticketEl.querySelector(".ticket-timer");
      const updateTimer = () => {
        const createdTime = new Date(ticket.created_on);
        const diffMs = new Date() - createdTime;
        const minutes = Math.floor(diffMs / 60000);
        const seconds = Math.floor((diffMs % 60000) / 1000);
        timerEl.textContent = `${minutes.toString().padStart(2, "0")}:${seconds
          .toString()
          .padStart(2, "0")}`;

        let color = "grey";
        if (minutes > 10) color = "#e0474c";
        else if (minutes > 5) color = "#f97316";

        ticketEl.querySelector(".ticket-header").style.background = color;
        ticketEl.style.border = `1px solid ${color}`;
      };

      updateTimer();
      setInterval(updateTimer, 1000);
    });
  });
}

// ==================== Toggle Item ====================
function toggleItem(kot_no, bill_no, i_code) {
  ws.send(JSON.stringify({ action: "toggle_item", kot_no, bill_no, i_code }));
}
