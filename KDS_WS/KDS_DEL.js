// function printOnClient(ticket) {
//   fetch("http://localhost:1000", {
//     method: "POST",
//     headers: { "Content-Type": "application/json" },
//     body: JSON.stringify({ ticket }),
//   }).catch((e) => console.error("❌ Client print error:", e));
// }

function printOnClient(ticket) {
  if (!allowPrint) return;

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  try {
    const now = new Date();
    const dateStr = now.toISOString().split("T")[0];
    const timeStr = now.toTimeString().split(" ")[0];
    let count = 0;

    const billTypeText =
      ticket.bill_type === "Table billing" ? "Table" : ticket.bill_type;

    // Build items HTML: each item in its own div
    let itemsHtml = "";
    ticket.items.forEach((item) => {
      count += 1;
      itemsHtml += `
        <div class="item">
          <div class="item-name">${count}. ${escapeHtml(item.name)}</div>
          <div class="item-qty">${escapeHtml(String(item.qty))}</div>
        </div>
      `;
    });

    const html = `<!doctype html>
      <html>
      <head>
        <meta charset="utf-8">
        <title>Print KOT</title>
        <style>
          @page { margin: 1mm; }
          @media print {
            body { margin:0; padding:0; -webkit-print-color-adjust: exact; }
          }
          body {
            font-family: "Consolas";
            font-size: 13px;
            color: #000;
            margin:0;
            -webkit-font-smoothing:antialiased;
            font-weight:700;
          }
          .ticket {
            width: 100%;
            max-width: 500px; /* use more left/right space */
            margin: 0 auto;
            box-sizing: border-box;
          }
          .header { font-size: 15px; font-weight:700; text-align:center; margin-bottom:6px; }
          .subheader { font-size:13px; font-weight:700; margin-bottom:4px; text-align:left; }
          .bold_line { border-top:2px dashed #000; margin:6px 0; }
          .line { border-top:1px dashed #000; margin:6px 0; }
          .meta { display:flex; font-size:12px; justify-content:space-between;}
          .items { margin-top:1px; }
          .item {
            display:flex;
            justify-content:space-between;
            align-items:flex-start;
            margin:0px;
            gap:2px;
          }
          .item-name {
            flex: 1 1 auto;
            font-weight:700;
            word-break:break-word;       /* allow wrapping */
            white-space: normal;
            font-size:12px;
          }
          .item-qty {
            flex: 0 0 60px;              /* fixed space for qty so it won't be cut off */
            text-align: right;
            font-weight:700;
            font-size:12px;
            min-width: 40px;
          }
          .footer { text-align:center; margin-top:8px; font-size:13px; font-weight:400; }
        </style>
      </head>
      <body>
        <div class="ticket">
          <div class="header">${escapeHtml(billTypeText)} : ${escapeHtml(
      String(ticket.table_no || "")
    )}</div>
          <div class="subheader">Bill:${escapeHtml(
            String(ticket.bill_no || "")
          )} | KOT:${escapeHtml(String(ticket.kot_no || ""))}</div>
          <div class="bold_line"></div>
          <div class="meta"><div>Date: ${dateStr}</div> &nbsp;&nbsp; <div>Time: ${timeStr}</div></div>
          <div class="meta"><div>ITEM</div> &nbsp;&nbsp; <div>QTY</div></div>
          <div class="line"></div>

          <div class="items">
            ${itemsHtml}
          </div>

          <div class="line"></div>
          ${
            ticket.stwd
              ? `<div class="meta"><div>Steward: ${escapeHtml(
                  ticket.stwd
                )} &nbsp;&nbsp;</div> <div>Items: ${
                  ticket.items.length
                }</div></div>`
              : ""
          }
          <div class="footer">KOT PRINT</div>
        </div>
      </body>
      </html>`;

    const printWindow = window.open("", "_blank");
    if (!printWindow) {
      console.error("❌ Unable to open print window (popup blocked)");
      return;
    }
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();

    // give browser a short moment to lay out the content, then print
    printWindow.focus();
    setTimeout(() => {
      try {
        printWindow.print();
        // don't always close immediately in case user wants preview, but close to match previous behaviour:
        printWindow.close();
      } catch (err) {
        console.error("❌ Print failed:", err);
      }
    }, 250);

    console.log(`✅ Printed ticket #${ticket.kot_no}`);
  } catch (e) {
    console.error("❌ Client print error:", e);
  }
}

// ==================== 1. Constants & State ====================
const previousStatuses = {}; // track previous ticketstatus by KOT_NO
let loggedIn = localStorage.getItem("kds_logged_in") === "true";
let kdsName = localStorage.getItem("kds_name") || "";

// ==================== 2. Elements ====================
const ticketContainer = document.getElementById("ticket-container");
const kotCountEl = document.getElementById("kot-count");
const hamburger = document.getElementById("hamburger");
const sidebar = document.getElementById("sidebar");
const configBtn = document.getElementById("config");
const configModal = document.getElementById("config-modal");
const configSubmit = document.getElementById("config-submit");
const kdsInput = document.getElementById("kds-name-input");
const loginIdInput = document.getElementById("login-id");
const loginPwdInput = document.getElementById("login-pwd");
const currentKdsSidebarEl = document.getElementById("current-kds-sidebar");

// ==================== 3. Live Clock ====================
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

// ==================== 4. WebSocket Setup ====================
let ws; // global reference

function connectKDSDel() {
  const wsHost = window.location.hostname;
  ws = new WebSocket(`ws://${wsHost}:9998`);

  ws.onopen = () => {
    console.log("✅ WebSocket connected");
    kdsName = localStorage.getItem("kds_name") || "NONE";
    ws.send(JSON.stringify({ action: "init_kds", kds_name: kdsName }));

    if (currentKdsSidebarEl) {
      currentKdsSidebarEl.textContent = `KDS Name: ${kdsName}`;
    }
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.tickets) {
      renderTickets(data.tickets);
    }

    // Handle server-directed printing
    if (data.action === "print_ticket" && data.ticket) {
      printOnClient(data.ticket);
    }
  };

  ws.onerror = (err) => {
    console.error("WebSocket error:", err);
    ws.close(); // trigger onclose
  };

  ws.onclose = () => {
    console.warn("❌ WebSocket closed. Reconnecting in 3s...");
    setTimeout(connectKDSDel, 3000); // reconnect loop
  };
}

// Start the WebSocket connection
connectKDSDel();

// ==================== 5. Login & Sidebar ====================
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

// ==================== 6. Config Modal ====================
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
    }

    alert("✅ Login Successful");
    configModal.style.display = "none";
  } else {
    alert("❌ Wrong ID or Password");
  }
};

// ==================== 7. UI Sidebar ====================

configModal.onclick = (e) => {
  if (e.target === configModal) configModal.style.display = "none";
};

const deliveredBtn = document.getElementById("delivered-btn");
const iframeModal = document.getElementById("iframe-modal");
const iframeClose = document.getElementById("iframe-close");
const deliveredIframe = document.getElementById("delivered-iframe");

deliveredBtn.onclick = () => {
  iframeModal.style.display = "block";
  deliveredIframe.src = "KDS_Recall.html";
};

iframeClose.onclick = () => {
  iframeModal.style.display = "none";
  deliveredIframe.src = "";
};

// Close modal if user clicks outside content
iframeModal.onclick = (e) => {
  if (e.target === iframeModal) {
    iframeModal.style.display = "none";
    deliveredIframe.src = "";
  }
};

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

// ==================== 8. Print Tickets ====================
let allowPrint = true; // default ON
const printToggle = document.getElementById("print-toggle");
printToggle.checked = allowPrint;
printToggle.addEventListener("change", () => {
  allowPrint = printToggle.checked;
  console.log("Printing " + (allowPrint ? "enabled" : "disabled"));
});

// ==================== 8. Render Tickets ====================
function renderTickets(tickets) {
  tickets.sort((a, b) => b.kot_no - a.kot_no);
  ticketContainer.innerHTML = "";
  kotCountEl.textContent = `No. of KOT = ${tickets.length}`;

  tickets.forEach((ticket) => {
    const ticketEl = document.createElement("div");
    ticketEl.classList.add("ticket");

    const totalItems = ticket.items.length;
    const readyItems = ticket.items.filter(
      (i) => Number(i.ready_status) === 1
    ).length;

    let ticketStatus = 0;
    if (totalItems > 0 && readyItems === totalItems) ticketStatus = 2;
    else if (readyItems > 0) ticketStatus = 1;

    ticketEl.classList.add(
      ticketStatus === 2 ? "ready" : ticketStatus === 1 ? "partial" : "pending"
    );

    previousStatuses[ticket.kot_no] = ticketStatus;

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
      let itemBg = "#f8d7da";
      if (item.status === "Delivered") itemBg = "#cce5ff";
      else if (item.status === "Ready") itemBg = "#d4edda";
      else if (Number(item.ready_status) === 1) itemBg = "#fff3cd";

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

    ticketEl.onclick = () => {
      const allPending = ticket.items.every(
        (i) => Number(i.ready_status) === 0 && i.status !== "Ready"
      );

      if (allPending) {
        showPopup("No Items Ready", 3000);
        return;
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
          order_type: ticket.order_type || "",
          bill_type: ticket.bill_type || "",
          cashier: ticket.cashier || "",
          print: allowPrint,
        })
      );
    };
    ticketContainer.appendChild(ticketEl);
  });
}
