/* ===== AgroIA — lógica del chat ===== */

// Si sirves el front desde el mismo FastAPI (recomendado), deja "" (mismo origen).
// Si abres el HTML por separado, pon: const API_BASE = "http://127.0.0.1:8000";
const API_BASE = "";

const chatWindow = document.getElementById("chatWindow");
const welcome = document.getElementById("welcome");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const chips = document.getElementById("chips");

// Mantener el contexto de la conversación entre mensajes.
let sessionId = localStorage.getItem("agroia_session") || null;

// SVG de la mascota para el avatar de los mensajes del bot.
const BOT_AVATAR = `
  <svg viewBox="0 0 100 122" class="avocado">
    <path class="av-skin" d="M50 6c-19 0-30 21-30 47 0 33 15 57 30 57s30-24 30-57C80 27 69 6 50 6z"/>
    <path class="av-flesh" d="M50 18c-13 0-21 17-21 39 0 27 11 47 21 47s21-20 21-47c0-22-8-39-21-39z"/>
    <circle class="av-pit" cx="50" cy="74" r="17"/>
    <circle class="av-eye" cx="43" cy="49" r="3.4"/>
    <circle class="av-eye" cx="57" cy="49" r="3.4"/>
    <path class="av-smile" d="M42 57c3 4 13 4 16 0"/>
  </svg>`;

// Crea y agrega un mensaje al chat.
function addMessage(role, text, isError = false) {
  if (welcome) welcome.remove();

  const msg = document.createElement("div");
  msg.className = "msg " + (role === "user" ? "user" : "bot") + (isError ? " error" : "");

  if (role === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.innerHTML = BOT_AVATAR;
    msg.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  msg.appendChild(bubble);

  chatWindow.appendChild(msg);
  scrollToBottom();
  return msg;
}

// Indicador de "escribiendo…".
function showTyping() {
  const msg = document.createElement("div");
  msg.className = "msg bot typing";
  msg.id = "typing";
  msg.innerHTML = `
    <div class="msg-avatar">${BOT_AVATAR}</div>
    <div class="bubble"><span></span><span></span><span></span></div>`;
  chatWindow.appendChild(msg);
  scrollToBottom();
}
function hideTyping() {
  const t = document.getElementById("typing");
  if (t) t.remove();
}

function scrollToBottom() {
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

// Envía el mensaje al backend.
async function sendMessage(text) {
  const message = (text ?? input.value).trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";
  autoResize();
  setLoading(true);
  showTyping();

  try {
    const res = await fetch(API_BASE + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });

    hideTyping();

    if (!res.ok) {
      if (res.status === 503) {
        addMessage("bot", "El servicio de IA no está disponible en este momento. Intenta de nuevo en un momento. 🥑", true);
      } else {
        addMessage("bot", "Ocurrió un problema al procesar tu mensaje (código " + res.status + ").", true);
      }
      return;
    }

    const data = await res.json();
    if (data.session_id) {
      sessionId = data.session_id;
      localStorage.setItem("agroia_session", sessionId);
    }
    addMessage("bot", data.response || "(sin respuesta)");
  } catch (err) {
    hideTyping();
    addMessage("bot", "No pude conectar con el servidor. Verifica que el servicio esté encendido. 🌱", true);
  } finally {
    setLoading(false);
    input.focus();
  }
}

function setLoading(loading) {
  sendBtn.disabled = loading;
  input.disabled = loading;
}

// Auto-ajusta la altura del textarea al escribir.
function autoResize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
}

// ===== Eventos =====
sendBtn.addEventListener("click", () => sendMessage());

input.addEventListener("input", autoResize);

input.addEventListener("keydown", (e) => {
  // Enter envía; Shift+Enter hace salto de línea.
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

if (chips) {
  chips.addEventListener("click", (e) => {
    if (e.target.classList.contains("chip")) {
      sendMessage(e.target.textContent);
    }
  });
}

input.focus();
