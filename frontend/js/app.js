import { PUNTUACION, PUNTUACION_TRIUNFO } from "./deck.js";

const API = "/api";

// ---------------------------------------------------------------------------
// Constantes visuales
// ---------------------------------------------------------------------------

const ICONOS = { oros: "♦", copas: "♥", espadas: "♠", bastos: "♣" };
const LETRA  = { as: "A", tres: "3", siete: "7", ocho: "8", nueve: "9", sota: "10", caballo: "11", rey: "12" };

// Orden de palos y valores para ordenar la mano del humano
const ORDEN_PALOS  = ["oros", "copas", "espadas", "bastos"];
const ORDEN_VALORES = ["siete", "ocho", "nueve", "sota", "caballo", "rey", "tres", "as"]; // menor a mayor cante

function ordenarManoHumano(mano, triunfo) {
  return [...mano].sort((a, b) => {
    // Primero agrupar por palo: triunfo al final
    const paloA = a.palo === triunfo ? 4 : ORDEN_PALOS.indexOf(a.palo);
    const paloB = b.palo === triunfo ? 4 : ORDEN_PALOS.indexOf(b.palo);
    if (paloA !== paloB) return paloA - paloB;
    // Dentro del palo, menor a mayor cante
    return ORDEN_VALORES.indexOf(a.valor) - ORDEN_VALORES.indexOf(b.valor);
  });
}

// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// Estado local
// ---------------------------------------------------------------------------

let estadoActual = null;
let modoTesteo = false;
let testeoCode = ""; // session-only; never stored or logged
const turnoHumano = (estado) => modoTesteo ? [0, 2].includes(estado.turno) : estado.turno === 0;
const apiPartida = () => modoTesteo ? `${API}/testeo/${estadoActual.id}` : `${API}/partida/${estadoActual.id}`;
let iaJugando = false;
let bloqueadoPorCante = false;
let bolotTimeout = null;
let canteMenuAbierto = false;
let cantesYaMostrados = new Set();
let bazaMostrandose = false;   // evita que render() sobreescriba mostrarBazaCompletada

const TIPOS_ENSENYA = new Set(["tercera", "cincuenta", "cien_seq", "cien_cuatro", "ciento_cincuenta", "doscientos"]);

// Multijugador
let modoMulti = false;
let miSlot = null;          // índice 0-3 de este jugador en la sala
let miNombre = null;        // nombre del jugador
let codigoSala = null;
let wsConexion = null;      // WebSocket activo
let wsReconectarTimer = null;
let wsReconectarIntentos = 0;
let wsHeartbeatTimer = null;
let timerInterval = null;   // setInterval del temporizador de turno
let modoEspectador = false; // true = modo solo-lectura, sin acciones

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function $(sel) { return document.querySelector(sel); }

// Devuelve el nombre visible de un slot. En modo multi usa el nombre real; en 1J usa JN para IAs.
function nombreJ(slot, estado) {
  const jugadorPropio = modoMulti ? miSlot : 0;
  if (slot === jugadorPropio || (modoTesteo && slot === 2)) return slot === 2 ? "Tú (J2)" : "Tú";
  return estado?.nombres?.[slot] || `J${slot}`;
}

// ---------------------------------------------------------------------------
// Sesión persistente (localStorage) — permite volver tras recargar
// ---------------------------------------------------------------------------

function guardarSesion() {
  if (codigoSala !== null && miSlot !== null && miNombre) {
    localStorage.setItem("bolot_sesion", JSON.stringify({ codigo: codigoSala, slot: miSlot, nombre: miNombre }));
  }
}

function limpiarSesion() { localStorage.removeItem("bolot_sesion"); }

function sesionGuardada() {
  try { const s = localStorage.getItem("bolot_sesion"); return s ? JSON.parse(s) : null; }
  catch { return null; }
}

function mostrarPanelReconectar(sesion) {
  const panel = $("#reconectar-panel");
  if (!panel) return;
  panel.querySelector(".rc-codigo").textContent = sesion.codigo;
  panel.querySelector(".rc-nombre").textContent = sesion.nombre;
  panel.classList.remove("oculto");
}

function ocultarPanelReconectar() {
  const panel = $("#reconectar-panel");
  if (panel) panel.classList.add("oculto");
}

async function reconectarSesion() {
  const sesion = sesionGuardada();
  if (!sesion) return;
  try {
    const res = await apiPost(`${API}/sala/${sesion.codigo}/unirse`, {
      nombre: sesion.nombre,
      slot_esperado: sesion.slot,
    });
    miSlot = res.slot;
    codigoSala = sesion.codigo;
    miNombre = sesion.nombre;
    modoMulti = true;
    guardarSesion();
    ocultarPanelReconectar();
    mostrarPantallaSala(res.sala);
    conectarWS();
  } catch (e) {
    limpiarSesion();
    ocultarPanelReconectar();
    alert("No se pudo retomar la partida: " + e.message);
  }
}

function puntosCartaEnJuego(carta, triunfo) {
  if (triunfo && carta.palo === triunfo) return PUNTUACION_TRIUNFO[carta.valor] ?? 0;
  return PUNTUACION[carta.valor] ?? 0;
}

function esJugable(carta, jugables) {
  if (!jugables || jugables.length === 0) return false;
  return jugables.some(j => j.palo === carta.palo && j.valor === carta.valor);
}

// ---------------------------------------------------------------------------
// SVG de palos españoles
// ---------------------------------------------------------------------------

function svgPalo(palo, sz) {
  const s = sz;
  switch (palo) {
    case 'oros':
      return `<svg viewBox="0 0 24 24" width="${s}" height="${s}" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10.5" fill="#e6b400" stroke="#a07800" stroke-width="2"/>
        <circle cx="12" cy="12" r="6" fill="#f5d800" stroke="#a07800" stroke-width="1.5"/>
        <circle cx="12" cy="12" r="2.2" fill="#a07800"/>
      </svg>`;
    case 'copas':
      return `<svg viewBox="0 0 22 28" width="${Math.round(s*0.79)}" height="${s}" xmlns="http://www.w3.org/2000/svg">
        <path d="M2,2 C2,15 11,16 11,16 C11,16 20,15 20,2 Z" fill="#c81818" stroke="#8a0000" stroke-width="1.5"/>
        <rect x="9" y="16" width="4" height="6" fill="#c81818"/>
        <rect x="3" y="22" width="16" height="4" rx="2" fill="#c81818" stroke="#8a0000" stroke-width="1"/>
      </svg>`;
    case 'espadas':
      return `<svg viewBox="0 0 18 28" width="${Math.round(s*0.64)}" height="${s}" xmlns="http://www.w3.org/2000/svg">
        <polygon points="9,1 11.5,21 9,27 6.5,21" fill="#1638c0" stroke="#0c2490" stroke-width="0.8"/>
        <rect x="1" y="17.5" width="16" height="4" rx="2" fill="#1638c0" stroke="#0c2490" stroke-width="0.8"/>
      </svg>`;
    case 'bastos':
      return `<svg viewBox="0 0 16 28" width="${Math.round(s*0.57)}" height="${s}" xmlns="http://www.w3.org/2000/svg">
        <ellipse cx="8" cy="14" rx="5" ry="11.5" fill="#2a8c14" stroke="#1a5a0c" stroke-width="2"/>
        <ellipse cx="8" cy="3.5"  rx="3.5" ry="3"    fill="#3aaa1e" stroke="#1a5a0c" stroke-width="1.5"/>
        <ellipse cx="8" cy="24.5" rx="3.5" ry="3"    fill="#3aaa1e" stroke="#1a5a0c" stroke-width="1.5"/>
      </svg>`;
  }
}

// ---------------------------------------------------------------------------
// Fallback SVG (cuando no hay imagen real)
// ---------------------------------------------------------------------------

function svgFallback(carta, triunfo, num, cntSz, crnSz, pts) {
  const isFace = ['sota', 'caballo', 'rey'].includes(carta.valor);
  return `
    <div class="c-tl"><span class="c-num">${num}</span>${svgPalo(carta.palo, crnSz)}</div>
    ${isFace
      ? `<div class="c-face"><span class="c-face-num">${num}</span></div>`
      : `<div class="c-cnt">${svgPalo(carta.palo, cntSz)}</div>`}
    <div class="c-br"><span class="c-num">${num}</span>${svgPalo(carta.palo, crnSz)}</div>
    ${pts > 0 ? `<div class="c-pts">${pts}</div>` : ""}
  `;
}

// ---------------------------------------------------------------------------
// Crear elemento carta
// ---------------------------------------------------------------------------

function crearElementoCarta(carta, triunfo, opciones = {}) {
  const { clickable = false, jugable = false, faceDown = false, pequeña = false, onClick = null, extraClass = "" } = opciones;
  const el = document.createElement("div");

  if (faceDown) {
    el.className = ["carta", "carta-dorso", pequeña ? "carta-pequeña" : "", extraClass].filter(Boolean).join(" ");
    el.innerHTML = '<div class="dorso-inner"></div>';
  } else {
    const esTriunfo = triunfo && triunfo === carta.palo;
    el.className = [
      "carta", `palo-${carta.palo}`,
      esTriunfo ? "triunfo" : "",
      clickable && jugable ? "jugable" : "",
      clickable && !jugable ? "no-jugable" : "",
      pequeña ? "carta-pequeña" : "",
      extraClass,
    ].filter(Boolean).join(" ");

    const num   = LETRA[carta.valor];
    const pts   = puntosCartaEnJuego(carta, triunfo);
    const cntSz = pequeña ? 26 : 40;
    const crnSz = pequeña ?  9 : 12;
    const imgSrc = `cards/${carta.palo}_${num}.svg`;

    // Intentar cargar imagen real; si falla, usar SVG
    const imgEl = document.createElement("img");
    imgEl.src = imgSrc;
    imgEl.className = "carta-img";
    imgEl.alt = `${num} de ${carta.palo}`;
    imgEl.onerror = function() {
      // Imagen no encontrada: reemplazar con diseño SVG
      this.parentElement.innerHTML = svgFallback(carta, triunfo, num, cntSz, crnSz, pts);
    };

    // Insertar estructura con imagen (se sustituye en onerror si falla)
    el.innerHTML = `${pts > 0 ? `<div class="c-pts">${pts}</div>` : ""}`;
    el.insertBefore(imgEl, el.firstChild);
  }

  if (onClick) el.addEventListener("click", onClick);
  return el;
}

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function apiPost(url, body = {}) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(url.startsWith(`${API}/testeo/`) ? {"X-Testeo-Code": testeoCode} : {}) },
    body: JSON.stringify(body),
  });
  let data;
  try { data = await res.json(); } catch { throw new Error("Respuesta inválida del servidor"); }
  if (!res.ok) {
    const d = data.detail;
    const msg = Array.isArray(d) ? d.map(e => e.msg).join("; ") : (d ?? "Error del servidor");
    throw new Error(msg);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Acciones de juego
// ---------------------------------------------------------------------------

async function animarReparto(dealer) {
  const overlay  = $("#deal-overlay");
  const msgEl    = $("#deal-msg");
  const nDealer  = nombreJ(dealer, estadoActual);
  const quien    = nDealer === "Tú" ? "Tú repartes" : `${nDealer} reparte`;
  msgEl.textContent = quien + "…";
  overlay.classList.remove("oculto");
  if (!modoTesteo) await delay(2000);
  overlay.classList.add("oculto");
}

async function arrancarTrasReparto() {
  const faseSubasta = f => f === "subasta_primeras" || f === "subasta_segundas";
  if (faseSubasta(estadoActual.fase) && !turnoHumano(estadoActual)) {
    await playIASubasta();
  } else if (estadoActual.fase === "bazas" && !turnoHumano(estadoActual)) {
    await playIA();
  }
}

async function nuevaPartida() {
  modoTesteo = false; testeoCode = "";
  const objetivo = parseInt($("#sel-objetivo").value);
  try {
    cantesYaMostrados = new Set();
    estadoActual = await apiPost(`${API}/partida/nueva`, { objetivo });
    mostrarMesa();
    aplicarRotacion();
    actualizarEtiquetas({});
    await animarReparto(estadoActual.dealer);
    render(estadoActual);
    await arrancarTrasReparto();
  } catch (e) {
    alert("Error al crear partida: " + e.message);
  }
}

async function iniciarTesteo() {
  const code = prompt("Código de acceso a testeo");
  if (!code) return;
  testeoCode = code; modoTesteo = true;
  const objetivo = parseInt($("#sel-objetivo-testeo").value);
  try {
    estadoActual = await apiPost(`${API}/testeo/nueva`, { objetivo });
    cantesYaMostrados = new Set();
    mostrarMesa(); aplicarRotacion(); actualizarEtiquetas({});
    await animarReparto(estadoActual.dealer);
    render(estadoActual); await arrancarTrasReparto();
  } catch (e) { modoTesteo = false; testeoCode = ""; alert("Testeo no iniciado: " + e.message); }
}

async function nuevaMano() {
  cantesYaMostrados = new Set();
  canteMenuAbierto = false;
  if (modoMulti) { wsSend({ tipo: "nueva_mano" }); return; }
  try {
    estadoActual = await apiPost(`${apiPartida()}/nueva-mano`);
    await animarReparto(estadoActual.dealer);
    render(estadoActual);
    await arrancarTrasReparto();
  } catch (e) {
    mostrarError(e.message);
  }
}

async function votarSubasta(accion, palo = null) {
  if (modoMulti) {
    wsSend({ tipo: "subasta", accion, palo });
    return;
  }
  try {
    estadoActual = await apiPost(
      `${apiPartida()}/subasta`,
      { accion, palo }
    );
    render(estadoActual);

    const faseSubasta = f => f === "subasta_primeras" || f === "subasta_segundas";
    if (faseSubasta(estadoActual.fase) && !turnoHumano(estadoActual)) {
      await playIASubasta();
    } else if (estadoActual.fase === "bazas" && !turnoHumano(estadoActual)) {
      await playIA();
    }
  } catch (e) {
    mostrarError(e.message);
  }
}

async function jugarCarta(carta) {
  if (bloqueadoPorCante) return;
  if (modoMulti) {
    cancelarTimerTurno();
    wsSend({ tipo: "jugar", palo: carta.palo, valor: carta.valor });
    return;
  }
  if (iaJugando) return;
  const prevBazaCount = estadoActual.bazas_jugadas.length;
  try {
    estadoActual = await apiPost(
      `${apiPartida()}/jugar`,
      { palo: carta.palo, valor: carta.valor }
    );
    // Hacer visible el aviso de cinco segundos antes de animar la baza.
    if (estadoActual.bolot_pendiente) renderBolotPendiente(estadoActual);
    if (estadoActual.bazas_jugadas.length > prevBazaCount) {
      await mostrarBazaCompletada(
        estadoActual.bazas_jugadas[estadoActual.bazas_jugadas.length - 1],
        estadoActual.triunfo
      );
    }
    render(estadoActual);

    if (!modoMulti) {
      if (!turnoHumano(estadoActual) && estadoActual.fase === "bazas" && !estadoActual.bolot_pendiente) await playIA();
    }
  } catch (e) {
    mostrarError(e.message);
  }
}

function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

async function mostrarBazaCompletada(baza, triunfo) {
  bazaMostrandose = true;
  const el = $("#baza-actual");
  el.innerHTML = "";
  const slots = {};
  [0, 1, 2, 3].forEach(j => {
    const slot = document.createElement("div");
    slot.className = `baza-slot baza-pos-${posicionBaza(j)}`;
    el.appendChild(slot);
    slots[j] = slot;
  });
  for (const { jugador, carta } of baza.cartas) {
    const wrap = document.createElement("div");
    wrap.className = "carta-en-baza";
    const label = document.createElement("span");
    label.className = `baza-jugador-label eq${jugador % 2}`;
    label.textContent = nombreJ(jugador, estadoActual);
    wrap.appendChild(label);
    wrap.appendChild(crearElementoCarta(carta, triunfo, { extraClass: "carta-mesa-grande" }));
    slots[jugador].appendChild(wrap);
  }
  // Badge de ganador
  const badge = document.createElement("div");
  badge.className = `baza-win-badge eq${baza.ganador % 2}`;
  badge.textContent = `${nombreJ(baza.ganador, estadoActual)} gana · ${baza.puntos}pts`;
  slots[baza.ganador].appendChild(badge);
  await delay(3000);
  bazaMostrandose = false;
}

// ---------------------------------------------------------------------------
// Overlay de subasta
// ---------------------------------------------------------------------------

function mostrarOverlaySubasta(texto, clase) {
  const overlay = $("#subasta-overlay");
  overlay.className = `subasta-overlay ${clase}`;
  overlay.querySelector(".subasta-overlay-text").textContent = texto;
}

function ocultarOverlaySubasta() {
  const overlay = $("#subasta-overlay");
  overlay.className = "subasta-overlay oculto";
}

async function playIASubasta() {
  iaJugando = true;
  const faseSubasta = f => f === "subasta_primeras" || f === "subasta_segundas";

  while (faseSubasta(estadoActual.fase) && !turnoHumano(estadoActual)) {
    const prevTurno   = estadoActual.turno;
    const prevFase    = estadoActual.fase;
    const prevTriunfo = estadoActual.triunfo;

    // Mostrar "está decidiendo..."
    mostrarOverlaySubasta(`${nombreJ(prevTurno, estadoActual)} está decidiendo…`, "decidiendo");
    if (!modoTesteo) await delay(1800);

    try {
      estadoActual = await apiPost(`${apiPartida()}/siguiente`, {});
    } catch (e) {
      ocultarOverlaySubasta();
      mostrarError(e.message);
      break;
    }

    // Determinar qué decidió: solo es "va" si la fase pasó a bazas
    const vaBool = estadoActual.fase === "bazas";

    let textoDecision;
    if (vaBool) {
      const paloStr = estadoActual.triunfo
        ? ` → ${ICONOS[estadoActual.triunfo]} ${estadoActual.triunfo}`
        : "";
      textoDecision = `${nombreJ(prevTurno, estadoActual)} ¡Va${paloStr}!`;
    } else {
      textoDecision = `${nombreJ(prevTurno, estadoActual)} no va`;
    }

    mostrarOverlaySubasta(textoDecision, vaBool ? "voy" : "pasa");
    render(estadoActual);
    if (!modoTesteo) await delay(1800);
  }

  ocultarOverlaySubasta();

  // Si el turno de bazas no es del humano, animar IA
  if (estadoActual.fase === "bazas" && !turnoHumano(estadoActual)) {
    await playIA();
  }
  iaJugando = false;
}

async function playIA() {
  if (modoMulti) return;
  iaJugando = true;
  let acabaDeEnsenyar = false;
  while (!turnoHumano(estadoActual) && estadoActual.fase !== "fin_mano") {
    if (!modoTesteo) await delay(acabaDeEnsenyar ? 300 : Math.floor(Math.random() * 3000) + 3000);
    acabaDeEnsenyar = false;
    const prevBazaCount = estadoActual.bazas_jugadas.length;
    const prevEnsenados = estadoActual.cantes_ensenados || {};
    try {
      estadoActual = await apiPost(`${apiPartida()}/siguiente`, {});
      const jugadorQueEnsenya = Object.keys(estadoActual.cantes_ensenados || {}).find(
        j => (estadoActual.cantes_ensenados[j]?.length || 0) > (prevEnsenados[j]?.length || 0)
      );
      if (jugadorQueEnsenya !== undefined) {
        render(estadoActual);
        await mostrarCantesJugador(Number(jugadorQueEnsenya), estadoActual.cantes_ensenados[jugadorQueEnsenya], estadoActual);
        acabaDeEnsenyar = true;
        continue; // La siguiente petición hará que la IA tire, después de enseñar.
      }
      if (estadoActual.bazas_jugadas.length > prevBazaCount) {
        await mostrarBazaCompletada(
          estadoActual.bazas_jugadas[estadoActual.bazas_jugadas.length - 1],
          estadoActual.triunfo
        );
      }
      render(estadoActual);
    } catch (e) {
      mostrarError(e.message);
      break;
    }
  }

  iaJugando = false;
}

// ---------------------------------------------------------------------------
// Render principal
// ---------------------------------------------------------------------------

function render(estado) {
  renderMarcador(estado);
  renderTriunfoBadge(estado);
  renderPuntosMano(estado);
  renderDealerBadge(estado);
  renderCartaMesa(estado);
  renderBazaActual(estado);
  renderManos(estado);
  renderTurnoIndicadores(estado);
  renderAcciones(estado);
  renderCantesPendientes(estado);
  renderBolotPendiente(estado);
  renderCantes(estado);
  renderMensajeFase(estado);
  renderBtnNuevaMano(estado);
  renderBtnUltimaBaza(estado);
  renderHistorial(estado);
  renderAnunciosPrimera(estado);
}

const NOMBRE_CANTE_BUBBLE = {
  tercera: "Tercera · 20pts",
  cincuenta: "Cincuenta · 50pts",
  cien_seq: "Cien (escalera) · 100pts",
  cien_cuatro: "Cien (cuatro) · 100pts",
  ciento_cincuenta: "150pts",
  doscientos: "200pts",
};

function renderAnunciosPrimera(estado) {
  const anuncios = estado.anuncios_primera || {};
  // Mostrar durante la primera (bazas_jugadas === 0) y en la transición a la segunda (=== 1)
  const activo = estado.bazas_jugadas.length <= 1 && Object.keys(anuncios).length > 0;

  for (let j = 0; j < 4; j++) {
    const zona = $(`#zona-j${j}`);
    if (!zona) continue;
    let bubble = zona.querySelector(".cante-bubble");

    const tipo = anuncios[String(j)]; // claves son strings desde el backend
    if (activo && tipo !== undefined && tipo !== null) {
      if (!bubble) {
        bubble = document.createElement("div");
        bubble.className = "cante-bubble";
        zona.appendChild(bubble);
      }
      bubble.textContent = tipo.split(", ").map(t => NOMBRE_CANTE_BUBBLE[t] || t).join(" + ");
    } else {
      if (bubble) bubble.remove();
    }
  }
}

function renderDealerBadge(estado) {
  for (let j = 0; j < 4; j++) {
    const chip = $(`#dealer-j${j}`);
    if (chip) chip.classList.toggle("oculto", estado.dealer !== j);
  }
}

function renderMarcador(estado) {
  $("#pts-eq0").textContent = estado.puntos_totales[0];
  $("#pts-eq1").textContent = estado.puntos_totales[1];
  $("#objetivo-label").textContent = `/ ${estado.objetivo}`;
}

function renderTriunfoBadge(estado) {
  const badge = $("#triunfo-badge");
  if (estado.triunfo) {
    badge.textContent = `Triunfo: ${ICONOS[estado.triunfo]} ${estado.triunfo}`;
    badge.className = `triunfo-badge palo-${estado.triunfo}`;
  } else if (estado.triunfo_propuesto) {
    badge.textContent = `Propuesto: ${ICONOS[estado.triunfo_propuesto]} ${estado.triunfo_propuesto}`;
    badge.className = `triunfo-badge triunfo-propuesto palo-${estado.triunfo_propuesto}`;
  } else {
    badge.className = "triunfo-badge oculto";
  }

  const qvBadge = $("#quien-va-badge");
  if (estado.quien_va !== null && estado.quien_va !== undefined && estado.fase !== "fin_mano") {
    const j = estado.quien_va;
    const nVa = nombreJ(j, estado);
    const quien = nVa === "Tú" ? "Tú vas" : `${nVa} va`;
    const eq = j % 2;
    const paloStr = estado.triunfo ? ` a ${ICONOS[estado.triunfo]} ${estado.triunfo}` : "";
    qvBadge.textContent = `⚑ ${quien}${paloStr}`;
    qvBadge.className = `quien-va-badge eq${eq}`;
  } else {
    qvBadge.className = "quien-va-badge oculto";
  }
}

function renderPuntosMano(estado) {
  const badge = $("#puntos-mano-badge");
  if (estado.fase === "bazas" || estado.fase === "fin_mano") {
    const [p0, p1] = estado.puntos_mano;
    badge.textContent = `Esta mano: ${p0} – ${p1}`;
    badge.className = "puntos-mano-badge";
  } else {
    badge.className = "puntos-mano-badge oculto";
  }
}

function renderCartaMesa(estado) {
  const wrap = $("#carta-mesa-wrap");
  const el = $("#carta-mesa");
  if (estado.carta_mesa) {
    wrap.classList.remove("oculto");
    el.innerHTML = "";
    el.appendChild(crearElementoCarta(estado.carta_mesa, estado.triunfo_propuesto));
  } else {
    wrap.classList.add("oculto");
  }
}

// Posición de cada jugador en la baza central según la rotación
const BAZA_POS = ["bot", "right", "top", "left"]; // delta 0,1,2,3

function posicionBaza(jugador) {
  const base = modoMulti ? (miSlot ?? 0) : 0;
  const delta = (jugador - base + 4) % 4;
  return BAZA_POS[delta];
}

function renderBazaActual(estado) {
  if (bazaMostrandose) return;  // no interrumpir la animación de baza completada
  const el = $("#baza-actual");
  el.innerHTML = "";

  // Crear 4 slots posicionales rotados
  const slots = {};
  [0, 1, 2, 3].forEach(j => {
    const slot = document.createElement("div");
    slot.className = `baza-slot baza-pos-${posicionBaza(j)}`;
    el.appendChild(slot);
    slots[j] = slot;
  });

  for (const { jugador, carta } of estado.baza_actual.cartas) {
    const wrap = document.createElement("div");
    wrap.className = "carta-en-baza";
    const label = document.createElement("span");
    label.className = `baza-jugador-label eq${jugador % 2}`;
    label.textContent = nombreJ(jugador, estado);
    wrap.appendChild(label);
    wrap.appendChild(crearElementoCarta(carta, estado.triunfo, { extraClass: "carta-mesa-grande" }));
    slots[jugador].appendChild(wrap);
  }
}

function renderManos(estado) {
  const jugables = estado.jugables_humano ?? [];
  const triunfo = estado.triunfo;
  // En testeo el humano controla J0 y J2: ambas manos siempre boca arriba.
  const esManoHumana = (j) => modoMulti ? j === miSlot : (modoTesteo ? (j === 0 || j === 2) : j === 0);

  for (let j = 0; j < 4; j++) {
    const contenedor = $(`#mano-j${j}`);
    contenedor.innerHTML = "";

    const esPropio = esManoHumana(j);
    const manoData = estado.manos[j];
    if (!Array.isArray(manoData)) {
      for (let i = 0; i < manoData; i++) contenedor.appendChild(crearElementoCarta(null, null, {faceDown:true}));
      continue;
    }

    // En multi, las manos ajenas son un número (conteo), no array
    if (!esPropio) {
      const count = typeof manoData === "number" ? manoData : (manoData?.length ?? 0);
      const base  = modoMulti ? (miSlot ?? 0) : 0;
      const delta = (j - base + 4) % 4;
      const pequeña = delta === 1 || delta === 3; // laterales = cartas pequeñas
      for (let i = 0; i < count; i++) {
        contenedor.appendChild(crearElementoCarta(null, null, { faceDown: true, pequeña }));
      }
      continue;
    }

    // Mano humana: boca arriba; clicable solo en su turno
    const esSuTurno = estado.turno === j && estado.fase === "bazas";
    const manoOrdenada = ordenarManoHumano(manoData, triunfo);
    manoOrdenada.forEach(carta => {
      const jugable = esSuTurno && esJugable(carta, jugables);
      const clickable = esSuTurno;
      contenedor.appendChild(crearElementoCarta(carta, triunfo, {
        clickable,
        jugable,
        pequeña: false,
        onClick: clickable && jugable ? () => jugarCarta(carta) : null,
      }));
    });
  }
}

function renderTurnoIndicadores(estado) {
  for (let j = 0; j < 4; j++) {
    const el = $(`#turno-j${j}`);
    if (estado.turno === j && estado.fase !== "fin_mano") {
      el.classList.remove("oculto");
    } else {
      el.classList.add("oculto");
    }
  }
}

// ---------------------------------------------------------------------------
// Temporizador de turno
// ---------------------------------------------------------------------------

function cancelarTimerTurno() {
  if (timerInterval !== null) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  const el = $("#timer-turno");
  if (el) { el.classList.add("oculto"); el.classList.remove("urgente"); }
}

function iniciarTimerTurno(segundos) {
  cancelarTimerTurno();
  let restante = segundos;
  const el = $("#timer-turno");
  if (!el) return;
  el.classList.remove("oculto");
  el.textContent = restante;
  el.classList.toggle("urgente", restante <= 5);

  timerInterval = setInterval(() => {
    restante--;
    if (el) {
      el.textContent = restante;
      el.classList.toggle("urgente", restante <= 5);
    }
    if (restante <= 0) {
      cancelarTimerTurno();
      wsSend({ tipo: "auto_jugar" });
    }
  }, 1000);
}

function renderAcciones(estado) {
  const el = $("#acciones");
  el.innerHTML = "";
  if (modoEspectador) return;

  const jugadorPropio = modoMulti ? miSlot : (modoTesteo ? ([0, 2].includes(estado.turno) ? estado.turno : -1) : 0);
  const nombres = estado.nombres || {};

  if (estado.fase === "subasta_primeras" && estado.turno === jugadorPropio) {
    const palo = estado.triunfo_propuesto;
    el.innerHTML = `<p class="accion-label">¿Aceptas <strong>${ICONOS[palo]} ${palo}</strong> como triunfo?</p>`;

    const btnVoy = document.createElement("button");
    btnVoy.textContent = "Voy";
    btnVoy.className = "btn-accion btn-voy";
    btnVoy.addEventListener("click", () => votarSubasta("voy"));
    el.appendChild(btnVoy);

    const btnNo = document.createElement("button");
    btnNo.textContent = "No voy";
    btnNo.className = "btn-accion btn-no-voy";
    btnNo.addEventListener("click", () => votarSubasta("no_voy"));
    el.appendChild(btnNo);
  }

  if (estado.fase === "subasta_segundas" && estado.turno === jugadorPropio) {
    const paloPropuesto = estado.triunfo_propuesto;
    el.innerHTML = `<p class="accion-label">De segundas. ¿Propones triunfo?</p>`;

    const divPalos = document.createElement("div");
    divPalos.className = "palos-segundas";

    ["oros", "copas", "espadas", "bastos"].forEach(palo => {
      if (palo === paloPropuesto) return;
      const btn = document.createElement("button");
      btn.textContent = `${ICONOS[palo]} ${palo}`;
      btn.className = `btn-accion btn-palo palo-${palo}`;
      btn.addEventListener("click", () => votarSubasta("voy", palo));
      divPalos.appendChild(btn);
    });
    el.appendChild(divPalos);

    const btnNo = document.createElement("button");
    btnNo.textContent = "No voy";
    btnNo.className = "btn-accion btn-no-voy";
    btnNo.addEventListener("click", () => votarSubasta("no_voy"));
    el.appendChild(btnNo);
  }

  if (estado.fase === "subasta_primeras" && estado.turno !== jugadorPropio) {
    const quien = nombres[estado.turno] || `J${estado.turno}`;
    el.innerHTML = `<p class="accion-label esperando">${modoMulti ? quien : "La máquina"} está decidiendo…</p>`;
  }

  if (estado.fase === "bazas" && estado.turno === jugadorPropio) {
    el.innerHTML = `<p class="accion-label tu-turno">Tu turno — elige una carta</p>`;
    if (estado.bazas_jugadas.length === 0 && (estado.cantes_disponibles?.length || estado.cantes_anunciados_propios?.length)) {
      const boton = document.createElement("button");
      boton.id = "btn-cantar"; boton.textContent = "Cantar";
      boton.addEventListener("click", () => { canteMenuAbierto = !canteMenuAbierto; renderCantesPendientes(estadoActual); });
      el.appendChild(boton);
    }
    if (estado.puede_ensenar_cantes) {
      const boton = document.createElement("button");
      boton.id = "btn-ensenar"; boton.textContent = "Enseñar cantes";
      boton.addEventListener("click", ensenarCantesManual);
      el.appendChild(boton);
    }
    if (estado.bolot_disponible) {
      const boton = document.createElement("button");
      boton.id = "btn-bolot-turno";
      boton.textContent = estado.bolot_disponible === "rebolot" ? "¡Rebolot!" : "¡Bolot!";
      boton.addEventListener("click", pulsarBolot);
      el.appendChild(boton);
    }
    if (modoMulti && estado.con_limite && timerInterval === null) iniciarTimerTurno(20);
  }

  if (estado.fase === "bazas" && estado.turno !== jugadorPropio) {
    const quien = nombres[estado.turno] || `J${estado.turno}`;
    el.innerHTML = `<p class="accion-label esperando">Turno de ${quien}…</p>`;
    cancelarTimerTurno();
  }
}

const NOMBRE_CANTE = {
  tercera: "Tercera", cincuenta: "Cincuenta", cien_seq: "Cien (escalera)",
  cien_cuatro: "Cien (cuatro)", ciento_cincuenta: "Ciento cincuenta",
  doscientos: "Doscientos", bolot: "Bolot", rebolot: "Rebolot",
};

function cantesDeJugador(jugador, estado) {
  const enCantes = estado.cantes.filter(c => c.jugador === jugador && TIPOS_ENSENYA.has(c.tipo));
  // Incluir pendientes del jugador propio (en multi miSlot puede ser != 0)
  const jugadorPropio = modoMulti ? miSlot : (modoTesteo ? ([0, 2].includes(estado.turno) ? estado.turno : -1) : 0);
  if (jugador === jugadorPropio) {
    const pendientes = (estado.cantes_pendientes_humano ?? []).filter(c => TIPOS_ENSENYA.has(c.tipo));
    return [...enCantes, ...pendientes];
  }
  return enCantes;
}

function jugadorDebeEnsenyar(jugador, estado) {
  if (estado.bazas_jugadas.length !== 1) return false;
  if (cantesYaMostrados.has(jugador)) return false;
  return cantesDeJugador(jugador, estado).length > 0;
}

async function mostrarCantesJugador(jugador, cantes, estado) {
  if (!cantes?.length) return;

  cantesYaMostrados.add(jugador);

  const overlay   = $("#cante-mostrar-overlay");
  const tituloEl  = $("#cante-mostrar-titulo");
  const cartasEl  = $("#cante-mostrar-cartas");

  const nEns = nombreJ(jugador, estado);
  const quien = nEns === "Tú" ? "Tú enseñas" : `${nEns} enseña`;
  const tipos = [...new Set(cantes.map(c => NOMBRE_CANTE[c.tipo] ?? c.tipo))].join(", ");
  tituloEl.textContent = `${quien}: ${tipos}`;

  cartasEl.innerHTML = "";
  const cartasUnicas = new Map();
  cantes.forEach(c => c.cartas.forEach(carta => {
    const key = `${carta.palo}_${carta.valor}`;
    if (!cartasUnicas.has(key)) cartasUnicas.set(key, carta);
  }));
  cartasUnicas.forEach(carta => cartasEl.appendChild(crearElementoCarta(carta, estado.triunfo)));

  overlay.classList.remove("oculto");
  overlay.onclick = () => overlay.classList.add("oculto");
  await delay(modoTesteo ? 3500 : 5000);
  overlay.classList.add("oculto");
}

async function cantarCanteManual(clave) {
  try {
    if (modoMulti) { wsSend({tipo:"declarar_cante",tipo_cante:clave}); canteMenuAbierto = false; return; }
    estadoActual = await apiPost(`${apiPartida()}/declarar-cante`, {tipo:clave});
    canteMenuAbierto = false; render(estadoActual);
  } catch(e) { mostrarError(e.message); }
}

async function ensenarCantesManual() {
  try {
    if (modoMulti) { wsSend({tipo:"ensenar_cantes"}); return; }
    const seat = modoTesteo ? estadoActual.turno : 0;
    estadoActual = await apiPost(`${apiPartida()}/ensenar-cantes`);
    render(estadoActual);
    const ensenados = estadoActual.cantes_ensenados?.[seat];
    if (ensenados?.length) await mostrarCantesJugador(seat, ensenados, estadoActual);
  } catch(e) { mostrarError(e.message); }
}

async function pulsarBolot() {
  try {
    if (modoMulti) { wsSend({tipo:"bolot"}); return; }
    estadoActual = await apiPost(`${apiPartida()}/bolot`);
    render(estadoActual);
    if (!modoMulti && !turnoHumano(estadoActual) && estadoActual.fase === "bazas" && !iaJugando) await playIA();
  } catch(e) { mostrarError(e.message); }
}

function renderBolotPendiente(estado) {
  const panel = $("#bolot-pendiente-panel");
  if (!panel) return;
  const pendiente = estado.bolot_pendiente;
  if (!pendiente) {
    clearTimeout(bolotTimeout);
    panel.innerHTML = "";
    panel.classList.add("oculto");
    return;
  }
  const token = `${estado.id}:${pendiente.tipo}:${estado.bazas_jugadas.length}:${estado.baza_actual.cartas.length}`;
  if (panel.dataset.token === token && !panel.classList.contains("oculto") && panel.querySelector("#btn-bolot")) return;
  clearTimeout(bolotTimeout);
  panel.dataset.token = token;
  panel.innerHTML = "";
  panel.classList.remove("oculto");
  const boton = document.createElement("button");
  boton.id = "btn-bolot";
  boton.textContent = pendiente.tipo === "rebolot" ? "¡Rebolot!" : "¡Bolot!";
  boton.addEventListener("click", pulsarBolot);
  panel.appendChild(boton);
  bolotTimeout = setTimeout(() => {
    panel.classList.add("oculto"); panel.innerHTML = "";
    if (!modoMulti && estadoActual && !turnoHumano(estadoActual) && estadoActual.fase === "bazas" && !iaJugando) playIA();
  }, pendiente.vence_en * 1000);
}

function renderCantesPendientes(estado) {
  const panel = $("#cantes-pendientes-panel");
  if (!panel) return;
  const disponibles = estado.cantes_disponibles || [];
  const anunciados = estado.cantes_anunciados_propios || [];
  const abierto = canteMenuAbierto && estado.fase === "bazas" && estado.bazas_jugadas.length === 0 && (modoTesteo ? [0, 2].includes(estado.turno) : estado.turno === (modoMulti ? miSlot : 0));
  panel.classList.toggle("oculto", !abierto);
  panel.innerHTML = "";
  if (!abierto) return;
  const cerrar = document.createElement("button");
  cerrar.id = "btn-cerrar-cantes"; cerrar.type = "button"; cerrar.textContent = "Cerrar";
  cerrar.addEventListener("click", () => { canteMenuAbierto = false; renderCantesPendientes(estadoActual); });
  panel.appendChild(cerrar);
  const titulo = document.createElement("p");
  titulo.textContent = "Elige todos los cantes que quieras anunciar antes de tirar:";
  panel.appendChild(titulo);
  for (const cante of disponibles) {
    const boton = document.createElement("button");
    boton.className = "btn-cante-opcion";
    boton.textContent = `${NOMBRE_CANTE[cante.tipo] || cante.tipo} · ${cante.puntos} pts (${cante.cartas.map(c=>`${LETRA[c.valor]} ${c.palo}`).join(", ")})`;
    boton.addEventListener("click", () => cantarCanteManual(cante.clave));
    panel.appendChild(boton);
  }
  if (anunciados.length) {
    const nota = document.createElement("p");
    nota.textContent = `Anunciados: ${anunciados.map(c=>NOMBRE_CANTE[c.tipo]).join(", ")}`;
    panel.appendChild(nota);
  }
}

function renderCantes(estado) {
  const panel = $("#cantes-panel");
  if (!estado.cantes || estado.cantes.length === 0) {
    panel.classList.add("oculto");
    return;
  }
  panel.classList.remove("oculto");
  panel.innerHTML = "<strong>Cantes:</strong> " + estado.cantes.map(c => {
    const eq = c.jugador % 2;
    const quien = nombreJ(c.jugador, estado);
    return `<span class="cante-tag eq${eq}">${c.tipo} ${c.puntos}pts (${quien})</span>`;
  }).join(" ");
}

function renderMensajeFase(estado) {
  const el = $("#mensaje-fase");

  if (estado.fase === "fin_mano") {
    const [p0, p1] = estado.puntos_mano;
    const [c0, c1] = estado.cantes_equipo;
    const quienVa = estado.quien_va;
    const eqVa = quienVa !== null ? quienVa % 2 : null;
    const jugadorPropio = modoMulti ? miSlot : 0;
    const eqPropio = jugadorPropio % 2; // 0 o 1

    // Nombres de equipo para la tabla
    const n = [0,1,2,3].map(s => nombreJ(s, estado));
    const labelEq0 = `${n[0]} &amp; ${n[2]}`;
    const labelEq1 = `${n[1]} &amp; ${n[3]}`;

    // Quién ganó (desde perspectiva del jugador propio)
    const total0 = p0 + c0;
    const total1 = p1 + c1;
    const totalPropio  = eqPropio === 0 ? total0 : total1;
    const totalRival   = eqPropio === 0 ? total1 : total0;
    let resultado = "";
    if (quienVa === null) {
      resultado = "Mano nula — todos pasaron";
    } else if (eqVa === eqPropio && totalPropio > totalRival) {
      resultado = "¡Ganasteis la mano! 🎉";
    } else if (eqVa !== eqPropio && totalRival > totalPropio) {
      resultado = "Los rivales ganan la mano";
    } else if (eqVa === eqPropio && totalPropio <= totalRival) {
      resultado = "Estáis puestos — los rivales se llevan los puntos";
    } else {
      resultado = "Los rivales están puestos — os lleváis los puntos";
    }

    const capota = estado.capota_equipo;
    const capotaRow = capota !== null && capota !== undefined
      ? `<tr><td>Capotá +100</td><td>${capota === 0 ? "✓" : ""}</td><td>${capota === 1 ? "✓" : ""}</td></tr>`
      : "";

    el.innerHTML = `
      <div class="fin-mano-resumen">
        <h3>Fin de la mano</h3>
        <p class="resultado-mano">${resultado}</p>
        <table class="tabla-puntos">
          <tr><th></th><th>${labelEq0}</th><th>${labelEq1}</th></tr>
          <tr><td>Bazas</td><td>${p0}</td><td>${p1}</td></tr>
          <tr><td>Cantes</td><td>${c0}</td><td>${c1}</td></tr>
          ${capotaRow}
          <tr class="total"><td>Total mano</td><td>${total0}</td><td>${total1}</td></tr>
          <tr class="total-juego"><td>Total juego</td><td>${estado.puntos_totales[0]}</td><td>${estado.puntos_totales[1]}</td></tr>
        </table>
      </div>
    `;

    // Comprobar si alguien llegó al objetivo
    const obj = estado.objetivo;
    const [tot0, tot1] = estado.puntos_totales;
    if (tot0 >= obj || tot1 >= obj) {
      const eqGana = tot0 >= obj && tot0 >= tot1 ? 0 : 1;
      const ganador = eqGana === eqPropio ? "¡¡GANASTEIS LA PARTIDA!! 🏆" : "Los rivales ganan la partida";
      el.querySelector(".fin-mano-resumen").insertAdjacentHTML("beforeend",
        `<p class="fin-partida">${ganador}</p>`
      );
    }
  } else {
    el.innerHTML = "";
  }
}

function renderBtnNuevaMano(estado) {
  const btn = $("#btn-nueva-mano");
  const visible = estado.fase === "fin_mano" && (!modoMulti || miSlot === 0);
  btn.classList.toggle("oculto", !visible);
}

function renderBtnUltimaBaza(estado) {
  const btn = $("#btn-ver-ultima-baza");
  const hayBazas = estado?.bazas_jugadas?.length > 0 && estado.fase !== "fin_mano";
  btn.classList.toggle("oculto", !hayBazas);
  if (!hayBazas) ocultarUltimaBazaPanel();
}

function mostrarUltimaBazaPanel() {
  if (!estadoActual?.bazas_jugadas?.length) return;
  const ultima = estadoActual.bazas_jugadas[estadoActual.bazas_jugadas.length - 1];
  const triunfo = estadoActual.triunfo;
  const nombres = estadoActual.nombres || {};
  const panel = $("#ultima-baza-panel");
  panel.innerHTML = "";

  for (const { jugador, carta } of ultima.cartas) {
    const wrap = document.createElement("div");
    wrap.className = "ubp-carta";
    const nombre = document.createElement("span");
    nombre.textContent = nombres[jugador] || `J${jugador}`;
    wrap.appendChild(nombre);
    wrap.appendChild(crearElementoCarta(carta, triunfo, { pequeña: true }));
    panel.appendChild(wrap);
  }

  const label = document.createElement("div");
  label.className = "ubp-ganador-label";
  label.textContent = `${nombres[ultima.ganador] || `J${ultima.ganador}`} ganó · ${ultima.puntos}pts`;
  panel.appendChild(label);

  panel.classList.remove("oculto");
}

function ocultarUltimaBazaPanel() {
  $("#ultima-baza-panel")?.classList.add("oculto");
}

// ---------------------------------------------------------------------------
// Historial de bazas
// ---------------------------------------------------------------------------

function renderHistorial(estado) {
  const lista = $("#historial-lista");
  lista.innerHTML = "";

  const bazas = estado.bazas_jugadas;
  const triunfo = estado.triunfo;

  if (bazas.length === 0) {
    lista.innerHTML = `<p class="historial-vacio">Aún no se ha jugado ninguna baza</p>`;
    return;
  }

  // Más reciente primero; solo la última (idx=0) es face-up
  [...bazas].reverse().forEach((baza, idx) => {
    const num = bazas.length - idx;
    const ganador = baza.ganador;
    const eqGanador = ganador % 2;
    const ganadorStr = nombreJ(ganador, estado);
    const faceUp = idx === 0;

    const card = document.createElement("div");
    card.className = `baza-card eq${eqGanador}`;

    card.innerHTML = `
      <div class="baza-card-header">
        <span class="baza-num">Baza ${num}</span>
        <span class="baza-ganador eq${eqGanador}">${ganadorStr} · ${baza.puntos}pts</span>
      </div>
    `;

    const cartas = document.createElement("div");
    cartas.className = "baza-card-cartas";

    baza.cartas.forEach(({ jugador, carta }) => {
      const item = document.createElement("div");
      item.className = `baza-carta-item ${faceUp && jugador === ganador ? "ganadora" : ""}`;
      if (faceUp) {
        const jLabel = document.createElement("span");
        jLabel.className = `baza-j-label eq${jugador % 2}`;
        jLabel.textContent = nombreJ(jugador, estado);
        item.appendChild(jLabel);
        item.appendChild(crearElementoCarta(carta, triunfo, { pequeña: true }));
      } else {
        item.appendChild(crearElementoCarta(null, null, { faceDown: true, pequeña: true }));
      }
      cartas.appendChild(item);
    });

    card.appendChild(cartas);
    lista.appendChild(card);
  });
}

// ---------------------------------------------------------------------------
// Errores
// ---------------------------------------------------------------------------

function mostrarError(msg) {
  const el = $("#acciones");
  const err = document.createElement("p");
  err.className = "error-msg";
  err.textContent = "⚠ " + msg;
  el.appendChild(err);
  setTimeout(() => err.remove(), 3000);
}

// ---------------------------------------------------------------------------
// Pantallas
// ---------------------------------------------------------------------------

function mostrarMesa() {
  $("#pantalla-inicio").classList.add("oculto");
  $("#pantalla-sala").classList.add("oculto");
  $("#mesa").classList.remove("oculto");
  // Botón de resincronizar: solo visible en modo multi
  $("#mesa").classList.toggle("modo-testeo", modoTesteo);
  $("#testeo-chip").classList.toggle("oculto", !modoTesteo);
  const btnResync = $("#btn-resync");
  if (btnResync) btnResync.classList.toggle("oculto", !modoMulti);
}

// ---------------------------------------------------------------------------
// Rotación del tablero — el jugador propio siempre abajo
// ---------------------------------------------------------------------------

// delta=0→abajo, 1→der, 2→arriba, 3→izq  (sentido contrario al reloj = orden de juego)
const POSICIONES   = ["abajo", "der", "arriba", "izq"];
const MANO_CLASES  = ["mano-horizontal", "mano-vertical", "mano-horizontal", "mano-vertical"];

function aplicarRotacion() {
  const base = modoMulti ? (miSlot ?? 0) : 0;
  for (let j = 0; j < 4; j++) {
    const delta = (j - base + 4) % 4;
    const pos   = POSICIONES[delta];
    const zona  = $(`#zona-j${j}`);
    if (!zona) continue;

    zona.classList.remove("zona-abajo", "zona-arriba", "zona-izq", "zona-der");
    zona.classList.add(`zona-${pos}`);

    const mano = $(`#mano-j${j}`);
    if (mano) {
      mano.classList.remove("mano-horizontal", "mano-vertical");
      mano.classList.add(MANO_CLASES[delta]);
    }

    const nombreEl = zona.querySelector(".nombre-jugador");
    if (nombreEl) nombreEl.classList.toggle("vertical", delta === 1 || delta === 3);
  }
}

function etiquetaRelativa(slot, base) {
  const delta = (slot - base + 4) % 4;
  if (delta === 0) return { texto: "Tú", eq: base % 2 };
  if (delta === 2) return { texto: "Compañero", eq: base % 2 };
  return { texto: "Rival", eq: slot % 2 };
}

function actualizarEtiquetas(nombres) {
  const base = modoMulti ? (miSlot ?? 0) : 0;
  for (let j = 0; j < 4; j++) {
    const zona = $(`#zona-j${j}`);
    if (!zona) continue;
    const rel   = etiquetaRelativa(j, base);
    const tag   = zona.querySelector(".tag-equipo");
    const nomEl = $(`#nombre-j${j}`);
    if (tag) {
      tag.textContent = rel.texto;
      tag.className   = `tag-equipo eq${rel.eq}`;
    }
    if (nomEl) nomEl.textContent = nombres[j] || `J${j}`;
  }
}

// ---------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Multijugador — Lobby y sala de espera
// ---------------------------------------------------------------------------

function nombreValido() {
  const n = $("#inp-nombre").value.trim();
  if (!n) { alert("Escribe tu nombre primero"); return null; }
  return n;
}

async function crearSala() {
  const nombre = nombreValido();
  if (!nombre) return;
  const objetivo = parseInt($("#sel-objetivo-multi").value);
  const con_limite = $("#sel-modo-sala").value === "1";
  try {
    const res = await apiPost(`${API}/sala/nueva`, { nombre, objetivo, con_limite });
    miSlot = res.slot;
    codigoSala = res.sala.codigo;
    miNombre = nombre;
    modoMulti = true;
    guardarSesion();
    mostrarPantallaSala(res.sala);
    conectarWS();
  } catch (e) { alert("Error al crear sala: " + e.message); }
}

async function unirseSala() {
  const nombre = nombreValido();
  if (!nombre) return;
  const codigo = $("#inp-codigo").value.trim().toUpperCase();
  if (codigo.length !== 4) { alert("El código debe tener 4 letras"); return; }
  try {
    const res = await apiPost(`${API}/sala/${codigo}/unirse`, { nombre });
    miSlot = res.slot;
    codigoSala = codigo;
    miNombre = nombre;
    modoMulti = true;
    guardarSesion();
    mostrarPantallaSala(res.sala);
    conectarWS();
  } catch (e) { alert("Error al unirse: " + e.message); }
}

async function unirseComoEspectador() {
  const nombre = $("#inp-nombre").value.trim() || "Espectador";
  const codigo = $("#inp-codigo").value.trim().toUpperCase();
  if (codigo.length !== 4) { alert("El código debe tener 4 letras"); return; }
  try {
    await apiPost(`${API}/sala/${codigo}/espectador`, { nombre });
    codigoSala = codigo;
    miNombre = nombre;
    modoMulti = true;
    modoEspectador = true;
    conectarWSEspectador();
  } catch (e) { alert("Error al unirse como espectador: " + e.message); }
}

function conectarWSEspectador() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/${codigoSala}/espectador/${encodeURIComponent(miNombre)}`;
  wsConexion = new WebSocket(url);

  wsConexion.onopen = () => {
    wsReconectarIntentos = 0;
    wsHeartbeatTimer = setInterval(() => {
      if (wsConexion?.readyState === WebSocket.OPEN) {
        wsConexion.send(JSON.stringify({ tipo: "ping" }));
      }
    }, 25000);
  };

  wsConexion.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.tipo === "estado") {
      recibirEstadoEspectador(msg.estado);
    }
  };

  wsConexion.onclose = () => {
    clearInterval(wsHeartbeatTimer);
    if (wsReconectarIntentos < 5) {
      wsReconectarIntentos++;
      const espera = Math.min(wsReconectarIntentos * 3000, 15000);
      wsReconectarTimer = setTimeout(conectarWSEspectador, espera);
    }
  };
}

async function recibirEstadoEspectador(estado) {
  estadoActual = estado;
  $("#pantalla-inicio").classList.add("oculto");
  $("#pantalla-sala").classList.add("oculto");
  mostrarMesa();
  $("#mesa").classList.add("modo-espectador");
  aplicarRotacion();
  const nombres = estado.nombres || {};
  actualizarEtiquetas(nombres);
  actualizarNombresUI(nombres);
  render(estado);
}

async function cambiarEquipo() {
  const equipoActual = miSlot % 2 === 0 ? "A" : "B";
  const equipoDestino = equipoActual === "A" ? "B" : "A";
  try {
    const res = await apiPost(`${API}/sala/${codigoSala}/elegir_slot`, {
      slot_actual: miSlot,
      equipo_destino: equipoDestino,
    });
    miSlot = res.slot;
    mostrarPantallaSala(res.sala);
  } catch (e) { alert(e.message); }
}

async function iniciarSala() {
  try {
    await apiPost(`${API}/sala/${codigoSala}/iniciar`, {});
  } catch (e) { alert(e.message); }
}

function mostrarPantallaSala(sala) {
  $("#pantalla-inicio").classList.add("oculto");
  $("#pantalla-sala").classList.remove("oculto");
  $("#mesa").classList.add("oculto");

  $("#sala-codigo-display").textContent = sala.codigo || codigoSala;

  const slots = sala.equipos
    ? { 0: sala.equipos.A[0], 1: sala.equipos.B[1], 2: sala.equipos.A[2], 3: sala.equipos.B[3] }
    : {};

  [0, 1, 2, 3].forEach(s => {
    const el = $(`#sala-slot-${s}`);
    if (!el) return;
    const nombre = slots[s];
    if (nombre) {
      el.textContent = s === miSlot ? `${nombre} (tú)` : nombre;
      el.className = `sala-slot ocupado${s === miSlot ? " yo" : ""}`;
    } else {
      el.textContent = "Libre...";
      el.className = "sala-slot";
    }
  });

  const completa = Object.values(slots).filter(Boolean).length === 4;
  const btnCambiar = $("#btn-cambiar-equipo");
  const btnIniciar = $("#btn-iniciar-sala");
  const espera = $("#sala-esperando");

  btnCambiar.classList.toggle("oculto", completa);
  btnIniciar.classList.toggle("oculto", !(completa && miSlot === 0));
  espera.classList.toggle("oculto", completa);
}

function conectarWS() {
  if (wsReconectarTimer) { clearTimeout(wsReconectarTimer); wsReconectarTimer = null; }
  clearInterval(wsHeartbeatTimer);

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws/${codigoSala}/${miSlot}`;
  wsConexion = new WebSocket(url);

  wsConexion.onopen = () => {
    wsReconectarIntentos = 0;
    // Heartbeat cada 25s para mantener la conexión viva (sobre todo en móvil)
    wsHeartbeatTimer = setInterval(() => {
      if (wsConexion?.readyState === WebSocket.OPEN) {
        wsConexion.send(JSON.stringify({ tipo: "ping" }));
      }
    }, 25000);
  };

  wsConexion.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.tipo === "sala") {
      mostrarPantallaSala(msg.sala);
    } else if (msg.tipo === "estado") {
      recibirEstadoMulti(msg.estado);
    } else if (msg.tipo === "desconexion") {
      mostrarError(`${msg.nombre} se ha desconectado`);
    } else if (msg.tipo === "error") {
      mostrarError(msg.mensaje);
    }
    // "pong" se ignora silenciosamente
  };

  wsConexion.onclose = () => {
    clearInterval(wsHeartbeatTimer);
    if (!modoMulti) return;
    if (wsReconectarIntentos < 5) {
      wsReconectarIntentos++;
      const espera = Math.min(wsReconectarIntentos * 3000, 15000);
      mostrarError(`Reconectando… (${wsReconectarIntentos}/5)`);
      wsReconectarTimer = setTimeout(conectarWS, espera);
    } else {
      mostrarError("Conexión perdida. Recarga la página para continuar.");
    }
  };
}

function wsSend(msg) {
  if (wsConexion && wsConexion.readyState === WebSocket.OPEN) {
    wsConexion.send(JSON.stringify(msg));
  }
}

async function recibirEstadoMulti(estado) {
  cancelarTimerTurno();
  const prevBazaCount = estadoActual ? estadoActual.bazas_jugadas.length : 0;
  if (estadoActual && estadoActual.mano_idx !== estado.mano_idx) canteMenuAbierto = false;
  estadoActual = estado;

  // Nueva mano: reiniciar cantes ya mostrados
  if (estado.bazas_jugadas.length === 0) cantesYaMostrados = new Set();

  $("#pantalla-sala").classList.add("oculto");
  mostrarMesa();
  aplicarRotacion();

  // Actualizar nombres en la UI
  const nombres = estado.nombres || {};
  actualizarEtiquetas(nombres);
  actualizarNombresUI(nombres);

  // Mostrar baza completada — condición: exactamente 1 baza nueva (evita replay en reconexión)
  if (estado.bazas_jugadas.length === prevBazaCount + 1) {
    await mostrarBazaCompletada(
      estado.bazas_jugadas[estado.bazas_jugadas.length - 1],
      estado.triunfo
    );
  }

  render(estado);
}

function actualizarNombresUI(nombres) {
  [0, 1, 2, 3].forEach(j => {
    const el = $(`#nombre-j${j}`);
    if (el) el.textContent = nombres[j] || `J${j}`;
  });
  // Marcador
  const eq0 = `${nombres[0] || "J0"} & ${nombres[2] || "J2"}`;
  const eq1 = `${nombres[1] || "J1"} & ${nombres[3] || "J3"}`;
  const ne0 = $("#nombre-eq0"); if (ne0) ne0.textContent = eq0;
  const ne1 = $("#nombre-eq1"); if (ne1) ne1.textContent = eq1;
}

function resync() {
  if (wsConexion?.readyState === WebSocket.OPEN) {
    wsConexion.send(JSON.stringify({ tipo: "resync" }));
  } else {
    conectarWS();
  }
}

// ---------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------

$("#btn-nueva-partida").addEventListener("click", nuevaPartida);
$("#btn-testeo").addEventListener("click", iniciarTesteo);
$("#btn-nueva-mano").addEventListener("click", nuevaMano);
$("#btn-crear-sala").addEventListener("click", crearSala);
$("#btn-unirse-sala").addEventListener("click", unirseSala);
$("#btn-cambiar-equipo").addEventListener("click", cambiarEquipo);
$("#btn-iniciar-sala").addEventListener("click", iniciarSala);
$("#btn-reconectar")?.addEventListener("click", reconectarSesion);
$("#btn-abandonar-sesion")?.addEventListener("click", () => { limpiarSesion(); ocultarPanelReconectar(); });
$("#btn-resync")?.addEventListener("click", resync);
const _btnUltima = $("#btn-ver-ultima-baza");
if (_btnUltima) {
  const _show = (e) => { e.preventDefault(); mostrarUltimaBazaPanel(); };
  const _hide = () => ocultarUltimaBazaPanel();
  _btnUltima.addEventListener("mousedown", _show);
  _btnUltima.addEventListener("touchstart", _show, { passive: false });
  _btnUltima.addEventListener("mouseup", _hide);
  _btnUltima.addEventListener("mouseleave", _hide);
  _btnUltima.addEventListener("touchend", _hide);
  _btnUltima.addEventListener("touchcancel", _hide);
}
$("#btn-ver-partida")?.addEventListener("click", unirseComoEspectador);

// Enter en el campo de código
$("#inp-codigo").addEventListener("keydown", e => { if (e.key === "Enter") unirseSala(); });
$("#inp-nombre").addEventListener("keydown", e => { if (e.key === "Enter") $("#inp-codigo").focus(); });

// Verificar sesión guardada al cargar
(function checkSesionGuardada() {
  const sesion = sesionGuardada();
  if (sesion) mostrarPanelReconectar(sesion);
})();



