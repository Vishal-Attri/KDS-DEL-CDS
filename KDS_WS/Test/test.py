import asyncio
import json
import websockets
import pyodbc
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, HTTPServer
from threading import Thread

# --- SQL Connection String ---
CONN_STR = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=DESKTOP-NKDVK7U;"
    "DATABASE=synopos-cp;"
    "UID=posgst11;"
    "PWD=hello213;"
)

# --- Status Map (matches front-end STATUS_MAP) ---
STATUS_MAP = ["Preparing", "Ready", "Delivered"]

# --- Connected clients set ---
clients = set()


# --- Fetch tickets using stored procedure ---
def fetch_tickets():
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()
        cursor.execute("EXEC dbo.USP_Get_KDS_Data")
        rows = cursor.fetchall()

        tickets = {}
        for row in rows:
            kot_no = row.KOT_NO
            bill_no = getattr(row, "BillNO", None)
            table_name = getattr(row, "TableName", None)
            created_on = getattr(row, "CreatedOn", None)
            comments = getattr(row, "comments", "") or ""
            cancel_type = getattr(row, "Cancel_Type", 0)
            order_type = getattr(row, "bill_type", "")
            i_code = getattr(row, "I_Code", None)
            i_name = getattr(row, "I_Name", "")
            qty = getattr(row, "Qty", 0)
            item_status_idx = int(getattr(row, "order_status", 0))
            item_status = STATUS_MAP[item_status_idx]

            if kot_no not in tickets:
                tickets[kot_no] = {
                    "kot_no": kot_no,
                    "bill_no": bill_no,
                    "table_no": table_name,
                    "order_type": order_type,
                    "created_on": str(created_on) if created_on is not None else "",
                    "order_status": item_status,
                    "Comments": comments,
                    "Cancelled": str(cancel_type) == "1",
                    "items": []
                }

            tickets[kot_no]["items"].append({
                "i_code": str(i_code) if i_code is not None else "",
                "name": i_name,
                "qty": qty,
                "status": item_status
            })

        conn.close()
        return list(tickets.values())

    except Exception as e:
        print("❌ DB Error:", e)
        return []


# --- Update item or ticket status ---
def update_item_status(kot_no, bill_no=None, i_code=None, cancel=False):
    try:
        conn = pyodbc.connect(CONN_STR)
        cursor = conn.cursor()

        if cancel:
            cursor.execute("UPDATE tbl_TempKot SET Cancel_Type = 1 WHERE KOT_NO = ?", kot_no)
        else:
            if kot_no is None or bill_no is None or i_code is None:
                conn.close()
                return
            cursor.execute("EXEC dbo.USP_Update_KDS ?, ?, ?", kot_no, str(i_code), bill_no)

        conn.commit()
        conn.close()

    except Exception as e:
        print("❌ Update Error:", e)


# --- Broadcast tickets to all clients ---
async def broadcast_tickets():
    data = json.dumps(fetch_tickets())
    for client in clients.copy():
        try:
            await client.send(data)
        except:
            clients.discard(client)


# --- Periodic broadcast for updates ---
async def periodic_broadcast(interval=2):
    last_data = None
    while True:
        tickets = fetch_tickets()
        if tickets != last_data:
            data = json.dumps(tickets)
            for client in clients.copy():
                try:
                    await client.send(data)
                except:
                    clients.discard(client)
            last_data = tickets
        await asyncio.sleep(interval)


# --- WebSocket handler ---
async def ws_handler(websocket):
    clients.add(websocket)
    print("✅ Client connected")
    try:
        await websocket.send(json.dumps(fetch_tickets()))

        async for message in websocket:
            data = json.loads(message)
            action = data.get("action")

            if action == "toggle_item":
                update_item_status(
                    data.get("kot_no"),
                    data.get("bill_no"),
                    data.get("i_code"),
                    cancel=False
                )

            elif action == "toggle_summary":
                i_code = data.get("i_code")
                if i_code is not None:
                    try:
                        conn = pyodbc.connect(CONN_STR)
                        cursor = conn.cursor()
                        cursor.execute(
                            "SELECT DISTINCT KOT_NO, BillNO FROM tbl_TempKot WHERE I_Code = ?",
                            str(i_code)
                        )
                        for r in cursor.fetchall():
                            update_item_status(r.KOT_NO, r.BillNO, str(i_code), cancel=False)
                        conn.close()
                    except Exception as e:
                        print("❌ Summary Toggle Error:", e)

            elif action == "cancel_ticket":
                update_item_status(data.get("kot_no"), cancel=True)

            await broadcast_tickets()

    except websockets.exceptions.ConnectionClosed:
        print("❌ Client disconnected")
    finally:
        clients.discard(websocket)


# --- HTTP server for static files (serves KDS.html, KDS.js, etc.) ---
def run_http():
    httpd = HTTPServer(("0.0.0.0", 8080), SimpleHTTPRequestHandler)
    print("✅ HTTP server running at http://0.0.0.0:8080")
    httpd.serve_forever()


# --- Main entry ---
async def main():
    # Start HTTP server in background thread
    Thread(target=run_http, daemon=True).start()

    print("Testing DB connection...")
    rows = fetch_tickets()
    print(f"DB rows fetched: {len(rows)}")

    async with websockets.serve(ws_handler, "0.0.0.0", 9999):
        print("✅ WebSocket server running at ws://0.0.0.0:9999")
        asyncio.create_task(periodic_broadcast())
        await asyncio.Future()


if __name__ == "__main__":
    Thread(target=run_http, daemon=True).start()
    asyncio.run(main())





    //=================================================================================================================

// ==================== Constants & State ====================
const STATUS_MAP = ["Pending", "Ready", "Delivered"];
let tickets = []; // tickets from server
let filters = {
  Pending: true,
  Ready: true,
  Delivered: true,
  Cancelled: false,
};
let sortBy = "time";
let lastTicketIds = new Set();

// ==================== Elements ====================
const ticketContainer = document.getElementById("tickets");
const foodSummaryEl = document.getElementById("food-summary");
const modal = document.getElementById("ticket-modal");
const modalKOT = document.getElementById("modal-kot");
const modalItems = document.getElementById("modal-items");
const modalAccept = document.getElementById("modal-accept");
const modalCancel = document.getElementById("modal-cancel");
const sound = document.getElementById("new-ticket-sound");

// ==================== Clock ====================
function startClock() {
  const clockEl = document.getElementById("clock");
  setInterval(() => {
    clockEl.textContent = new Date().toLocaleTimeString();
  }, 1000);
}
startClock();

// ==================== WebSocket ====================
const ws = new WebSocket("ws://192.168.1.6:9999");
ws.onopen = () => console.log("✅ WS Connected");

ws.onmessage = (msg) => {
  const data = JSON.parse(msg.data);
  const currentIds = new Set(data.map((t) => t.kot_no));

  // Detect new tickets
  const newTickets = data.filter((t) => !lastTicketIds.has(t.kot_no));
  if (newTickets.length > 0) {
    newTickets.forEach((t) => openModalForNewTicket(t));
    const playPromise = sound.play();
    if (playPromise !== undefined)
      playPromise.catch((e) => console.log("⚠️ Sound play blocked:", e));
  }

  lastTicketIds = currentIds;
  tickets = data;
  renderTickets();
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

// ==================== Render Tickets ====================
function renderTickets() {
  let sorted = [...tickets];

  // Sorting
  if (sortBy === "time")
    sorted.sort((a, b) => new Date(a.created_on) - new Date(b.created_on));
  if (sortBy === "table") sorted.sort((a, b) => a.table_no - b.table_no);

  ticketContainer.innerHTML = "";
  const summary = {}; // keyed by i_code

  sorted.forEach((ticket) => {
    // --- Filter Checks ---
    if (ticket.Cancelled && !filters.Cancelled) return;

    // If not cancelled, ensure item statuses pass filters
    if (!ticket.Cancelled) {
      const allMatch = ticket.items.every((it) => filters[it.status]);
      if (!allMatch) return;
    }

    // --- Ticket Wrapper ---
    const ticketEl = document.createElement("div");
    ticketEl.className = "ticket";
    ticketEl.dataset.kot = ticket.kot_no;
    ticketEl.dataset.bill = ticket.bill_no ?? "";
    ticketEl.dataset.comments = ticket.Comments || "";

    // --- Items ---
    const itemsHtml = ticket.items
      .map((it) => {
        const ic = String(it.i_code ?? "");
        if (!summary[ic])
          summary[ic] = { name: it.name, qty: 0, status: it.status };
        summary[ic].qty += it.qty;
        summary[ic].status = it.status;

        return `<div class="ticket-item">
                  <div class="item-name">${it.name}</div>
                  <div>${it.qty}</div>
                  <div class="item-status" style="cursor:pointer;"
                       onclick="toggleItem('${ticket.kot_no}','${
          ticket.bill_no
        }','${ic}')">
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

    // --- Ticket Layout ---
    ticketEl.innerHTML = `
      <div class="ticket-header"
           style="display:flex; justify-content:space-between; align-items:center; cursor:pointer;">
        <div>#${ticket.kot_no} | Tbl ${ticket.table_no}</div>
        <div class="ticket-timer">0 min</div>
      </div>
      <div class="ticket-items">${itemsHtml}</div>
      ${
        ticket.Comments
          ? `<div class="ticket-comments">${ticket.Comments}</div>`
          : ""
      }
    `;

    // --- Open Modal on Click ---
    ticketEl.querySelector(".ticket-header").onclick = () =>
      openModal(ticketEl);

    // Append ticket
    ticketContainer.appendChild(ticketEl);

    // --- Timer & Border Update ---
    const timerEl = ticketEl.querySelector(".ticket-timer");
    const updateColorAndTime = () => {
      const createdTime = new Date(ticket.created_on);
      const now = new Date();
      const elapsedMin = Math.floor((now - createdTime) / 60000);
      timerEl.textContent = `${elapsedMin} min`;

      let color = "grey";
      if (elapsedMin > 10) color = "#dc2626"; // red
      else if (elapsedMin > 5) color = "#f97316"; // orange

      ticketEl.querySelector(".ticket-header").style.background = color;
      ticketEl.style.border = `1px solid ${color}`;
      ticketEl.style.borderRadius = "8px";
    };

    updateColorAndTime();
    setInterval(updateColorAndTime, 30000);
  });

  // --- Food Summary ---
  foodSummaryEl.innerHTML = Object.entries(summary)
    .map(
      ([icode, obj]) =>
        `<div class="food-item">
          <span>${obj.name} x ${obj.qty}</span>
          <span style="cursor:pointer;" onclick="toggleSummaryItem('${icode}')">
            ${
              obj.status === "Pending"
                ? "⏳"
                : obj.status === "Ready"
                ? "✅"
                : "📦"
            }
          </span>
        </div>`
    )
    .join("");
}

// ==================== Toggle Item ====================
function toggleItem(kot_no, bill_no, i_code) {
  ws.send(JSON.stringify({ action: "toggle_item", kot_no, bill_no, i_code }));
}

// ==================== Toggle Summary Item ====================
function toggleSummaryItem(i_code) {
  ws.send(JSON.stringify({ action: "toggle_summary", i_code }));
}

// ==================== Modal ====================
function openModal(ticketEl) {
  const kotNo = ticketEl.dataset.kot;
  const comments = ticketEl.dataset.comments;
  const itemsHtml = ticketEl.querySelector(".ticket-items").innerHTML;

  modal.style.display = "flex";
  modalKOT.textContent = `KOT #${kotNo}`;
  modalItems.innerHTML =
    itemsHtml +
    (comments ? `<div class="ticket-comments">${comments}</div>` : "");

  modalAccept.onclick = () => (modal.style.display = "none");
  modalCancel.onclick = () => {
    ws.send(JSON.stringify({ action: "cancel_ticket", kot_no: kotNo }));
    modal.style.display = "none";
  };
}

// ==================== Modal Auto-Open for New Tickets ====================
function openModalForNewTicket(ticket) {
  const tempEl = document.createElement("div");
  tempEl.className = "ticket";
  tempEl.dataset.kot = ticket.kot_no;
  tempEl.dataset.comments = ticket.Comments || "";
  tempEl.innerHTML = `<div class="ticket-items">
    ${ticket.items
      .map((it) => `<div>${it.name} x${it.qty} — ${it.status}</div>`)
      .join("")}
    ${
      ticket.Comments
        ? `<div class="ticket-comments">${ticket.Comments}</div>`
        : ""
    }
  </div>`;
  openModal(tempEl);
}

// ==================== Close Modal on Outside Click ====================
modal.addEventListener("click", (e) => {
  if (e.target === modal) modal.style.display = "none";
});

const ws = new WebSocket("ws://localhost:9998");
const ticketContainer = document.getElementById("ticket-container");
const activeTimers = {}; // track 5-min timers
let previousTicketStatuses = {}; // track ticketstatus changes

// Sound for ticket ready
const newTicketSound = new Audio("new_ticket.mp3");
let soundUnlocked = false;

// --------------- Unlock audio on first click ----------------
document.body.addEventListener("click", () => {
  if (!soundUnlocked) {
    newTicketSound.play().then(() => newTicketSound.pause());
    newTicketSound.currentTime = 0;
    soundUnlocked = true;
    console.log("Audio unlocked");
  }
}, { once: true });

// ---------------- WebSocket ----------------
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const ticketsArray = data.tickets || [];

  // Only unique tickets by KOT_NO
  const tickets = ticketsArray.map((t) => ({
    kot_no: parseInt(t.kot_no),
    ticketstatus: t.ticketstatus, // 1=ready, 0=pending
  }));

  // Sort ready first
  tickets.sort((a, b) => {
    if (a.ticketstatus === b.ticketstatus) return a.kot_no - b.kot_no;
    return b.ticketstatus - a.ticketstatus;
  }));

  // Track 5-min timers for ready tickets & sound
  tickets.forEach((ticket) => {
    const prevStatus = previousTicketStatuses[ticket.kot_no] || 0;

    // Play sound only if ticket just turned green
    if (ticket.ticketstatus === 1 && prevStatus !== 1 && soundUnlocked) {
      newTicketSound.play().catch(() => {});
    }

    // Start timer for green ticket
    if (ticket.ticketstatus === 1 && !activeTimers[ticket.kot_no]) {
      activeTimers[ticket.kot_no] = Date.now();
    } else if (ticket.ticketstatus === 0) {
      delete activeTimers[ticket.kot_no];
    }

    // Update previous status
    previousTicketStatuses[ticket.kot_no] = ticket.ticketstatus;
  });

  // Remove tickets after 5 minutes of being green
  const filteredTickets = tickets.filter((ticket) => {
    if (ticket.ticketstatus === 1 && activeTimers[ticket.kot_no]) {
      const elapsed = Date.now() - activeTimers[ticket.kot_no];
      if (elapsed >= 300000) {
        delete activeTimers[ticket.kot_no];
        delete previousTicketStatuses[ticket.kot_no];
        return false;
      }
    }
    return true;
  });

  // Render
  ticketContainer.innerHTML = "";
  filteredTickets.forEach((ticket) => {
    const ticketEl = document.createElement("div");
    ticketEl.classList.add("ticket");
    ticketEl.classList.add(ticket.ticketstatus === 1 ? "ready" : "pending");
    ticketEl.textContent = ticket.kot_no;

    // Click to toggle server-side
    ticketEl.onclick = () => {
      ws.send(
        JSON.stringify({
          action: "toggle_ticket",
          kot_no: ticket.kot_no,
        })
      );
    };

    ticketContainer.appendChild(ticketEl);
  });
};

// ==================== WebSocket ====================
const ws = new WebSocket("ws://localhost:9998");
const ticketContainer = document.getElementById("ticket-container");

// ==================== Live Clock ====================
function updateClock() {
  const clockEl = document.getElementById("clock");
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  clockEl.textContent = `${hh}:${mm}:${ss}`;
}

// Update every second
setInterval(updateClock, 1000);
updateClock(); // initial call

// ==================== Render Tickets ====================
function renderTickets(tickets) {
  ticketContainer.innerHTML = "";

  tickets.forEach((ticket) => {
    const ticketEl = document.createElement("div");
    ticketEl.classList.add("ticket");

    // Determine if ticket is ready
    const isReady = ticket.ticketstatus === 1;
    ticketEl.classList.add(isReady ? "ready" : "pending");

    // ==================== Ticket Header ====================
    const ticketHeader = document.createElement("div");
    ticketHeader.classList.add("ticket-header");
    ticketHeader.innerHTML = `
      #${ticket.kot_no} | Tbl ${ticket.table_no}
      <span class="cds-status" style="float:right">
        ${isReady ? "CDS Status: Ready" : ""}
      </span>
    `;

    // ==================== Ticket Items ====================
    let itemsHtml = "";
    ticket.items.forEach((item) => {
      // Ticket-items background is now independent of ticketstatus
      let itemBg = "#f8d7da"; // Pending
      if (item.status === "Delivered") itemBg = "#cce5ff"; // Delivered
      else if (item.status === "Ready") itemBg = "#d4edda"; // Item Ready (not ticket)

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

    // ==================== Click Event ====================
    // Clicking triggers backend procedure for all items
    // Ticket-item background remains unchanged; only ticket bg changes
    ticketEl.onclick = () => {
      ws.send(
        JSON.stringify({
          action: "toggle_ticket",
          kot_no: ticket.kot_no,
          bill_no: ticket.bill_no,
          items: ticket.items,
        })
      );
    };

    ticketContainer.appendChild(ticketEl);
  });
}
========================================================================================================
// ==================== WebSocket Message Handler ====================
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.tickets) renderTickets(data.tickets);
};



const ws = new WebSocket("ws://localhost:9998");
const ticketContainer = document.getElementById("ticket-container");
const activeTimers = {}; // track 5-min timers
let previousTicketStatuses = {}; // track ticketstatus changes

// Sound for ticket ready
const newTicketSound = new Audio("new_ticket.mp3");
let soundUnlocked = false;

// --------------- Unlock audio on first click ----------------
document.body.addEventListener(
  "click",
  () => {
    if (!soundUnlocked) {
      newTicketSound.play().then(() => newTicketSound.pause());
      newTicketSound.currentTime = 0;
      soundUnlocked = true;
      console.log("Audio unlocked");
    }
  },
  { once: true }
);

// ---------------- WebSocket ----------------
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const ticketsArray = data.tickets || [];

  // ✅ Only keep tickets where ticketstatus == 1
  const tickets = ticketsArray
    .filter((t) => t.ticketstatus === 1) // <-- This ensures only ready tickets
    .map((t) => ({
      kot_no: parseInt(t.kot_no),
      ticketstatus: t.ticketstatus, // 1=ready, 0=pending
    }));

  // Sort ready first (not really needed now but kept for safety)
  tickets.sort((a, b) => a.kot_no - b.kot_no);

  // Track 5-min timers for ready tickets & sound
  tickets.forEach((ticket) => {
    const prevStatus = previousTicketStatuses[ticket.kot_no] || 0;

    // Play sound only if ticket just turned green
    if (ticket.ticketstatus === 1 && prevStatus !== 1 && soundUnlocked) {
      newTicketSound.play().catch(() => {});
    }

    // Start timer for green ticket
    if (ticket.ticketstatus === 1 && !activeTimers[ticket.kot_no]) {
      activeTimers[ticket.kot_no] = Date.now();
    } else if (ticket.ticketstatus === 0) {
      delete activeTimers[ticket.kot_no];
    }

    // Update previous status
    previousTicketStatuses[ticket.kot_no] = ticket.ticketstatus;
  });

  // Remove tickets after 5 minutes of being green
  const filteredTickets = tickets.filter((ticket) => {
    if (ticket.ticketstatus === 1 && activeTimers[ticket.kot_no]) {
      const elapsed = Date.now() - activeTimers[ticket.kot_no];
      if (elapsed >= 300000) {
        delete activeTimers[ticket.kot_no];
        delete previousTicketStatuses[ticket.kot_no];
        return false;
      }
    }
    return true;
  });

  // Render only ready tickets
  ticketContainer.innerHTML = "";
  filteredTickets.forEach((ticket) => {
    const ticketEl = document.createElement("div");
    ticketEl.classList.add("ticket");
    ticketEl.classList.add("ready"); // only ready tickets now
    ticketEl.textContent = ticket.kot_no;

    // Click to toggle server-side
    ticketEl.onclick = () => {
      ws.send(
        JSON.stringify({
          action: "toggle_ticket",
          kot_no: ticket.kot_no,
        })
      );
    };

    ticketContainer.appendChild(ticketEl);
  });
};
