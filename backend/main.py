from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
from pathlib import Path
import asyncio
import json
import copy
import hmac
import threading
import time
from collections import deque
from fastapi import Request
from functools import wraps
from fastapi import Header
import testeo

from models.deck import Carta, Palo, Valor, crear_baraja, barajar, PUNTUACION, ORDEN_TRIUNFO, ORDEN_NO_TRIUNFO, PUNTOS_TOTALES
from models.game import (
    EstadoPartida, Fase, nueva_partida, votar_subasta, jugar_carta, cartas_jugables,
    equipo_de, siguiente_turno, cantar_cante, ensenar_cantes, declarar_bolot, bolot_disponible, cantes_disponibles, puede_ensenar_cantes,
)
from models.game import _ganador_parcial, _companyero_ganando
from models.sala import Sala, salas, crear_sala, obtener_sala

app = FastAPI(title="Bolot API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Estado en memoria
# ---------------------------------------------------------------------------

partidas: Dict[str, EstadoPartida] = {}
testeo_sessions = {}  # game id -> {seq, hand_index}; process memory, like existing partidas
testeo_locks = {}
# Bounded, process-local sliding window. The private code must still be long:
# an instance restart resets this safeguard, and multiple workers do not share it.
_test_keys_lock = threading.Lock()
_test_failures_by_ip = {}
_test_failures_global = deque()
_TEST_WINDOW_SECONDS = 15 * 60
_TEST_MAX_IP_FAILURES = 5
_TEST_MAX_GLOBAL_FAILURES = 50

JUGADOR_HUMANO = 0

# ---------------------------------------------------------------------------
# IA
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers de análisis de estado
# ---------------------------------------------------------------------------

def _cartas_vistas(estado: EstadoPartida, jugador: int) -> set:
    """Cartas que el jugador sabe que ya no están en manos enemigas."""
    vistas = set(estado.manos[jugador])
    for baza in estado.bazas_jugadas:
        for _, c in baza.cartas:
            vistas.add(c)
    for _, c in estado.baza_actual.cartas:
        vistas.add(c)
    return vistas


def _es_carta_imbatible(estado: EstadoPartida, jugador: int, carta: Carta) -> bool:
    """True si ninguna carta de mayor rango del mismo palo puede seguir en juego."""
    triunfo = estado.triunfo
    vistas = _cartas_vistas(estado, jugador)
    for v in Valor:
        candidata = Carta(palo=carta.palo, valor=v)
        if candidata.rango(triunfo) > carta.rango(triunfo) and candidata not in vistas:
            return False
    return True


def _puntos_en_baza_actual(estado: EstadoPartida) -> int:
    triunfo = estado.triunfo
    return sum(c.puntos_en_juego(triunfo) for _, c in estado.baza_actual.cartas)


def _margen_puntos(estado: EstadoPartida, jugador: int) -> int:
    """Positivo = el equipo del jugador va ganando en puntos de mano."""
    eq = equipo_de(jugador)
    return estado.puntos_mano[eq] - estado.puntos_mano[1 - eq]


# ---------------------------------------------------------------------------
# Helpers de lógica de baza
# ---------------------------------------------------------------------------

def _carta_gana_a(carta: Carta, ganadora: Carta, palo_salida: Palo, triunfo) -> bool:
    """True si carta gana a ganadora en el contexto de la baza."""
    if carta.palo == palo_salida and ganadora.palo == palo_salida:
        return carta.rango(triunfo) > ganadora.rango(triunfo)
    if triunfo and carta.palo == triunfo and ganadora.palo != triunfo:
        return True
    if triunfo and carta.palo == triunfo and ganadora.palo == triunfo:
        return carta.rango(triunfo) > ganadora.rango(triunfo)
    return False


def _es_ultima_baza(estado: EstadoPartida) -> bool:
    return len(estado.bazas_jugadas) == 7


# ---------------------------------------------------------------------------
# IA de subasta
# ---------------------------------------------------------------------------

def _ia_accion_subasta(estado: EstadoPartida, jugador: int):
    mano = estado.manos[jugador]
    triunfo_prop = estado.triunfo_propuesto
    triunfos = [c for c in mano if c.palo == triunfo_prop]
    pts = sum(c.puntos_en_juego(triunfo_prop) for c in mano)  # incluye Valet(20) y Catorce(14)
    tiene_valet = any(c.palo == triunfo_prop and c.valor == Valor.SOTA for c in mano)
    tiene_catorce = any(c.palo == triunfo_prop and c.valor == Valor.NUEVE for c in mano)
    score = pts + len(triunfos) * 5 + (15 if tiene_valet else 0) + (10 if tiene_catorce else 0)
    umbral = 55 if estado.fase == Fase.SUBASTA_PRIMERAS else 65
    return "voy" if score >= umbral else "no_voy"


# ---------------------------------------------------------------------------
# IA de juego de carta — tres situaciones
# ---------------------------------------------------------------------------

def _ia_salida(estado: EstadoPartida, jugador: int, jugables: list) -> Carta:
    """Estrategia cuando el jugador sale primero en la baza."""
    triunfo = estado.triunfo
    no_triunfo = [c for c in jugables if c.palo != triunfo]

    # 1. Carta imbatible con puntos → garantiza recoger esos puntos
    imbatibles_con_pts = [
        c for c in no_triunfo
        if c.puntos_en_juego(triunfo) > 0 and _es_carta_imbatible(estado, jugador, c)
    ]
    if imbatibles_con_pts:
        return max(imbatibles_con_pts, key=lambda c: c.puntos_en_juego(triunfo))

    # 2. Carta imbatible sin puntos → tanteo, fuerza al rival a gastar buenas cartas
    imbatibles_sin_pts = [
        c for c in no_triunfo
        if c.puntos_en_juego(triunfo) == 0 and _es_carta_imbatible(estado, jugador, c)
    ]
    if imbatibles_sin_pts:
        return imbatibles_sin_pts[0]

    # 3. Modo agresivo si el equipo va perdiendo por mucho
    if triunfo and _margen_puntos(estado, jugador) < -30:
        triunfos = [c for c in jugables if c.palo == triunfo]
        if triunfos:
            return max(triunfos, key=lambda c: c.rango(triunfo))

    # 4. Carta sin puntos más débil (mínimo riesgo)
    sin_pts = [c for c in jugables if c.puntos_en_juego(triunfo) == 0]
    if sin_pts:
        return min(sin_pts, key=lambda c: c.rango(triunfo))

    # 5. Fallback: carta de menor valor
    return min(jugables, key=lambda c: c.puntos_en_juego(triunfo))


def _ia_companero_gana(estado: EstadoPartida, jugador: int, jugables: list) -> Carta:
    """Estrategia cuando el compañero va ganando la baza: intentar cargar puntos."""
    triunfo = estado.triunfo
    baza = estado.baza_actual
    es_ultimo = len(baza.cartas) == 3
    pts_en_baza = _puntos_en_baza_actual(estado)

    cartas_con_pts = sorted(
        [c for c in jugables if c.puntos_en_juego(triunfo) > 0],
        key=lambda c: c.puntos_en_juego(triunfo),
    )

    if cartas_con_pts:
        # Si es el último o la baza ya tiene mucho valor, cargar lo mejor
        if es_ultimo or pts_en_baza >= 20:
            return cartas_con_pts[-1]
        # Si no es el último: cargar algo moderado (rey/caballo ≤4 pts) pero guardar as/tres
        medios = [c for c in cartas_con_pts if c.puntos_en_juego(triunfo) <= 4]
        if medios:
            return medios[-1]
        # Solo tiene as/tres: cargar si la baza ya vale la pena
        if pts_en_baza >= 10:
            return cartas_con_pts[-1]

    # No hay puntos útiles que cargar: tirar la carta más débil
    return min(jugables, key=lambda c: c.rango(triunfo))


def _ia_rival_gana(estado: EstadoPartida, jugador: int, jugables: list) -> Carta:
    """Estrategia cuando un rival va ganando la baza."""
    triunfo = estado.triunfo
    baza = estado.baza_actual
    pts_en_baza = _puntos_en_baza_actual(estado)
    palo_salida = baza.cartas[0][1].palo

    gan_j = _ganador_parcial(baza, triunfo)
    carta_ganadora = next(c for j, c in baza.cartas if j == gan_j)

    ganadoras = [
        c for c in jugables
        if _carta_gana_a(c, carta_ganadora, palo_salida, triunfo)
    ]

    if not ganadoras:
        # No puede ganar: tirar la de menor valor para no regalar puntos
        return min(jugables, key=lambda c: c.puntos_en_juego(triunfo))

    # Umbral de puntos para decidir si vale la pena ganar la baza
    umbral = 10 if _margen_puntos(estado, jugador) > 40 else 5
    if pts_en_baza < umbral and not _es_ultima_baza(estado):
        return min(jugables, key=lambda c: c.puntos_en_juego(triunfo))

    # Ganar con el mínimo coste: la ganadora de menor rango
    return min(ganadoras, key=lambda c: c.rango(triunfo))


def _ia_elegir_carta(estado: EstadoPartida, jugador: int) -> Carta:
    jugables = cartas_jugables(estado, jugador)
    baza = estado.baza_actual
    if not baza.cartas:
        return _ia_salida(estado, jugador, jugables)
    if _companyero_ganando(baza, jugador, estado.triunfo):
        return _ia_companero_gana(estado, jugador, jugables)
    return _ia_rival_gana(estado, jugador, jugables)


def _one_step_ia(estado: EstadoPartida, human_seats=(0,)) -> EstadoPartida:
    """Juega UN solo turno de IA."""
    if estado.fase == Fase.FIN_MANO or estado.turno in human_seats:
        return estado
    if estado.error:
        estado.error = None

    j = estado.turno
    if estado.fase in (Fase.SUBASTA_PRIMERAS, Fase.SUBASTA_SEGUNDAS):
        accion = _ia_accion_subasta(estado, j)
        if accion == "voy":
            if estado.fase == Fase.SUBASTA_SEGUNDAS:
                mano_ia = estado.manos[j]
                palos_validos = [p for p in Palo if p != estado.triunfo_propuesto]
                palo = max(palos_validos, key=lambda p: sum(1 for c in mano_ia if c.palo == p))
                estado = votar_subasta(estado, j, "voy", palo)
            else:
                estado = votar_subasta(estado, j, "voy")
        else:
            estado = votar_subasta(estado, j, "no_voy")
    elif estado.fase == Fase.BAZAS:
        if len(estado.bazas_jugadas) == 0:
            for cante in list(cantes_disponibles(estado, j)):
                from models.game import _clave_cante
                cantar_cante(estado, j, _clave_cante(cante))
        if puede_ensenar_cantes(estado, j):
            # Separate the reveal from the card play: the client must show the
            # actual cards to everyone before requesting the next AI action.
            ensenar_cantes(estado, j)
            return estado
        if bolot_disponible(estado, j):
            declarar_bolot(estado, j)
        carta = _ia_elegir_carta(estado, j)
        estado = jugar_carta(estado, j, carta)
        if estado.bolot_pendiente and estado.bolot_pendiente[0] == j:
            declarar_bolot(estado, j)

    return estado


def _auto_play_ia(estado: EstadoPartida) -> EstadoPartida:
    """Juega todos los turnos de IA hasta que sea el turno del jugador humano o fin de mano."""
    for _ in range(60):
        if estado.fase == Fase.FIN_MANO or estado.turno == JUGADOR_HUMANO:
            break
        estado = _one_step_ia(estado)
        if estado.error:
            break
    return estado


# ---------------------------------------------------------------------------
# Helper: añade cartas jugables del humano a la respuesta
# ---------------------------------------------------------------------------

def _respuesta(estado: EstadoPartida) -> dict:
    d = estado.to_dict()
    if estado.fase == Fase.BAZAS and estado.turno == JUGADOR_HUMANO:
        jugables = cartas_jugables(estado, JUGADOR_HUMANO)
        d["jugables_humano"] = [c.to_dict() for c in jugables]
    else:
        d["jugables_humano"] = []
    return d


# ---------------------------------------------------------------------------
# Modelos de petición
# ---------------------------------------------------------------------------

class NuevaPartidaRequest(BaseModel):
    objetivo: int = 1000


class SubastaRequest(BaseModel):
    accion: str          # "voy" | "no_voy"
    palo: Optional[str] = None


class JugarCartaRequest(BaseModel):
    palo: str
    valor: str


class DeclaracionCanteRequest(BaseModel):
    tipo: str


# ---------------------------------------------------------------------------
# Endpoints de partida
# ---------------------------------------------------------------------------

@app.post("/api/partida/nueva", summary="Crea una nueva partida")
def post_nueva_partida(body: NuevaPartidaRequest = NuevaPartidaRequest()):
    estado = nueva_partida(objetivo=body.objetivo)
    partidas[estado.id] = estado
    return _respuesta(estado)


@app.get("/api/partida/{partida_id}", summary="Devuelve el estado de una partida")
def get_partida(partida_id: str):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/subasta", summary="El jugador humano vota en la subasta")
def post_subasta(partida_id: str, body: SubastaRequest):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")

    try:
        palo = Palo(body.palo) if body.palo else None
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Palo inválido: {body.palo}")
    estado = votar_subasta(estado, JUGADOR_HUMANO, body.accion, palo)

    if estado.error:
        raise HTTPException(status_code=400, detail=estado.error)

    partidas[partida_id] = estado
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/jugar", summary="El jugador humano juega una carta")
def post_jugar(partida_id: str, body: JugarCartaRequest):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")

    try:
        palo = Palo(body.palo)
        valor = Valor(body.valor)
    except ValueError:
        raise HTTPException(status_code=400, detail="Carta inválida")

    carta = Carta(palo=palo, valor=valor)
    estado = jugar_carta(estado, JUGADOR_HUMANO, carta)

    if estado.error:
        raise HTTPException(status_code=400, detail=estado.error)

    # No auto-play: el frontend anima los turnos de IA paso a paso
    partidas[partida_id] = estado
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/siguiente", summary="La IA juega un paso (para animación)")
def post_siguiente(partida_id: str):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")

    estado = _one_step_ia(estado)
    if estado.error:
        raise HTTPException(status_code=400, detail=estado.error)

    partidas[partida_id] = estado
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/declarar-cante")
def post_declarar_cante(partida_id: str, body: DeclaracionCanteRequest):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")
    cantar_cante(estado, JUGADOR_HUMANO, body.tipo)
    if estado.error:
        raise HTTPException(status_code=400, detail=estado.error)
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/ensenar-cantes")
def post_ensenar_cantes(partida_id: str):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")
    ensenar_cantes(estado, JUGADOR_HUMANO)
    if estado.error:
        raise HTTPException(status_code=400, detail=estado.error)
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/bolot")
def post_bolot(partida_id: str):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")
    declarar_bolot(estado, JUGADOR_HUMANO)
    if estado.error:
        raise HTTPException(status_code=400, detail=estado.error)
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/omitir-cantes")
def post_omitir_cantes(partida_id: str):
    estado = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")
    # Compatibilidad de endpoint antiguo: no concede puntos ni enseña.
    estado.cantes_anunciados.pop(JUGADOR_HUMANO, None)
    return _respuesta(estado)


@app.post("/api/partida/{partida_id}/nueva-mano", summary="Inicia una nueva mano conservando los puntos")
def post_nueva_mano(partida_id: str):
    estado_ant = partidas.get(partida_id) if partida_id not in testeo_sessions else None
    if estado_ant is None:
        raise HTTPException(status_code=404, detail="Partida no encontrada")
    if estado_ant.fase != Fase.FIN_MANO:
        raise HTTPException(status_code=400, detail="La mano no ha terminado aún")

    nuevo_dealer = (estado_ant.dealer + 1) % 4
    nuevo = nueva_partida(objetivo=estado_ant.objetivo, dealer=nuevo_dealer)
    nuevo.puntos_totales = list(estado_ant.puntos_totales)
    nuevo.id = estado_ant.id
    partidas[partida_id] = nuevo
    return _respuesta(nuevo)


# ---------------------------------------------------------------------------
# Modo testeo. This family is isolated; standard single-player remains J0-only.
# All state-changing requests require a server-side access code and a verified
# Supabase save before replacing the in-memory game state.
# ---------------------------------------------------------------------------

def _serialized_testeo(fn):
    @wraps(fn)
    def wrapped(partida_id, *args, **kwargs):
        # Authenticate before touching a session lock: an unknown ID must not
        # allow unauthenticated requests to evade the attempt limiter.
        _testeo_guard(kwargs.get('x_testeo_code'), kwargs.get('request'))
        lock = testeo_locks.get(partida_id)
        if lock is None:
            raise HTTPException(status_code=404, detail="Partida de testeo no encontrada")
        with lock:
            return fn(partida_id, *args, **kwargs)
    return wrapped

def _testeo_guard(code, request=None):
    if not testeo.enabled():
        raise HTTPException(status_code=503, detail="Testeo sin configurar en servidor")
    # Use the socket peer rather than an untrusted forwarded-IP header. On a
    # shared proxy this is deliberately stricter; the global cap remains useful.
    peer = request.client.host if request and request.client else "unknown"
    now = time.monotonic()
    with _test_keys_lock:
        cutoff = now - _TEST_WINDOW_SECONDS
        while _test_failures_global and _test_failures_global[0] <= cutoff:
            _test_failures_global.popleft()
        attempts = _test_failures_by_ip.get(peer)
        if attempts is None:
            attempts = deque()
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if len(attempts) >= _TEST_MAX_IP_FAILURES or len(_test_failures_global) >= _TEST_MAX_GLOBAL_FAILURES:
            raise HTTPException(status_code=429, detail="Demasiados intentos; vuelve a probar en 15 minutos")
        if not code or not hmac.compare_digest(code.encode('utf-8'), __import__('os').environ['BOLOT_TESTEO_CODE'].encode('utf-8')):
            attempts.append(now)
            _test_failures_by_ip[peer] = attempts
            _test_failures_global.append(now)
            raise HTTPException(status_code=403, detail="Acceso a testeo no autorizado")
        # Correct access clears only this peer's failures. Neither headers nor
        # a forged session ID can reset another peer's attempts.
        _test_failures_by_ip.pop(peer, None)

def _testeo_game(partida_id, code, request=None):
    _testeo_guard(code, request)
    if partida_id not in testeo_sessions or partida_id not in partidas:
        raise HTTPException(status_code=404, detail="Partida de testeo no encontrada")
    return partidas[partida_id]

def _testeo_commit(partida_id, before, after, actor, action):
    if after.error:
        raise HTTPException(status_code=400, detail=after.error)
    meta = testeo_sessions[partida_id]
    evt = testeo.event(before, after, actor, action, meta['seq'], meta['hand_index'])
    try:
        testeo.save(evt)
    except Exception:
        raise HTTPException(status_code=503, detail="No se pudo guardar la decisión; inténtalo de nuevo")
    meta['seq'] += 1
    partidas[partida_id] = after
    return testeo.serialize(after)

@app.post('/api/testeo/nueva')
def testeo_nueva(body: NuevaPartidaRequest, request: Request, x_testeo_code: Optional[str] = Header(None)):
    _testeo_guard(x_testeo_code, request)
    estado = nueva_partida(objetivo=body.objetivo)
    # Persist the initial deal before exposing it. No silent fallback to local storage.
    try:
        testeo.save({'game_id': estado.id, 'seq': 0, 'hand_index': 0,
                     'actor': 0, 'actor_kind': 'human', 'phase': 'start',
                     'observation': {}, 'action': {'type': 'new_game', 'objective': body.objetivo},
                     'result': {'phase': estado.fase.value, 'dealer': estado.dealer}})
    except Exception:
        raise HTTPException(status_code=503, detail="No se pudo iniciar el registro en Supabase")
    testeo_sessions[estado.id] = {'seq': 1, 'hand_index': 0}
    testeo_locks[estado.id] = threading.RLock()
    partidas[estado.id] = estado
    return testeo.serialize(estado)

@app.get('/api/testeo/{partida_id}')
def testeo_get(partida_id: str, request: Request, x_testeo_code: Optional[str] = Header(None)):
    return testeo.serialize(_testeo_game(partida_id, x_testeo_code, request))

@app.post('/api/testeo/{partida_id}/subasta')
@_serialized_testeo
def testeo_subasta(partida_id: str, body: SubastaRequest, request: Request, x_testeo_code: Optional[str] = Header(None)):
    before = _testeo_game(partida_id, x_testeo_code, request)
    actor = before.turno
    if actor not in testeo.HUMANS:
        raise HTTPException(status_code=409, detail="Ahora juega la IA")
    if body.accion not in ('voy', 'no_voy'):
        raise HTTPException(status_code=400, detail='Acción de subasta inválida')
    try: palo = Palo(body.palo) if body.palo else None
    except ValueError: raise HTTPException(status_code=400, detail="Palo inválido")
    after = votar_subasta(copy.deepcopy(before), actor, body.accion, palo)
    return _testeo_commit(partida_id, before, after, actor, {'type':'bid', 'decision':body.accion, 'suit':body.palo})

@app.post('/api/testeo/{partida_id}/jugar')
@_serialized_testeo
def testeo_jugar(partida_id: str, body: JugarCartaRequest, request: Request, x_testeo_code: Optional[str] = Header(None)):
    before = _testeo_game(partida_id, x_testeo_code, request)
    actor = before.turno
    if actor not in testeo.HUMANS: raise HTTPException(status_code=409, detail="Ahora juega la IA")
    try: carta = Carta(palo=Palo(body.palo), valor=Valor(body.valor))
    except ValueError: raise HTTPException(status_code=400, detail="Carta inválida")
    after = jugar_carta(copy.deepcopy(before), actor, carta)
    return _testeo_commit(partida_id, before, after, actor, {'type':'play_card', 'card':carta.to_dict()})

@app.post('/api/testeo/{partida_id}/siguiente')
@_serialized_testeo
def testeo_siguiente(partida_id: str, request: Request, x_testeo_code: Optional[str] = Header(None)):
    before = _testeo_game(partida_id, x_testeo_code, request)
    actor = before.turno
    if actor in testeo.HUMANS or before.fase == Fase.FIN_MANO:
        raise HTTPException(status_code=409, detail="No es turno de la IA")
    after = _one_step_ia(copy.deepcopy(before), testeo.HUMANS)
    return _testeo_commit(partida_id, before, after, actor, {'type':'ai_step'})

@app.post('/api/testeo/{partida_id}/declarar-cante')
@_serialized_testeo
def testeo_cante(partida_id: str, body: DeclaracionCanteRequest, request: Request, x_testeo_code: Optional[str] = Header(None)):
    before = _testeo_game(partida_id, x_testeo_code, request); actor = before.turno
    if actor not in testeo.HUMANS: raise HTTPException(status_code=409, detail="Ahora juega la IA")
    after = copy.deepcopy(before); cantar_cante(after, actor, body.tipo)
    return _testeo_commit(partida_id, before, after, actor, {'type':'declare', 'declaration':body.tipo})

@app.post('/api/testeo/{partida_id}/ensenar-cantes')
@_serialized_testeo
def testeo_ensenar(partida_id: str, request: Request, x_testeo_code: Optional[str] = Header(None)):
    before = _testeo_game(partida_id, x_testeo_code, request); actor = before.turno
    if actor not in testeo.HUMANS: raise HTTPException(status_code=409, detail="Ahora juega la IA")
    after = copy.deepcopy(before); ensenar_cantes(after, actor)
    return _testeo_commit(partida_id, before, after, actor, {'type':'reveal_declarations'})

@app.post('/api/testeo/{partida_id}/bolot')
@_serialized_testeo
def testeo_bolot(partida_id: str, request: Request, x_testeo_code: Optional[str] = Header(None)):
    before = _testeo_game(partida_id, x_testeo_code, request)
    actor = before.bolot_pendiente[0] if before.bolot_pendiente else before.turno
    if actor not in testeo.HUMANS: raise HTTPException(status_code=409, detail="No hay bolot humano")
    after = copy.deepcopy(before); declarar_bolot(after, actor)
    return _testeo_commit(partida_id, before, after, actor, {'type':'bolot'})

@app.post('/api/testeo/{partida_id}/nueva-mano')
@_serialized_testeo
def testeo_nueva_mano(partida_id: str, request: Request, x_testeo_code: Optional[str] = Header(None)):
    before = _testeo_game(partida_id, x_testeo_code, request)
    if before.fase != Fase.FIN_MANO: raise HTTPException(status_code=400, detail="La mano no ha terminado")
    after = nueva_partida(objetivo=before.objetivo, dealer=(before.dealer + 1) % 4)
    after.puntos_totales = list(before.puntos_totales); after.id = before.id
    testeo_sessions[partida_id]['hand_index'] += 1
    try:
        return _testeo_commit(partida_id, before, after, 0, {'type':'new_hand'})
    except Exception:
        testeo_sessions[partida_id]['hand_index'] -= 1
        raise

# ---------------------------------------------------------------------------
# Endpoints de baraja (legacy)
# ---------------------------------------------------------------------------

@app.get("/api/baraja", summary="Devuelve las 32 cartas sin barajar")
def get_baraja():
    baraja = crear_baraja()
    return {
        "total": len(baraja),
        "puntos_totales": PUNTOS_TOTALES,
        "cartas": [c.to_dict() for c in baraja],
    }


@app.get("/api/baraja/info", summary="Metadatos de la baraja")
def get_info_baraja():
    return {
        "palos": [p.value for p in Palo],
        "puntuacion": {v.value: pts for v, pts in PUNTUACION.items()},
        "orden_triunfo": [v.value for v in reversed(ORDEN_TRIUNFO)],
        "orden_no_triunfo": [v.value for v in reversed(ORDEN_NO_TRIUNFO)],
        "puntos_totales": PUNTOS_TOTALES,
    }


# ---------------------------------------------------------------------------
# Endpoints de sala (multijugador)
# ---------------------------------------------------------------------------

class CrearSalaRequest(BaseModel):
    nombre: str
    objetivo: int = 1000
    con_limite: bool = False

class UnirseSalaRequest(BaseModel):
    nombre: str
    equipo: str = "A"   # "A" o "B"
    slot_esperado: Optional[int] = None  # para reconexión

class ElegirSlotRequest(BaseModel):
    slot_actual: int
    equipo_destino: str  # "A" o "B"


@app.post("/api/sala/nueva")
async def post_crear_sala(body: CrearSalaRequest):
    sala = crear_sala(body.nombre.strip()[:20], body.objetivo, body.con_limite)
    return {"codigo": sala.codigo, "slot": 0, "sala": sala.to_dict(mi_slot=0)}


@app.get("/api/sala/{codigo}")
async def get_sala(codigo: str):
    sala = obtener_sala(codigo)
    if sala is None:
        raise HTTPException(status_code=404, detail="Sala no encontrada")
    return sala.to_dict()


@app.post("/api/sala/{codigo}/unirse")
async def post_unirse(codigo: str, body: UnirseSalaRequest):
    sala = obtener_sala(codigo)
    if sala is None:
        raise HTTPException(status_code=404, detail="Sala no encontrada")

    nombre = body.nombre.strip()[:20]

    # ── Reconexión: el jugador ya tiene un slot en esta sala ─────────────────
    slot_rc = None
    if body.slot_esperado is not None and sala.jugadores.get(body.slot_esperado) == nombre:
        slot_rc = body.slot_esperado
    if slot_rc is None:
        for s, n in sala.jugadores.items():
            if n == nombre:
                slot_rc = s
                break
    if slot_rc is not None:
        return {"slot": slot_rc, "sala": sala.to_dict(mi_slot=slot_rc)}

    # ── Nuevo jugador ────────────────────────────────────────────────────────
    if sala.iniciada:
        raise HTTPException(status_code=400, detail="La partida ya ha comenzado")
    if sala.completa():
        raise HTTPException(status_code=400, detail="La sala está llena")

    equipo = body.equipo.upper()
    if equipo not in ("A", "B"):
        equipo = "A"
    slot = sala.slot_libre(equipo)
    if slot is None:
        otro = "B" if equipo == "A" else "A"
        slot = sala.slot_libre(otro)
    if slot is None:
        raise HTTPException(status_code=400, detail="La sala está llena")

    sala.jugadores[slot] = nombre
    sala.conexiones[slot] = None

    await sala.broadcast({"tipo": "sala", "sala": sala.to_dict()})
    return {"slot": slot, "sala": sala.to_dict(mi_slot=slot)}


@app.post("/api/sala/{codigo}/elegir_slot")
async def post_elegir_slot(codigo: str, body: ElegirSlotRequest):
    sala = obtener_sala(codigo)
    if sala is None:
        raise HTTPException(status_code=404, detail="Sala no encontrada")
    if sala.iniciada:
        raise HTTPException(status_code=400, detail="La partida ya ha comenzado")

    slot_actual = body.slot_actual
    if slot_actual not in sala.jugadores:
        raise HTTPException(status_code=400, detail="Slot inválido")

    equipo = body.equipo_destino.upper()
    nuevo_slot = sala.slot_libre(equipo)
    if nuevo_slot is None:
        raise HTTPException(status_code=400, detail="El equipo está lleno")

    nombre = sala.jugadores.pop(slot_actual)
    ws = sala.conexiones.pop(slot_actual, None)
    sala.jugadores[nuevo_slot] = nombre
    sala.conexiones[nuevo_slot] = ws

    await sala.broadcast({"tipo": "sala", "sala": sala.to_dict()})
    return {"slot": nuevo_slot, "sala": sala.to_dict(mi_slot=nuevo_slot)}


@app.post("/api/sala/{codigo}/iniciar")
async def post_iniciar(codigo: str, body: dict = {}):
    sala = obtener_sala(codigo)
    if sala is None:
        raise HTTPException(status_code=404, detail="Sala no encontrada")
    if not sala.completa():
        raise HTTPException(status_code=400, detail="Faltan jugadores")
    if sala.iniciada:
        raise HTTPException(status_code=400, detail="Ya iniciada")

    sala.iniciada = True
    sala.estado = nueva_partida(objetivo=sala.objetivo)
    await sala.broadcast_estado()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Endpoints de espectador
# ---------------------------------------------------------------------------

@app.post("/api/sala/{codigo}/espectador")
async def post_unirse_espectador(codigo: str, body: dict):
    sala = obtener_sala(codigo)
    if sala is None:
        raise HTTPException(status_code=404, detail="Sala no encontrada")
    nombre = str(body.get("nombre", "Espectador")).strip()[:20] or "Espectador"
    # Permitir aunque la sala esté llena/iniciada
    if nombre not in sala.espectadores:
        sala.espectadores[nombre] = None
    return {"ok": True, "nombre": nombre}


# ---------------------------------------------------------------------------
# WebSocket — acciones de juego en tiempo real
# ---------------------------------------------------------------------------

@app.websocket("/ws/{codigo}/{slot}")
async def websocket_sala(websocket: WebSocket, codigo: str, slot: int):
    sala = obtener_sala(codigo)
    if sala is None or slot not in sala.jugadores:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    sala.conexiones[slot] = websocket

    # Enviar estado actual si la partida ya empezó
    if sala.iniciada and sala.estado:
        nombres = {s: sala.jugadores.get(s, f"J{s}") for s in range(4)}
        await websocket.send_text(json.dumps({
            "tipo": "estado",
            "estado": sala.estado.to_dict_para(slot, nombres)
        }))
    else:
        await websocket.send_text(json.dumps({"tipo": "sala", "sala": sala.to_dict(mi_slot=slot)}))

    try:
        while True:
            texto = await websocket.receive_text()
            msg = json.loads(texto)
            await _procesar_accion_ws(sala, slot, msg)
    except WebSocketDisconnect:
        sala.conexiones[slot] = None
        await sala.broadcast({"tipo": "desconexion", "slot": slot, "nombre": sala.jugadores.get(slot, f"J{slot}")})


@app.websocket("/ws/{codigo}/espectador/{nombre}")
async def websocket_espectador(websocket: WebSocket, codigo: str, nombre: str):
    sala = obtener_sala(codigo)
    if sala is None:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    sala.espectadores[nombre] = websocket

    # Enviar estado actual si la partida ya empezó
    if sala.iniciada and sala.estado:
        nombres = {s: sala.jugadores.get(s, f"J{s}") for s in range(4)}
        datos = sala.estado.to_dict_para(4, nombres)  # slot 4 → todas las manos ocultas
        datos["con_limite"] = sala.con_limite
        datos["espectador"] = True
        await websocket.send_text(json.dumps({"tipo": "estado", "estado": datos}, ensure_ascii=False))

    try:
        while True:
            await websocket.receive_text()  # solo acepta pings, ignora el resto
    except WebSocketDisconnect:
        sala.espectadores.pop(nombre, None)


async def _procesar_accion_ws(sala: Sala, slot: int, msg: dict):
    """Procesa una acción de juego recibida por WebSocket."""
    if sala.estado is None:
        return

    estado = sala.estado
    tipo = msg.get("tipo")

    if estado.turno != slot and tipo not in ("nueva_mano", "bolot"):
        # No es tu turno
        nombres = {s: sala.jugadores.get(s, f"J{s}") for s in range(4)}
        ws = sala.conexiones.get(slot)
        if ws:
            await ws.send_text(json.dumps({
                "tipo": "error", "mensaje": "No es tu turno"
            }))
        return

    if tipo == "subasta":
        palo_str = msg.get("palo")
        palo = Palo(palo_str) if palo_str else None
        estado = votar_subasta(estado, slot, msg["accion"], palo)

    elif tipo == "jugar":
        carta = Carta(palo=Palo(msg["palo"]), valor=Valor(msg["valor"]))
        estado = jugar_carta(estado, slot, carta)

    elif tipo == "declarar_cante":
        cantar_cante(estado, slot, msg.get("tipo_cante", ""))

    elif tipo == "ensenar_cantes":
        ensenar_cantes(estado, slot)

    elif tipo == "bolot":
        declarar_bolot(estado, slot)

    elif tipo == "omitir_cantes":
        if estado.fase == Fase.BAZAS and len(estado.bazas_jugadas) == 1:
            estado.cantes_anunciados.pop(slot, None)
        else:
            estado.error = "No es momento de omitir cantes"

    elif tipo == "auto_jugar":
        # El cliente agotó el temporizador — jugar carta legal aleatoria (via IA)
        if estado.fase == Fase.BAZAS and sala.con_limite:
            carta = _ia_elegir_carta(estado, slot)
            estado = jugar_carta(estado, slot, carta)
            # Temporizador de turno agotado: ningún cante se declara por el jugador.

    elif tipo == "nueva_mano":
        if estado.fase == Fase.FIN_MANO and slot == sala.anfitrion_slot:
            nuevo_dealer = (estado.dealer + 1) % 4
            nuevo = nueva_partida(objetivo=estado.objetivo, dealer=nuevo_dealer)
            nuevo.puntos_totales = list(estado.puntos_totales)
            nuevo.id = estado.id
            estado = nuevo

    elif tipo == "ping":
        # Mantener conexión viva — no hacer broadcast
        return

    elif tipo == "resync":
        # Reenviar estado actual solo a quien lo pide
        nombres = {s: sala.jugadores.get(s, f"J{s}") for s in range(4)}
        ws = sala.conexiones.get(slot)
        if ws:
            try:
                await ws.send_text(json.dumps({
                    "tipo": "estado",
                    "estado": sala.estado.to_dict_para(slot, nombres)
                }, ensure_ascii=False))
            except Exception:
                sala.conexiones[slot] = None
        return

    if estado.error:
        ws = sala.conexiones.get(slot)
        if ws:
            await ws.send_text(json.dumps({"tipo": "error", "mensaje": estado.error}, ensure_ascii=False))
        estado.error = None
        return
    sala.estado = estado
    await sala.broadcast_estado()


# ---------------------------------------------------------------------------
# Servir frontend (build de Vite) en producción
# ---------------------------------------------------------------------------

_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _DIST.exists():
    # Sirve todo el build de Vite (cartas, assets, index.html, SPA fallback)
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)



