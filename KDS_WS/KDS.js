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

// ==================== Live Clock ====================
function updateClock() {
  const clockEl = document.getElementById("clock");
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  clockEl.textContent = `${hh}:${mm}:${ss}`;
}
setInterval(updateClock, 1000);
updateClock();

// ==================== WebSocket ====================
const wsHost = window.location.hostname; // automatically gets IP on other PCs
const ws = new WebSocket(`ws://${wsHost}:9998`);
ws.onopen = () => {
  const kdsName = localStorage.getItem("kds_name") || "NONE";
  ws.send(JSON.stringify({ action: "init_kds", kds_name: kdsName }));
};

// ==================== Sidebar & Login ====================
let loggedIn = localStorage.getItem("kds_logged_in") === "true"; // persist login
let kdsName = localStorage.getItem("kds_name") || ""; // saved KDS name

const hamburger = document.getElementById("hamburger");
const sidebar = document.getElementById("sidebar");

function promptLogin() {
  const id = prompt("Enter ID:", "");
  const pwd = prompt("Enter Password:", "");
  if (id === "abc" && pwd === "abc") {
    localStorage.setItem("kds_logged_in", "true");
    loggedIn = true;
    alert("✅ Login Successful");
  } else {
    alert("❌ Wrong credentials");
  }
}

function toggleSidebar() {
  if (!loggedIn) {
    promptLogin();
    if (!loggedIn) return;
  }
  sidebar.style.left = sidebar.style.left === "0px" ? "-250px" : "0px";
}

hamburger.onclick = toggleSidebar;

// ==================== Config Modal ====================
const configBtn = document.getElementById("config");
const configModal = document.getElementById("config-modal");
const configSubmit = document.getElementById("config-submit");
const kdsInput = document.getElementById("kds-name-input");
const loginIdInput = document.getElementById("login-id");
const loginPwdInput = document.getElementById("login-pwd");

configBtn.onclick = () => {
  kdsInput.value = kdsName; // prefill current name
  configModal.style.display = "flex";
};

configSubmit.onclick = () => {
  const enteredId = loginIdInput.value.trim();
  const enteredPwd = loginPwdInput.value.trim();
  const newKds = kdsInput.value.trim();

  if (enteredId === "abc" && enteredPwd === "abc") {
    loggedIn = true;
    localStorage.setItem("kds_logged_in", "true");

    if (newKds !== "") {
      kdsName = newKds;
      localStorage.setItem("kds_name", kdsName);
      document.getElementById("current-kds").textContent = `KDS: ${kdsName}`;
      document.getElementById(
        "current-kds-sidebar"
      ).textContent = `KDS: ${kdsName}`;
    }

    alert("✅ Login Successful");
    configModal.style.display = "none";
  } else {
    alert("❌ Wrong ID or Password");
  }
};

configModal.onclick = (e) => {
  if (e.target === configModal) configModal.style.display = "none";
};

// ==================== WebSocket Message Handler ====================
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

    const itemsToRender =
      currentView === "ITEM" ? filteredItems : [filteredItems];

    itemsToRender.forEach((itemArr) => {
      const ticketEl = document.createElement("div");
      ticketEl.className = "ticket";
      ticketEl.dataset.kot = ticket.kot_no;
      ticketEl.dataset.bill = ticket.bill_no ?? "";

      const allAck = ticket.items.every((it) => it.ack_status === 1);
      ticketEl.id = allAck ? "ticket_accepted" : "ticket_new";

      const itemsHtml = (currentView === "ITEM" ? [itemArr] : itemArr)
        .map((it) => {
          const commentText = it.comment || ticket.Comments || "";
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

      ticketEl.addEventListener("click", (e) => {
        if (e.target.classList.contains("item-status")) return;

        ticket.items.forEach((it) => (it.ack_status = 1));
        ticketEl.id = "ticket_accepted";

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
