const wsHost = window.location.hostname; // automatically gets IP on other PCs
const ws = new WebSocket(`ws://${wsHost}:9998`);
const ticketContainer = document.getElementById("ticket-container");

// Track current tickets displayed
let shownTickets = new Map(); // kot_no -> status

// ==================== Sound ====================
// Reliable: reference the HTML audio element
const newTicketSound = document.getElementById("new-ticket-sound");

// ✅ Unlock audio immediately on page load

// let soundUnlocked = true;

// function unlockAudio() {
//   if (!soundUnlocked) {
//     newTicketSound
//       .play()
//       .then(() => {
//         newTicketSound.pause();
//         newTicketSound.currentTime = 0;
//         soundUnlocked = true;
//         console.log("✅ Audio unlocked");
//       })
//       .catch((err) => console.log("Audio unlock error:", err));
//   }
// }
// document.addEventListener("click", unlockAudio, { once: true });
// document.addEventListener("keydown", unlockAudio, { once: true });

// ==================== Watermark ====================
// const watermark = document.createElement("div");
// watermark.id = "watermark";
// watermark.textContent = "Synoweb";
// document.body.appendChild(watermark);

// ==================== Watermark Image ====================
const watermark = document.createElement("div");
watermark.id = "watermark";

const wmImage = document.createElement("img");
wmImage.src = "/data/Images/big_logo.png";
watermark.appendChild(wmImage);

document.body.appendChild(watermark);

// ==================== WebSocket ====================
ws.onmessage = (event) => {
  let data;
  try {
    data = JSON.parse(event.data);
  } catch (err) {
    console.warn("❌ Invalid JSON received:", event.data);
    return;
  }

  if (!data || !Array.isArray(data.tickets)) {
    console.warn("⚠️ No tickets array in message:", data);
    return;
  }

  data.tickets.forEach((ticket) => {
    const prevStatus = shownTickets.get(ticket.kot_no);
    const currStatus = ticket.ticketstatus;

    // Play sound only if status changed from 0/undefined → 1/2
    if (
      (prevStatus === 0 || prevStatus === undefined) &&
      (currStatus === 1 || currStatus === 2)
    ) {
      newTicketSound.currentTime = 0;
      newTicketSound.play().catch(() => {});
    }

    // Update the status map
    shownTickets.set(ticket.kot_no, currStatus);
  });

  // ✅ Now filter only ready tickets for UI
  const readyTickets = data.tickets.filter(
    (t) => t.ticketstatus === 1 || t.ticketstatus === 2
  );
  readyTickets.sort((b, a) => a.kot_no - b.kot_no);

  // ✅ Update UI
  ticketContainer.innerHTML = "";
  if (readyTickets.length === 0) {
    watermark.classList.add("visible");
  } else {
    watermark.classList.remove("visible");
    readyTickets.forEach((ticket) => {
      const ticketEl = document.createElement("div");
      ticketEl.classList.add("ticket", "ready");
      ticketEl.textContent = ticket.kot_no;
      ticketContainer.appendChild(ticketEl);
    });
  }
};
