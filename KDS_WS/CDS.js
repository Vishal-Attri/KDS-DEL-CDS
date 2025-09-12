const wsHost = window.location.hostname; // automatically gets IP on other PCs
const ws = new WebSocket(`ws://${wsHost}:9998`);
const ticketContainer = document.getElementById("ticket-container");
let seenTickets = new Set(); // Track already shown tickets

// ==================== Sound ====================
const newTicketSound = new Audio("new_ticket.mp3");
newTicketSound.preload = "auto";
let soundUnlocked = false;

// Unlock audio on first click or keypress
function unlockAudio() {
  if (!soundUnlocked) {
    newTicketSound
      .play()
      .then(() => {
        newTicketSound.pause();
        newTicketSound.currentTime = 0;
        soundUnlocked = true;
        console.log("✅ Audio unlocked");
      })
      .catch((err) => console.log("Audio unlock error:", err));
  }
}

document.addEventListener("click", unlockAudio, { once: true });
document.addEventListener("keydown", unlockAudio, { once: true });

// ==================== WebSocket ====================
ws.onmessage = (event) => {
  let data;
  try {
    data = JSON.parse(event.data);
  } catch (err) {
    console.warn("❌ Invalid JSON received:", event.data);
    return; // skip invalid message
  }

  if (!data || !Array.isArray(data.tickets)) {
    console.warn("⚠️ No tickets array in message:", data);
    return; // skip if no tickets
  }

  // ✅ Filter tickets with status 1 or 2
  const readyTickets = data.tickets
    .filter((t) => t.ticketstatus === 1 || t.ticketstatus === 2)
    .map((t) => ({
      kot_no: parseInt(t.kot_no),
      ticketstatus: t.ticketstatus,
    }));

  // Sort tickets by KOT number
  readyTickets.sort((a, b) => a.kot_no - b.kot_no);

  // Play sound for newly appeared tickets
  readyTickets.forEach((ticket) => {
    if (!seenTickets.has(ticket.kot_no) && soundUnlocked) {
      newTicketSound.currentTime = 0;
      newTicketSound.play().catch(() => {});
      seenTickets.add(ticket.kot_no);
    }
  });

  // Render ready tickets
  ticketContainer.innerHTML = "";
  readyTickets.forEach((ticket) => {
    const ticketEl = document.createElement("div");
    ticketEl.classList.add("ticket", "ready");
    ticketEl.textContent = ticket.kot_no;

    // Send toggle message on click
    ticketEl.onclick = () => {
      ws.send(
        JSON.stringify({
          action: "toggle_ticket",
          kot_no: ticket.kot_no,
        })
      );
    };

    // // Automatically remove after 10 seconds
    // setTimeout(() => {
    //   if (ticketEl.parentNode) {
    //     ticketEl.classList.add("fade-out"); // for smooth animation
    //     setTimeout(() => ticketEl.remove(), 500); // remove after fade-out
    //   }
    // }, 10000); // 10 sec

    ticketContainer.appendChild(ticketEl);
  });
};
