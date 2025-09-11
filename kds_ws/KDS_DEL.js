const wsHost = window.location.hostname; // automatically gets IP on other PCs
const ws = new WebSocket(`ws://${wsHost}:9998`);
ws.onopen = () => {
  const kdsName = localStorage.getItem("kds_name") || "NONE";
  ws.send(JSON.stringify({ action: "init_kds", kds_name: kdsName }));
};

const ticketContainer = document.getElementById("ticket-container");
const kotCountEl = document.getElementById("kot-count");

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

// ==================== Sound ====================
// const ticketSound = new Audio("new_ticket.mp3");
const previousStatuses = {}; // track previous ticketstatus by KOT_NO

// ---------- LOGIN & SIDEBAR ----------
let loggedIn = localStorage.getItem("kds_logged_in") === "true"; // persist login
let kdsName = localStorage.getItem("kds_name") || ""; // saved KDS name

const hamburger = document.getElementById("hamburger");
const sidebar = document.getElementById("sidebar");

// ---------- LOGIN PROMPT ----------
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

// ---------- SIDEBAR TOGGLE ----------
function toggleSidebar() {
  if (!loggedIn) {
    promptLogin();
    if (!loggedIn) return; // stop if login failed
  }
  sidebar.style.left = sidebar.style.left === "0px" ? "-250px" : "0px";
}

hamburger.onclick = toggleSidebar;

// ---------- CONFIG MODAL ----------
const configBtn = document.getElementById("config");
const configModal = document.getElementById("config-modal");
const configSubmit = document.getElementById("config-submit");
const kdsInput = document.getElementById("kds-name-input");
const loginIdInput = document.getElementById("login-id");
const loginPwdInput = document.getElementById("login-pwd");

// Open modal
configBtn.onclick = () => {
  kdsInput.value = kdsName; // prefill current name
  configModal.style.display = "flex";
};

// Handle config save
configSubmit.onclick = () => {
  const enteredId = loginIdInput.value.trim();
  const enteredPwd = loginPwdInput.value.trim();
  const newKds = kdsInput.value.trim();

  // Check credentials
  if (enteredId === "abc" && enteredPwd === "abc") {
    loggedIn = true;
    localStorage.setItem("kds_logged_in", "true"); // persist login

    // Save KDS name permanently in localStorage
    if (newKds !== "") {
      kdsName = newKds;
      localStorage.setItem("kds_name", kdsName);
    }

    alert("✅ Login Successful");
    configModal.style.display = "none"; // close modal
  } else {
    alert("❌ Wrong ID or Password");
  }
};

// Close modal if clicking outside content
configModal.onclick = (e) => {
  if (e.target === configModal) configModal.style.display = "none";
};

// ==================== Render Tickets ====================
function renderTickets(tickets) {
  tickets.sort((a, b) => a.kot_no - b.kot_no);
  ticketContainer.innerHTML = "";

  // Update KOT count
  kotCountEl.textContent = `No. of KOT = ${tickets.length}`;

  tickets.forEach((ticket) => {
    const ticketEl = document.createElement("div");
    ticketEl.classList.add("ticket");

    // ===== ticket status logic (0 = Pending, 1 = Partial, 2 = Ready) =====
    const totalItems = ticket.items.length;
    const readyItems = ticket.items.filter(
      (i) => Number(i.ready_status) === 1
    ).length;

    let ticketStatus = 0; // default Pending
    if (totalItems > 0 && readyItems === totalItems)
      ticketStatus = 2; // all ready -> green
    else if (readyItems > 0) ticketStatus = 1; // some ready -> orange

    // apply class
    ticketEl.classList.add(
      ticketStatus === 2 ? "ready" : ticketStatus === 1 ? "partial" : "pending"
    );

    // Play sound if ticket becomes Partial or Ready
    if (
      (ticketStatus === 1 && previousStatuses[ticket.kot_no] !== 1) ||
      (ticketStatus === 2 && previousStatuses[ticket.kot_no] !== 2)
    ) {
      // ticketSound.play().catch(() => {});
    }
    previousStatuses[ticket.kot_no] = ticketStatus;

    // Ticket Header
    const ticketHeader = document.createElement("div");
    ticketHeader.classList.add("ticket-header");
    ticketHeader.innerHTML = `
      #${ticket.kot_no} | ${ticket.bill_type} ${ticket.table_no}  
      <span class="cds-status" style="float:right">
        ${ticketStatus === 2 ? "Ready" : ticketStatus === 1 ? "Partial" : ""}
      </span>
    `;

    let itemsHtml = "";
    ticket.items.forEach((item) => {
      let itemBg = "#f8d7da"; // pending (red)
      if (item.status === "Delivered") itemBg = "#cce5ff"; // delivered -> blue
      else if (item.status === "Ready") itemBg = "#d4edda"; // ready -> green
      else if (Number(item.ready_status) === 1) itemBg = "#fff3cd"; // marked ready -> yellow

      itemsHtml += `
        <div class="ticket-item" style="background:${itemBg}">
          <div class="item-name">${item.name}</div>
          <div class="item-qty">${item.qty}</div>
        </div>
      `;
    });

    const itemsContainer = document.createElement("div");
    itemsContainer.classList.add("ticket-items");
    itemsContainer.innerHTML = itemsHtml;

    ticketEl.appendChild(ticketHeader);
    ticketEl.appendChild(itemsContainer);

    // Click Event — backend will run your procedure
    ticketEl.onclick = () => {
      const allPending = ticket.items.every(
        (i) => Number(i.ready_status) === 0 && i.status !== "Ready"
      );

      if (allPending) {
        alert("No Orders Ready");
        return; // do not send websocket message
      }
      ws.send(
        JSON.stringify({
          action: "toggle_ticket",
          kot_no: ticket.kot_no,
          bill_no: ticket.bill_no,
          items: ticket.items,
          table_no: ticket.table_no,
          ticketstatus: ticket.ticketstatus,
          ready_date: ticket.ready_date || "",
          stwd: ticket.stwd || "",
        })
      );
    };

    ticketContainer.appendChild(ticketEl);
  });
}

// ==================== WebSocket Message Handler ====================
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Tickets received:", data.tickets); // debug
  if (data.tickets) renderTickets(data.tickets);
};
