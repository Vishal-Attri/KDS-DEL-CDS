// ==================== Constants & State ====================
const STATUS_MAP = ["Pending", "Ready", "Delivered"];
let tickets = [];
// Dynamically initialize filters from checkboxes
let filters = {};
document.querySelectorAll("#filter-checkboxes input").forEach((cb) => {
  filters[cb.value] = cb.checked;
});
let sortBy = "time";
let cached_tickets = [];
let cached_summary = {};
let last_refresh_time = 0;
let sortAsc = false; // add this line

let lastTicketIds = new Set();
let currentView = "ITEM"; // "KOT" or "ITEM"

// ==================== Elements ====================
const ticketContainer = document.getElementById("tickets");
const foodSummaryEl = document.getElementById("food-summary");
const sound = document.getElementById("new-ticket-sound");
const kotCountEl = document.getElementById("kot-count");
const currentKdsSidebarEl = document.getElementById("current-kds-sidebar");

// popup timer handle
let popupTimer = null;

// ==================== Live Clock ====================
function updateClock() {
  const clockEl = document.getElementById("clock");
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  if (clockEl) clockEl.textContent = `${hh}:${mm}:${ss}`;
}
setInterval(updateClock, 1000);
updateClock();

// ==================== Sidebar & Login ====================
let loggedIn = localStorage.getItem("kds_logged_in") === "true";
let kdsName = localStorage.getItem("kds_name") || "";

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
  kdsInput.value = kdsName;
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
      if (currentKdsSidebarEl)
        currentKdsSidebarEl.textContent = `KDS: ${kdsName}`;

      // ✅ Re-send KDS name to server after login
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: "init_kds", kds_name: kdsName }));
      }
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

// ==================== UI Helpers ====================
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

function insertSummaryToggle() {
  // Insert toggle button left of filters if not already present
  const controls = document.getElementById("controls");
  if (!controls) return;
  const filterBlock = document.getElementById("filter-checkboxes");
  if (!filterBlock) return;
  if (document.getElementById("toggle-summary-btn")) return;

  const btn = document.createElement("button");
  btn.id = "toggle-summary-btn";
  btn.textContent = "Show Summary"; // start hidden
  btn.style.marginRight = "8px";
  btn.classList.remove("active"); // summary hidden => not green
  btn.onclick = () => {
    const isHidden = document.body.classList.toggle("summary-hidden");
    btn.textContent = isHidden ? "Show Summary" : "Hide Summary";
    btn.classList.toggle("active", !isHidden);
  };

  // place it just before filterBlock
  filterBlock.parentNode.insertBefore(btn, filterBlock);
}

// call once to add the button
insertSummaryToggle();

// ==================== Default States ====================
document.body.classList.add("summary-hidden"); // hide summary by default
document.getElementById("sort-time").classList.add("active"); // default sort active
document.getElementById("sort-table").classList.remove("active");
document.getElementById("sort-time").classList.add("active");
document.getElementById("sort-time").textContent = "Time⬇";

// ==================== WebSocket Message Handler ====================
let ws; // global WebSocket reference

function connectKDS() {
  const wsHost = window.location.hostname;
  ws = new WebSocket(`ws://${wsHost}:9999`);

  ws.onopen = () => {
    console.log("✅ WebSocket connected");
    kdsName = localStorage.getItem("kds_name") || "NONE";
    ws.send(JSON.stringify({ action: "init_kds", kds_name: kdsName }));

    if (currentKdsSidebarEl) {
      currentKdsSidebarEl.textContent = `KDS Name: ${kdsName}`;
    }
  };

  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    const ticketsData = (data.tickets || []).filter(
      (t) => t.kds_name === kdsName || !t.kds_name
    );
    tickets = ticketsData;
    renderTickets();

    const summaryData = data.summary || [];
    if (foodSummaryEl) {
      foodSummaryEl.innerHTML = summaryData
        .map(
          (item) =>
            `<div class="food-item">
               <span class="food-name">${item.name}</span>
               <span class="food-qty">${item.qty}</span>
             </div>`
        )
        .join("");
    }

    const currentIds = new Set(ticketsData.map((t) => t.kot_no));
    const newTickets = ticketsData.filter((t) => !lastTicketIds.has(t.kot_no));
    if (newTickets.length > 0) sound.play().catch(() => {});
    lastTicketIds = currentIds;
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
    ws.close(); // triggers onclose
  };

  ws.onclose = () => {
    console.warn("❌ WebSocket closed. Reconnecting in 3s...");
    setTimeout(connectKDS, 3000); // reconnect loop
  };
}

// Start the WebSocket
connectKDS();

// ==================== Filters ====================
document.querySelectorAll("#filter-checkboxes input").forEach((cb) => {
  cb.addEventListener("change", () => {
    filters[cb.value] = cb.checked;
    renderTickets();
  });
});

// ==================== Sorting ====================
document.getElementById("sort-time").addEventListener("click", () => {
  if (sortBy === "time") {
    sortAsc = !sortAsc; // toggle direction
  } else {
    sortBy = "time";
    sortAsc = false; // default to descending first
  }
  document.getElementById("sort-time").classList.add("active");
  document.getElementById("sort-table").classList.remove("active");
  document.getElementById("sort-time").textContent = sortAsc
    ? "Time⬆"
    : "Time⬇";
  renderTickets();
});

document.getElementById("sort-table").addEventListener("click", (e) => {
  sortBy = "table";
  document.getElementById("sort-table").classList.add("active");
  document.getElementById("sort-time").classList.remove("active");
  renderTickets();
});

// ==================== View Toggle ====================
const viewBtn = document.getElementById("view-btn");

// initialize class
viewBtn.classList.add("kot-view");
viewBtn.textContent = "Switch to KOT View";

viewBtn.addEventListener("click", () => {
  if (currentView === "KOT") {
    currentView = "ITEM";
    viewBtn.textContent = "Switch to KOT View";
    viewBtn.classList.remove("kot-view");
    viewBtn.classList.add("item-view");
  } else {
    currentView = "KOT";
    viewBtn.textContent = "Switch to Item View";
    viewBtn.classList.remove("item-view");
    viewBtn.classList.add("kot-view");
  }

  renderTickets();
});

// ==================== Render Tickets ====================
function renderTickets() {
  // Clear previous timers
  document.querySelectorAll(".ticket").forEach((t) => {
    if (t._timerInterval) clearInterval(t._timerInterval);
  });

  const sorted = [...tickets];

  // Sorting
  if (sortBy === "time") {
    sorted.sort((a, b) =>
      sortAsc
        ? new Date(a.created_on) - new Date(b.created_on)
        : new Date(b.created_on) - new Date(a.created_on)
    );
  } else if (sortBy === "table") {
    sorted.sort((a, b) => a.table_no - b.table_no);
  }

  // Clear container
  ticketContainer.innerHTML = "";
  let visibleTicketCount = 0;

  sorted.forEach((ticket) => {
    // Filter tickets by order_type
    if (!filters[ticket.order_type]) return;

    // Filter items inside ticket
    const filteredItems = ticket.items.filter((it) => {
      const state = Number(it.ack_status) === 1 ? "Ready" : "Pending";
      return filters[state];
    });
    if (!filteredItems.length) return;

    visibleTicketCount++;

    // ✅ Split into one-item tickets in ITEM view
    const ticketsToRender =
      currentView === "ITEM"
        ? filteredItems.map((it) => ({
            ...ticket,
            items: [it],
          }))
        : [ticket];

    ticketsToRender.forEach((tkt) => {
      const ticketEl = document.createElement("div");
      ticketEl.className = "ticket";
      ticketEl.dataset.kot = tkt.kot_no;
      ticketEl.dataset.bill = tkt.bill_no ?? "";

      // Ticket status
      const allAck = tkt.items.every((it) => Number(it.ack_status) === 1);
      ticketEl.id = allAck ? "ticket_accepted" : "ticket_new";

      // Header
      const headerEl = document.createElement("div");
      headerEl.className = "ticket-header";
      headerEl.innerHTML = `<div>${tkt.kot_no} | ${tkt.order_type} ${tkt.table_no}</div>`;
      headerEl.classList.add(tkt.order_type.toLowerCase().replace(/\s+/g, "-"));
      ticketEl.appendChild(headerEl);

      // Items container
      const itemsContainer = document.createElement("div");
      itemsContainer.className = "ticket-items";
      ticketEl.appendChild(itemsContainer);

      // Items HTML (only one in ITEM view)
      const itemsHtml = tkt.items
        .map((it) => {
          const commentText = it.comment || tkt.Comments || "";
          let itemClass = "pending";
          if (Number(it.ack_status) === 1) itemClass = "ready";
          else if (it.status === "Delivered") itemClass = "delivered";
          else if (it.status === "Ready") itemClass = "ready";

          const statusIcon =
            Number(it.ack_status) === 1
              ? '<img src="data/Images/Preparing.png" class="status-icon" alt="Ready">'
              : "⏳";

          return `<div class="ticket-item ${itemClass}" data-i-code="${
            it.i_code
          }">
            <div class="item-name">
              ${it.name}
              ${
                commentText
                  ? `<span class="item-comment">${commentText}</span>`
                  : ""
              }
            </div>
            <div class="item-qty">${it.qty}</div>
            <div class="item-status" onclick="toggleItem('${ticket.kot_no}','${
            ticket.bill_no
          }','${it.i_code}', event)">${statusIcon}</div>
          </div>`;
        })
        .join("");

      itemsContainer.innerHTML = itemsHtml;
      ticketContainer.appendChild(ticketEl);

      // ✅ ITEM view click → only one item turns green
      if (currentView === "ITEM") {
        // ✅ ITEM view: click anywhere on the ticket except status icon
        ticketEl.addEventListener("click", (e) => {
          if (e.target.classList.contains("item-status")) return;
          const item = tkt.items[0]; // only one item per ticket now
          if (!item) return;

          const wasAlreadyAcked = Number(item.ack_status) === 1;
          item.ack_status = 1; // mark as acknowledged
          ticketEl.classList.add("ticket-acked");

          ws.send(
            JSON.stringify({
              action: "ack_ticket",
              kot_no: tkt.kot_no,
              bill_no: tkt.bill_no ?? "",
              items: [{ i_code: item.i_code }],
            })
          );

          showPopup(
            wasAlreadyAcked
              ? `Item Delivered: ${item.name}`
              : `Item Accepted: ${item.name}`,
            3000
          );
          e.stopPropagation();
        });
      } else {
        // ✅ KOT view click → whole ticket acknowledged
        ticketEl.addEventListener("click", (e) => {
          if (e.target.classList.contains("item-status")) return;
          const allAlreadyAcked = tkt.items.every(
            (it) => Number(it.ack_status) === 1
          );
          tkt.items.forEach((it) => (it.ack_status = 1));

          ws.send(
            JSON.stringify({
              action: "ack_ticket",
              kot_no: tkt.kot_no,
              bill_no: tkt.bill_no ?? "",
              items: tkt.items.map((it) => ({ i_code: it.i_code })),
            })
          );

          renderTickets();
          showPopup(
            allAlreadyAcked
              ? `Order Delivered: KOT ${tkt.kot_no}`
              : `Order Accepted: KOT ${tkt.kot_no}`,
            3000
          );
        });
      }

      // Timer
      const timerEl = document.createElement("div");
      timerEl.className = "ticket-timer";
      itemsContainer.appendChild(timerEl);

      const updateTimer = () => {
        const createdTime = new Date(tkt.created_on);
        const diffMs = new Date() - createdTime;
        const minutes = Math.floor(diffMs / 60000);
        const seconds = Math.floor((diffMs % 60000) / 1000);
        const totalSeconds = Math.floor(diffMs / 1000);

        timerEl.textContent = `Waiting : ${minutes
          .toString()
          .padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;

        ticketEl.classList.remove(
          "ticket-wait-grey",
          "ticket-wait-orange",
          "ticket-wait-red",
          "ticket-acked"
        );
        if (minutes >= 5) ticketEl.classList.add("ticket-wait-red");
        else if (minutes >= 3) ticketEl.classList.add("ticket-wait-orange");
        else if (
          seconds > 30 &&
          tkt.items.some((it) => Number(it.ack_status) === 0)
        )
          ticketEl.classList.add("ticket-wait-red");
        else ticketEl.classList.add("ticket-wait-grey");

        if (currentView === "ITEM") {
          if (tkt.items.some((it) => Number(it.ack_status) === 1))
            ticketEl.classList.add("ticket-acked");
        } else {
          if (tkt.items.every((it) => Number(it.ack_status) === 1))
            ticketEl.classList.add("ticket-acked");
        }
      };

      updateTimer();
      ticketEl._timerInterval = setInterval(updateTimer, 1000);
    });
  });

  if (kotCountEl) kotCountEl.textContent = `No. of KOT = ${visibleTicketCount}`;
}

// ==================== Toggle Item ====================
function toggleItem(kot_no, bill_no, i_code, e) {
  if (e) e.stopPropagation(); // prevent parent ticket click from firing

  const ticket = tickets.find((t) => String(t.kot_no) === String(kot_no));
  if (!ticket) {
    ws.send(JSON.stringify({ action: "toggle_item", kot_no, bill_no, i_code }));
    return;
  }

  const item = ticket.items.find((it) => String(it.i_code) === String(i_code));
  if (!item) {
    ws.send(JSON.stringify({ action: "toggle_item", kot_no, bill_no, i_code }));
    return;
  }

  // Toggle only this item
  item.ack_status = Number(item.ack_status) === 1 ? 0 : 1;

  renderTickets();

  ws.send(JSON.stringify({ action: "toggle_item", kot_no, bill_no, i_code }));
}
