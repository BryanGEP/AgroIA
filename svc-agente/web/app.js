/* ===== AgroIA — lógica del chat ===== */

// Mismo origen (servido por FastAPI). Si abres el HTML aparte: "http://127.0.0.1:8000"
const API_BASE = "";

const chatWindow = document.getElementById("chatWindow");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const chips = document.getElementById("chips");
const newChatBtn = document.getElementById("newChat");
const headerAvatar = document.getElementById("headerAvatar");
const soundToggleBtn = document.getElementById("soundToggle");
const micBtn = document.getElementById("micBtn");

let sessionId = safeGet("agroia_session") || null;
let history = loadHistory();

// Por defecto el sonido esta silenciado; el usuario debe activarlo explicitamente.
let soundEnabled = safeGet("agroia_sound_enabled") === "true";

// SVG de la mascota para el avatar de los mensajes del bot.
const BOT_AVATAR = `
  <svg viewBox="0 0 120 140" class="avocado">
    <path class="av-skin" d="M60 14 C38 14 27 38 27 68 C27 104 42 128 60 128 C78 128 93 104 93 68 C93 38 82 14 60 14 Z"/>
    <path class="av-flesh" d="M60 26 C44 26 36 46 36 70 C36 100 47 118 60 118 C73 118 84 100 84 70 C84 46 76 26 60 26 Z"/>
    <circle class="av-pit" cx="60" cy="90" r="18"/>
    <g class="av-eyes">
      <ellipse class="av-eye" cx="51" cy="54" rx="4.2" ry="5.2"/>
      <ellipse class="av-eye" cx="69" cy="54" rx="4.2" ry="5.2"/>
    </g>
    <path class="av-smile" d="M52 64 c4 5 12 5 16 0"/>
  </svg>`;

const COPY_ICON = `<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z"/></svg>`;

const SOUND_ON_ICON = `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 8v8a4.5 4.5 0 0 0 2.5-4zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>`;
const SOUND_OFF_ICON = `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M3 9v6h4l5 5V4L7 9H3zm13.59 3 2.7-2.71-1.42-1.42L15.17 10l-2.7-2.71-1.42 1.42L13.76 11.4l-2.71 2.7 1.42 1.42 2.7-2.71 2.71 2.71 1.42-1.42z"/></svg>`;

/* ---------- Almacenamiento seguro ---------- */
function safeGet(k) { try { return localStorage.getItem(k); } catch { return null; } }
function safeSet(k, v) { try { localStorage.setItem(k, v); } catch {} }
function safeRemove(k) { try { localStorage.removeItem(k); } catch {} }
function loadHistory() { try { return JSON.parse(safeGet("agroia_history") || "[]"); } catch { return []; } }
function saveHistory() { safeSet("agroia_history", JSON.stringify(history)); }

/* ---------- Limpieza de respuesta ---------- */
// Si el LLM envuelve TODA la respuesta en un unico bloque de codigo
// (``` o ```markdown ... ```), se quitan solo esas comillas triples de
// apertura/cierre. No afecta bloques de codigo que esten en medio del texto,
// porque exige que el fence este al inicio y al final de todo el mensaje.
function stripWrappingCodeFence(text) {
  const trimmed = text.trim();
  const match = trimmed.match(/^```[a-zA-Z]*\r?\n([\s\S]*?)\r?\n?```$/);
  return match ? match[1] : text;
}

/* ---------- Markdown seguro (escapa primero, luego formatea) ---------- */
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function inlineMd(s) {
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
  s = s.replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  return s;
}
function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  let html = "", listType = null, buffer = [], para = [];
  const closeList = () => { if (listType) { html += "<" + listType + ">" + buffer.join("") + "</" + listType + ">"; buffer = []; listType = null; } };
  const flushPara = () => { if (para.length) { html += "<p>" + para.join("<br>") + "</p>"; para = []; } };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet) {
      flushPara();
      if (listType !== "ul") { closeList(); listType = "ul"; }
      buffer.push("<li>" + inlineMd(bullet[1]) + "</li>");
    } else if (numbered) {
      flushPara();
      if (listType !== "ol") { closeList(); listType = "ol"; }
      buffer.push("<li>" + inlineMd(numbered[1]) + "</li>");
    } else if (line.trim() === "") {
      closeList(); flushPara();
    } else {
      closeList(); para.push(inlineMd(line));
    }
  }
  closeList(); flushPara();
  return html || "<p></p>";
}

/* ---------- Efecto de escritura (typewriter) ---------- */
// Revela el texto plano progresivamente y solo al final lo re-renderiza como
// Markdown, para que nunca quede una etiqueta HTML a medio formar. Respeta
// prefers-reduced-motion mostrando la respuesta completa sin animar.
function typeWriter(bubbleEl, fullText, onDone) {
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReducedMotion || !fullText) {
    bubbleEl.innerHTML = renderMarkdown(fullText);
    onDone();
    return;
  }
  const TOTAL_TICKS = 110; // fotogramas aproximados, independiente del largo del texto
  const INTERVAL_MS = 18;
  const step = Math.max(1, Math.ceil(fullText.length / TOTAL_TICKS));

  bubbleEl.textContent = "";
  bubbleEl.classList.add("is-typing");
  let i = 0;
  const timer = setInterval(() => {
    i += step;
    if (i >= fullText.length) {
      clearInterval(timer);
      bubbleEl.classList.remove("is-typing");
      bubbleEl.innerHTML = renderMarkdown(fullText);
      onDone();
    } else {
      bubbleEl.textContent = fullText.slice(0, i);
    }
    scrollToBottom();
  }, INTERVAL_MS);
}

/* ---------- Copiar al portapapeles ---------- */
async function copyToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // Alternativa para navegadores/contextos sin Clipboard API.
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}
function buildCopyButton(text) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "copy-btn";
  btn.setAttribute("aria-label", "Copiar respuesta");
  btn.innerHTML = COPY_ICON + '<span class="copy-label">Copiar</span>';
  btn.addEventListener("click", async () => {
    const label = btn.querySelector(".copy-label");
    try {
      await copyToClipboard(text);
      btn.classList.add("copied");
      label.textContent = "¡Copiado!";
    } catch {
      label.textContent = "No se pudo copiar";
    }
    setTimeout(() => { label.textContent = "Copiar"; btn.classList.remove("copied"); }, 1500);
  });
  return btn;
}

/* ---------- Render de mensajes ---------- */
function buildMessage(role, text, { isError = false, animate = false } = {}) {
  const msg = document.createElement("div");
  msg.className = "msg " + (role === "user" ? "user" : "bot") + (isError ? " error" : "");
  if (role === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "msg-avatar";
    avatar.innerHTML = BOT_AVATAR;
    msg.appendChild(avatar);
  }

  const bubbleWrap = document.createElement("div");
  bubbleWrap.className = "bubble-wrap";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (role === "bot" && !isError) {
    if (animate) typeWriter(bubble, text, () => {});
    else bubble.innerHTML = renderMarkdown(text);
  } else {
    bubble.textContent = text;
  }
  bubbleWrap.appendChild(bubble);

  if (role === "bot" && !isError) bubbleWrap.appendChild(buildCopyButton(text));

  msg.appendChild(bubbleWrap);
  return msg;
}

function addMessage(role, rawText, { isError = false, animate = false } = {}) {
  const welcome = document.getElementById("welcome");
  if (welcome) welcome.remove();

  const text = (role === "bot" && !isError) ? stripWrappingCodeFence(rawText) : rawText;
  chatWindow.appendChild(buildMessage(role, text, { isError, animate }));
  scrollToBottom();
  if (!isError) { history.push({ role, text }); saveHistory(); }
}

function showTyping() {
  const msg = document.createElement("div");
  msg.className = "msg bot typing";
  msg.id = "typing";
  msg.innerHTML = `<div class="msg-avatar">${BOT_AVATAR}</div><div class="bubble"><span></span><span></span><span></span></div>`;
  chatWindow.appendChild(msg);
  scrollToBottom();
}
function hideTyping() { const t = document.getElementById("typing"); if (t) t.remove(); }
function scrollToBottom() { chatWindow.scrollTop = chatWindow.scrollHeight; }

/* ---------- Sonido sutil de notificacion (Web Audio API, sin archivos) ---------- */
let audioCtx = null;
function getAudioCtx() {
  const AudioCtor = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtor) return null;
  if (!audioCtx) audioCtx = new AudioCtor();
  return audioCtx;
}
function playNotificationSound() {
  if (!soundEnabled) return;
  const ctx = getAudioCtx();
  if (!ctx) return;
  if (ctx.state === "suspended") ctx.resume();

  // Tono corto, suave y ascendente (tipo "pop"), a volumen muy bajo.
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(660, now);
  osc.frequency.exponentialRampToValueAtTime(880, now + 0.09);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(0.05, now + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
  osc.connect(gain).connect(ctx.destination);
  osc.start(now);
  osc.stop(now + 0.2);
}
function updateSoundButton() {
  if (!soundToggleBtn) return;
  soundToggleBtn.innerHTML = soundEnabled ? SOUND_ON_ICON : SOUND_OFF_ICON;
  soundToggleBtn.setAttribute("aria-pressed", String(soundEnabled));
  const label = soundEnabled ? "Silenciar sonido" : "Activar sonido";
  soundToggleBtn.title = label;
  soundToggleBtn.setAttribute("aria-label", label);
}
function toggleSound() {
  soundEnabled = !soundEnabled;
  safeSet("agroia_sound_enabled", String(soundEnabled));
  if (soundEnabled) getAudioCtx(); // crea/retoma el contexto en el mismo gesto del usuario
  updateSoundButton();
}

/* ---------- Envío ---------- */
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
      if (res.status === 503) addMessage("bot", "El servicio de IA no está disponible en este momento. Intenta de nuevo en un momento. 🥑", { isError: true });
      else addMessage("bot", "Ocurrió un problema al procesar tu mensaje (código " + res.status + ").", { isError: true });
      return;
    }
    const data = await res.json();
    if (data.session_id) { sessionId = data.session_id; safeSet("agroia_session", sessionId); }
    playNotificationSound();
    addMessage("bot", data.response || "(sin respuesta)", { animate: true });
  } catch (err) {
    hideTyping();
    addMessage("bot", "No pude conectar con el servidor. Verifica que el servicio esté encendido. 🌱", { isError: true });
  } finally {
    setLoading(false);
    input.focus();
  }
}

function setLoading(loading) {
  sendBtn.disabled = loading;
  input.disabled = loading;
  if (headerAvatar) headerAvatar.classList.toggle("is-thinking", loading);
}

function autoResize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
}

/* ---------- Nueva conversación ---------- */
function newConversation() {
  history = [];
  saveHistory();
  sessionId = null;
  safeRemove("agroia_session");
  location.reload();
}

/* ---------- Restaurar historial al cargar ---------- */
function restore() {
  if (history.length) {
    const welcome = document.getElementById("welcome");
    if (welcome) welcome.remove();
    for (const m of history) chatWindow.appendChild(buildMessage(m.role, m.text));
    scrollToBottom();
  }
}

/* ---------- Entrada por voz (Web Speech API) ---------- */
const SpeechRecognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let isListening = false;

function setListening(state) {
  isListening = state;
  if (!micBtn) return;
  micBtn.classList.toggle("is-listening", state);
  micBtn.setAttribute("aria-pressed", String(state));
  const label = state ? "Escuchando… (clic para detener)" : "Dictar por voz";
  micBtn.title = label;
  micBtn.setAttribute("aria-label", label);
}

function setupSpeechRecognition() {
  if (!micBtn) return;
  if (!SpeechRecognitionCtor) {
    // Navegador sin soporte: se desactiva el boton y se explica por que via tooltip.
    micBtn.disabled = true;
    const label = "El dictado por voz no está disponible en este navegador";
    micBtn.title = label;
    micBtn.setAttribute("aria-label", label);
    return;
  }
  recognition = new SpeechRecognitionCtor();
  recognition.lang = "es-MX";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.addEventListener("result", (event) => {
    const transcript = Array.from(event.results).map((r) => r[0].transcript).join(" ").trim();
    if (transcript) {
      input.value = input.value ? input.value + " " + transcript : transcript;
      autoResize();
    }
  });
  recognition.addEventListener("end", () => { setListening(false); input.focus(); });
  recognition.addEventListener("error", () => setListening(false));
}

function toggleListening() {
  if (!recognition) return;
  if (isListening) {
    recognition.stop();
    return;
  }
  try {
    recognition.start();
    setListening(true);
  } catch {
    // Puede lanzar si ya hay una sesion de reconocimiento activa; se ignora.
  }
}

/* ---------- Eventos ---------- */
sendBtn.addEventListener("click", () => sendMessage());
input.addEventListener("input", autoResize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
if (chips) chips.addEventListener("click", (e) => { if (e.target.classList.contains("chip")) sendMessage(e.target.textContent); });
if (newChatBtn) newChatBtn.addEventListener("click", newConversation);
if (soundToggleBtn) soundToggleBtn.addEventListener("click", toggleSound);
if (micBtn) micBtn.addEventListener("click", toggleListening);

restore();
setupSpeechRecognition();
updateSoundButton();
input.focus();
