"""
Lógica completa de una mano de Bolot.

Jugadores y equipos:
  Jugadores 0 y 2 → Equipo 0 (pareja A)
  Jugadores 1 y 3 → Equipo 1 (pareja B)

Turno de juego (contrario a las agujas del reloj):
  0 → 1 → 2 → 3 → 0 …
  El jugador 0 es "mano" (primero en hablar en la subasta).
  El jugador 3 es el repartidor.

Flujo de una mano:
  1. nueva_partida()          → SUBASTA_PRIMERAS
  2. votar_subasta() × ≤4    → SUBASTA_SEGUNDAS  (si todos pasan)
                              → BAZAS             (si alguien va)
  3. [si SEGUNDAS] votar_subasta() × ≤4
  4. jugar_carta() × 32      → baza a baza (8 bazas × 4 jugadores)
  5. _fin_mano()              → FIN_MANO, actualiza puntos totales
"""

from __future__ import annotations

import random
import uuid
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .deck import (
    Carta, Palo, Valor,
    ORDEN_TRIUNFO, ORDEN_NO_TRIUNFO,
    PUNTOS_TOTALES, PUNTOS_ULTIMAS,
    barajar, crear_baraja,
)


# ---------------------------------------------------------------------------
# Enumeraciones
# ---------------------------------------------------------------------------

class Fase(str, Enum):
    SUBASTA_PRIMERAS = "subasta_primeras"
    SUBASTA_SEGUNDAS = "subasta_segundas"
    BAZAS = "bazas"
    FIN_MANO = "fin_mano"


# ---------------------------------------------------------------------------
# Secuencia para detectar cantes de escalera
# Siete < Ocho < Nueve < Tres < Sota < Caballo < Rey < As
# ---------------------------------------------------------------------------

SECUENCIA_CANTES: List[Valor] = [
    Valor.SIETE, Valor.OCHO, Valor.NUEVE, Valor.TRES,
    Valor.SOTA, Valor.CABALLO, Valor.REY, Valor.AS,
]


# ---------------------------------------------------------------------------
# Dataclasses de estado
# ---------------------------------------------------------------------------

@dataclass
class Cante:
    tipo: str       # "tercera" | "cincuenta" | "cien_seq" | "cien_cuatro" |
                    # "ciento_cincuenta" | "doscientos" | "bolot"
    puntos: int
    cartas: List[Carta]
    jugador: int    # índice del jugador que lo tiene

    def to_dict(self) -> dict:
        return {
            "tipo": self.tipo,
            "puntos": self.puntos,
            "cartas": [c.to_dict() for c in self.cartas],
            "jugador": self.jugador,
        }


@dataclass
class Baza:
    cartas: List[Tuple[int, Carta]] = field(default_factory=list)
    ganador: Optional[int] = None
    puntos: int = 0

    def to_dict(self) -> dict:
        return {
            "cartas": [{"jugador": j, "carta": c.to_dict()} for j, c in self.cartas],
            "ganador": self.ganador,
            "puntos": self.puntos,
        }


@dataclass
class EstadoPartida:
    id: str
    manos: List[List[Carta]]            # manos[jugador] = lista de cartas en mano
    mazo: List[Carta]                   # cartas pendientes de repartir
    fase: Fase
    turno: int                          # jugador que debe actuar ahora
    mano_idx: int                       # quién es "mano" esta mano
    triunfo: Optional[Palo]             # palo de triunfo confirmado (None hasta que alguien va)
    triunfo_propuesto: Optional[Palo]   # palo de la carta boca arriba (de primeras)
    carta_mesa: Optional[Carta]         # carta boca arriba en la subasta
    quien_va: Optional[int]             # jugador que dijo "voy"
    votos_subasta: List[Optional[str]]  # votos de cada jugador
    baza_actual: Baza
    bazas_jugadas: List[Baza]
    puntos_mano: List[int]              # puntos de cartas en esta mano [eq0, eq1]
    puntos_totales: List[int]           # puntos acumulados del juego [eq0, eq1]
    cantes: List[Cante]                 # cantes declarados en esta mano
    cantes_equipo: List[int]            # puntos de cantes por equipo [eq0, eq1]
    bolot_declarado: List[bool]         # bolot_declarado[j] = True si j ya dijo bolot
    ultimas_ganadas_por: Optional[int]  # equipo que ganó la última baza
    capota_equipo: Optional[int]        # equipo que hizo capotá esta mano (None si no hubo)
    objetivo: int                       # puntos objetivo del juego (1000 o 1500)
    dealer: int                         # jugador que reparte esta mano
    cantes_pendientes_humano: List[Cante]  # campo antiguo conservado para clientes anteriores
    rebolot_declarado: List[bool]       # True si j declaró la segunda carta de triunfo a tiempo
    error: Optional[str]                # mensaje de error de la última acción
    anuncios_primera: Dict[int, Optional[str]] = field(default_factory=dict)
    cantes_anunciados: Dict[int, List[Cante]] = field(default_factory=dict)
    cantes_ensenados: Dict[int, List[Cante]] = field(default_factory=dict)
    equipo_ganador_cantes: Optional[int] = None  # fijado al cerrar la primera baza
    bolot_pendiente: Optional[Tuple[int, str, float]] = None  # jugador, tipo, plazo monotónico
    bolot_primera_jugada: List[bool] = field(default_factory=lambda: [False] * 4)

    def to_dict(self) -> dict:
        return self.to_dict_para(jugador_pov=None)

    def to_dict_para(self, jugador_pov: Optional[int], nombres: Optional[Dict[int, str]] = None) -> dict:
        """
        Serializa el estado desde el punto de vista de jugador_pov.
        - jugador_pov=None → modo 1 jugador (muestra todas las cartas)
        - jugador_pov=0..3 → oculta las cartas de los demás jugadores
        nombres: dict slot→nombre para sustituir J0/J1/J2/J3
        """
        manos_serializadas = []
        for j, mano in enumerate(self.manos):
            if jugador_pov is None or j == jugador_pov:
                manos_serializadas.append([c.to_dict() for c in mano])
            else:
                # Ocultar cartas ajenas: solo enviar el número de cartas
                manos_serializadas.append(len(mano))

        # Cantes pendientes: en single player todo, en multi solo los propios
        if jugador_pov is None:
            cantes_pendientes = [c.to_dict() for c in self.cantes_pendientes_humano]
        else:
            cantes_pendientes = [c.to_dict() for c in self.cantes_pendientes_humano
                                 if c.jugador == jugador_pov]

        # Cartas jugables para este jugador si es su turno
        jugables = []
        pov = jugador_pov if jugador_pov is not None else 0
        if self.turno == pov and self.fase == Fase.BAZAS:
            jugables = [c.to_dict() for c in cartas_jugables(self, pov)]

        propios = self.cantes_anunciados.get(pov, [])
        opciones = cantes_disponibles(self, pov) if self.fase == Fase.BAZAS and self.turno == pov and len(self.bazas_jugadas) == 0 else []
        pendiente_bolot = self.bolot_pendiente
        return {
            "cantes_disponibles": [{**c.to_dict(), "clave": _clave_cante(c)} for c in opciones],
            "cantes_anunciados_propios": [c.to_dict() for c in propios],
            "puede_ensenar_cantes": puede_ensenar_cantes(self, pov),
            "cantes_ensenados_propios": [c.to_dict() for c in self.cantes_ensenados.get(pov, [])],
            # Solo los cantes ya enseñados son públicos. Nunca exponer manos ni
            # anuncios aún pendientes de otros jugadores en multijugador.
            "cantes_ensenados": {str(j): [c.to_dict() for c in cantes]
                                  for j, cantes in self.cantes_ensenados.items()},
            "bolot_pendiente": ({"tipo": pendiente_bolot[1], "vence_en": max(0, pendiente_bolot[2] - time.monotonic())}
                                 if pendiente_bolot and pendiente_bolot[0] == pov and pendiente_bolot[2] > time.monotonic() else None),
            "bolot_disponible": bolot_disponible(self, pov),
            "id": self.id,
            "fase": self.fase.value,
            "turno": self.turno,
            "mano_idx": self.mano_idx,
            "triunfo": self.triunfo.value if self.triunfo else None,
            "triunfo_propuesto": self.triunfo_propuesto.value if self.triunfo_propuesto else None,
            "carta_mesa": self.carta_mesa.to_dict() if self.carta_mesa else None,
            "quien_va": self.quien_va,
            "votos_subasta": self.votos_subasta,
            "manos": manos_serializadas,
            "baza_actual": self.baza_actual.to_dict(),
            "bazas_jugadas": [b.to_dict() for b in self.bazas_jugadas],
            "puntos_mano": self.puntos_mano,
            "puntos_totales": self.puntos_totales,
            "cantes": [c.to_dict() for c in self.cantes],
            "cantes_equipo": self.cantes_equipo,
            "objetivo": self.objetivo,
            "dealer": self.dealer,
            "cantes_pendientes_humano": cantes_pendientes,
            "jugables_humano": jugables,
            "capota_equipo": self.capota_equipo,
            "error": self.error,
            "jugador_pov": jugador_pov,
            "nombres": nombres or {i: f"J{i}" for i in range(4)},
            "anuncios_primera": {str(k): v for k, v in self.anuncios_primera.items()},
        }


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def equipo_de(jugador: int) -> int:
    """Jugadores 0 y 2 son equipo 0; jugadores 1 y 3 son equipo 1."""
    return jugador % 2


def siguiente_turno(jugador: int) -> int:
    """Orden de juego: 0 → 1 → 2 → 3 → 0"""
    return (jugador + 1) % 4


# ---------------------------------------------------------------------------
# Detección de cantes
# ---------------------------------------------------------------------------

def _detectar_secuencias(mano: List[Carta], jugador: int) -> List[Cante]:
    """Detecta terceras (20 pts), cincuentas (50 pts) y cienes de escalera (100 pts)."""
    cantes: List[Cante] = []
    by_palo: Dict[Palo, List[int]] = {p: [] for p in Palo}

    for carta in mano:
        if carta.valor in SECUENCIA_CANTES:
            by_palo[carta.palo].append(SECUENCIA_CANTES.index(carta.valor))

    for palo, indices in by_palo.items():
        if len(indices) < 3:
            continue
        indices_sorted = sorted(set(indices))

        # Encuentra rachas consecutivas
        rachas: List[List[int]] = []
        racha_actual = [indices_sorted[0]]
        for i in range(1, len(indices_sorted)):
            if indices_sorted[i] == indices_sorted[i - 1] + 1:
                racha_actual.append(indices_sorted[i])
            else:
                rachas.append(racha_actual)
                racha_actual = [indices_sorted[i]]
        rachas.append(racha_actual)

        for racha in rachas:
            if len(racha) < 3:
                continue
            cartas_racha = [Carta(palo=palo, valor=SECUENCIA_CANTES[i]) for i in racha]
            if len(racha) >= 5:
                cantes.append(Cante("cien_seq", 100, cartas_racha, jugador))
            elif len(racha) == 4:
                cantes.append(Cante("cincuenta", 50, cartas_racha, jugador))
            else:
                cantes.append(Cante("tercera", 20, cartas_racha, jugador))

    return cantes


def _detectar_iguales(mano: List[Carta], jugador: int) -> List[Cante]:
    """Detecta cantes con cuatro cartas del mismo valor."""
    by_valor: Dict[Valor, List[Carta]] = {}
    for carta in mano:
        by_valor.setdefault(carta.valor, []).append(carta)

    cantes: List[Cante] = []
    for valor, cartas in by_valor.items():
        if len(cartas) == 4:
            if valor == Valor.NUEVE:
                cantes.append(Cante("ciento_cincuenta", 150, cartas, jugador))
            elif valor == Valor.SOTA:
                cantes.append(Cante("doscientos", 200, cartas, jugador))
            elif valor in (Valor.TRES, Valor.CABALLO, Valor.REY, Valor.AS):
                cantes.append(Cante("cien_cuatro", 100, cartas, jugador))

    return cantes


def _detectar_bolot(mano: List[Carta], triunfo: Palo, jugador: int) -> Optional[Cante]:
    """Detecta si el jugador tiene Caballo y Rey del palo de triunfo."""
    tiene_caballo = any(c.palo == triunfo and c.valor == Valor.CABALLO for c in mano)
    tiene_rey = any(c.palo == triunfo and c.valor == Valor.REY for c in mano)
    if tiene_caballo and tiene_rey:
        cartas = [
            next(c for c in mano if c.palo == triunfo and c.valor == Valor.CABALLO),
            next(c for c in mano if c.palo == triunfo and c.valor == Valor.REY),
        ]
        return Cante("bolot", 20, cartas, jugador)
    return None


_TIPOS_IGUALES = {"cien_cuatro", "ciento_cincuenta", "doscientos"}
_TIPOS_SEQ     = {"tercera", "cincuenta", "cien_seq"}
_TIPOS_CANTE   = _TIPOS_SEQ | _TIPOS_IGUALES


def _mejor_cante_equipo(cantes: List[Cante]) -> Optional[Cante]:
    """Devuelve el cante más fuerte de una lista (excluye bolot/rebolot)."""
    relevantes = [c for c in cantes if c.tipo in _TIPOS_CANTE]
    if not relevantes:
        return None
    def _clave(c: Cante):
        es_iguales = c.tipo in _TIPOS_IGUALES
        top_seq = (
            max(SECUENCIA_CANTES.index(carta.valor) for carta in c.cartas)
            if c.tipo in _TIPOS_SEQ else 0
        )
        return (c.puntos, 1 if es_iguales else 0, top_seq)
    return max(relevantes, key=_clave)


def _resolver_cantes_todos(
    cantes_por_equipo: List[List[Cante]],
    triunfo: Optional[Palo],
    mano_idx: int,
) -> Optional[int]:
    """
    Determina qué equipo gana el derecho a puntuar todos sus cantes
    (secuencias + iguales). Bolot/rebolot se gestionan aparte.

    Criterios:
      1. Puntos del mejor cante (mayor gana)
      2. Iguales gana a secuencia si ambos valen 100
      3. Si ambos son secuencias: carta más alta de la escalera
      4. Si misma carta alta: palo de triunfo
      5. Desempate: equipo del jugador mano
    """
    mejor = [
        _mejor_cante_equipo(cantes_por_equipo[0]),
        _mejor_cante_equipo(cantes_por_equipo[1]),
    ]

    if mejor[0] is None and mejor[1] is None:
        return None
    if mejor[0] is None:
        return 1
    if mejor[1] is None:
        return 0

    # 1. Puntos
    if mejor[0].puntos != mejor[1].puntos:
        return 0 if mejor[0].puntos > mejor[1].puntos else 1

    # 2. Iguales > secuencia (para el empate de 100 pts)
    ig0 = mejor[0].tipo in _TIPOS_IGUALES
    ig1 = mejor[1].tipo in _TIPOS_IGUALES
    if ig0 != ig1:
        return 0 if ig0 else 1

    # 3. Ambos son secuencias: carta más alta
    if not ig0:
        top0 = max(SECUENCIA_CANTES.index(c.valor) for c in mejor[0].cartas)
        top1 = max(SECUENCIA_CANTES.index(c.valor) for c in mejor[1].cartas)
        if top0 != top1:
            return 0 if top0 > top1 else 1

        # 4. Palo de triunfo
        if triunfo:
            p0 = mejor[0].cartas[0].palo
            p1 = mejor[1].cartas[0].palo
            if p0 == triunfo and p1 != triunfo:
                return 0
            if p1 == triunfo and p0 != triunfo:
                return 1

    # 5. Desempate: equipo del jugador mano
    return equipo_de(mano_idx)


def _clave_cante(cante: Cante) -> str:
    return cante.tipo + ":" + ",".join(sorted(f"{c.valor.value}_{c.palo.value}" for c in cante.cartas))


def cantes_disponibles(estado: EstadoPartida, jugador: int) -> List[Cante]:
    if estado.fase != Fase.BAZAS or estado.turno != jugador or estado.bazas_jugadas:
        return []
    mano = estado.manos[jugador]
    candidatos = _detectar_secuencias(mano, jugador) + _detectar_iguales(mano, jugador)
    ya = {_clave_cante(c) for c in estado.cantes_anunciados.get(jugador, [])}
    return [c for c in candidatos if _clave_cante(c) not in ya]


def cantar_cante(estado: EstadoPartida, jugador: int, clave: str) -> EstadoPartida:
    estado.error = None
    cante = next((c for c in cantes_disponibles(estado, jugador) if _clave_cante(c) == clave), None)
    if cante is None:
        estado.error = "No tienes ese cante disponible en esta primera baza"
        return estado
    estado.cantes_anunciados.setdefault(jugador, []).append(cante)
    estado.anuncios_primera[jugador] = ", ".join(c.tipo for c in estado.cantes_anunciados[jugador])
    return estado


def puede_ensenar_cantes(estado: EstadoPartida, jugador: int) -> bool:
    """Solo el equipo ganador puede mostrar sus anuncios en la segunda baza."""
    return (estado.fase == Fase.BAZAS and estado.turno == jugador
            and len(estado.bazas_jugadas) == 1
            and estado.equipo_ganador_cantes == equipo_de(jugador)
            and bool(estado.cantes_anunciados.get(jugador)))


def ensenar_cantes(estado: EstadoPartida, jugador: int) -> EstadoPartida:
    estado.error = None
    if estado.fase != Fase.BAZAS or estado.turno != jugador or len(estado.bazas_jugadas) != 1:
        estado.error = "Solo puedes enseñar antes de tirar en la segunda baza"
        return estado
    if estado.equipo_ganador_cantes != equipo_de(jugador):
        estado.error = "Tu equipo no ha ganado el choque de cantes"
        return estado
    cantes = estado.cantes_anunciados.pop(jugador, [])
    if not cantes:
        estado.error = "No hay cantes anunciados para enseñar"
        return estado
    estado.cantes_ensenados[jugador] = cantes
    return estado


def bolot_disponible(estado: EstadoPartida, jugador: int) -> Optional[str]:
    """Tipo de bolot que el jugador puede cantar ANTES de tirar, o None.

    Bolot: tiene Caballo y Rey de triunfo en mano y aún no ha jugado ninguno.
    Rebolot: ya cantó bolot, ya jugó la primera de la pareja y le queda la otra.
    """
    if estado.fase != Fase.BAZAS or estado.turno != jugador or not estado.triunfo:
        return None
    mano = estado.manos[jugador]
    triunfo = estado.triunfo
    if not estado.bolot_declarado[jugador] and not estado.bolot_primera_jugada[jugador]:
        if _detectar_bolot(mano, triunfo, jugador):
            return "bolot"
    if estado.bolot_declarado[jugador] and estado.bolot_primera_jugada[jugador] \
            and not estado.rebolot_declarado[jugador]:
        if any(c.palo == triunfo and c.valor in (Valor.CABALLO, Valor.REY) for c in mano):
            return "rebolot"
    return None


def declarar_bolot(estado: EstadoPartida, jugador: int) -> EstadoPartida:
    estado.error = None
    pendiente = estado.bolot_pendiente
    if pendiente and pendiente[0] == jugador and time.monotonic() <= pendiente[2]:
        _, tipo, _ = pendiente
        estado.bolot_pendiente = None
    else:
        # Sin ventana: el botón se ofrece antes de tirar la carta.
        tipo = bolot_disponible(estado, jugador)
        if not tipo:
            estado.error = "No hay bolot que cantar ahora"
            return estado
    if tipo == "bolot":
        estado.bolot_declarado[jugador] = True
        cante = Cante(tipo, 20, [], jugador)
    else:
        estado.rebolot_declarado[jugador] = True
        cante = Cante(tipo, 0, [], jugador)
    estado.cantes.append(cante)
    estado.cantes_equipo[equipo_de(jugador)] += cante.puntos
    return estado


# ---------------------------------------------------------------------------
# Creación de partida
# ---------------------------------------------------------------------------

def nueva_partida(objetivo: int = 1000, dealer: Optional[int] = None) -> EstadoPartida:
    """
    Crea e inicializa una nueva mano de Bolot.

    Reparto inicial:
      - 5 cartas a cada jugador (20 cartas)
      - 1 carta boca arriba en el centro → triunfo propuesto "de primeras"
      - 11 cartas quedan en el mazo para repartir cuando alguien diga "voy"

    El dealer reparte; el jugador siguiente (mano) habla primero en la subasta.
    """
    if dealer is None:
        dealer = random.randint(0, 3)
    mano_idx = (dealer + 1) % 4

    baraja = barajar(crear_baraja())

    manos = [list(baraja[i * 5:(i + 1) * 5]) for i in range(4)]
    carta_mesa = baraja[20]
    mazo = list(baraja[21:])   # 11 cartas restantes

    return EstadoPartida(
        id=str(uuid.uuid4()),
        manos=manos,
        mazo=mazo,
        fase=Fase.SUBASTA_PRIMERAS,
        turno=mano_idx,
        mano_idx=mano_idx,
        triunfo=None,                   # se confirma cuando alguien va
        triunfo_propuesto=carta_mesa.palo,
        carta_mesa=carta_mesa,
        quien_va=None,
        votos_subasta=[None, None, None, None],
        baza_actual=Baza(),
        bazas_jugadas=[],
        puntos_mano=[0, 0],
        puntos_totales=[0, 0],
        cantes=[],
        cantes_equipo=[0, 0],
        bolot_declarado=[False, False, False, False],
        rebolot_declarado=[False, False, False, False],
        ultimas_ganadas_por=None,
        capota_equipo=None,
        objetivo=objetivo,
        dealer=dealer,
        cantes_pendientes_humano=[],
        error=None,
        anuncios_primera={},
        cantes_anunciados={},
        cantes_ensenados={},
        bolot_pendiente=None,
        bolot_primera_jugada=[False] * 4,
    )


# ---------------------------------------------------------------------------
# Subasta
# ---------------------------------------------------------------------------

def votar_subasta(
    estado: EstadoPartida,
    jugador: int,
    accion: str,           # "voy" | "no_voy"
    palo: Optional[Palo] = None,   # solo necesario en segundas para "voy"
) -> EstadoPartida:
    """
    Procesa un voto en la subasta.

    De primeras: se acepta o rechaza el palo de la carta boca arriba.
    De segundas: quien va propone un palo diferente al de la carta boca arriba.

    Al decir "voy":
      - El jugador toma la carta de la mesa (si es de primeras)
      - Se reparten 2 cartas más al jugador que va y 3 a cada uno de los demás
      - Se pasa directamente a BAZAS
    """
    estado.error = None

    if estado.turno != jugador:
        estado.error = f"No es el turno del jugador {jugador}"
        return estado

    if accion == "voy":
        if estado.fase == Fase.SUBASTA_PRIMERAS:
            # Toma la carta de la mesa y confirma el triunfo
            estado.manos[jugador].append(estado.carta_mesa)
            estado.triunfo = estado.triunfo_propuesto
        else:
            # De segundas: propone un palo diferente; la carta de la mesa también va al jugador
            if palo is None:
                estado.error = "Debes indicar el palo en la subasta de segundas"
                return estado
            if palo == estado.triunfo_propuesto:
                estado.error = "En segundas no puedes proponer el mismo palo que la carta de la mesa"
                return estado
            estado.triunfo = palo
            if estado.carta_mesa:
                estado.manos[jugador].append(estado.carta_mesa)

        estado.quien_va = jugador
        estado.carta_mesa = None

        # Repartir cartas adicionales del mazo
        # El jugador que va recibe 2; los demás reciben 3 cada uno
        # (en ambos casos ya tomó la carta_mesa, quedando con 5+1+2=8)
        estado.manos[jugador].extend(estado.mazo[:2])
        estado.mazo = estado.mazo[2:]
        for j in range(4):
            if j != jugador:
                estado.manos[j].extend(estado.mazo[:3])
                estado.mazo = estado.mazo[3:]

        estado.fase = Fase.BAZAS
        estado.turno = estado.mano_idx

    else:  # "no_voy"
        estado.votos_subasta[jugador] = "no_voy"
        next_j = siguiente_turno(jugador)

        if all(v is not None for v in estado.votos_subasta):
            # Todos han votado y nadie ha dicho voy
            if estado.fase == Fase.SUBASTA_PRIMERAS:
                estado.fase = Fase.SUBASTA_SEGUNDAS
                estado.votos_subasta = [None, None, None, None]
                estado.turno = estado.mano_idx
            else:
                # Todos pasan en segundas → mano nula
                estado.fase = Fase.FIN_MANO
        else:
            estado.turno = next_j

    return estado


# ---------------------------------------------------------------------------
# Validación de jugadas
# ---------------------------------------------------------------------------

def cartas_jugables(estado: EstadoPartida, jugador: int) -> List[Carta]:
    """
    Devuelve las cartas que el jugador puede jugar legalmente en este momento.

    Reglas:
      - Si la baza está vacía: cualquier carta.
      - Siempre hay que seguir el palo de salida si se tiene.
      - Si el palo de salida es triunfo: además hay que superar la mayor carta
        de triunfo sobre la mesa si es posible.
      - Si no se tiene el palo de salida y no es triunfo:
          · Si el compañero va ganando la baza → cualquier carta.
          · Si no → hay que fallar (jugar triunfo); si no se tiene, cualquier carta.
      - Si no se tiene ninguna carta válida obligatoria → cualquier carta.
    """
    mano = estado.manos[jugador]
    baza = estado.baza_actual
    triunfo = estado.triunfo

    if not baza.cartas:
        return list(mano)

    palo_salida = baza.cartas[0][1].palo
    cartas_palo = [c for c in mano if c.palo == palo_salida]

    if palo_salida == triunfo:
        # Palo de salida es triunfo: obligatorio seguir y, si se puede superar, hay que hacerlo
        # EXCEPCIÓN: si el compañero ya va ganando, no hace falta superar
        if cartas_palo:
            if _companyero_ganando(baza, jugador, triunfo):
                return cartas_palo  # cualquier triunfo vale; no hay obligación de superar
            mayor_mesa = max(
                (c for _, c in baza.cartas if c.palo == triunfo),
                key=lambda c: c.rango(triunfo),
                default=None,
            )
            if mayor_mesa:
                ganadoras = [c for c in cartas_palo if c.rango(triunfo) > mayor_mesa.rango(triunfo)]
                if ganadoras:
                    return ganadoras
            return cartas_palo
        return list(mano)

    # Palo de salida NO es triunfo
    if cartas_palo:
        return cartas_palo

    # No tiene el palo: comprueba si el compañero va ganando
    if _companyero_ganando(baza, jugador, triunfo):
        return list(mano)

    # El compañero no gana: hay que fallar (jugar triunfo)
    cartas_triunfo = [c for c in mano if c.palo == triunfo] if triunfo else []
    if cartas_triunfo:
        return cartas_triunfo

    return list(mano)


def _ganador_parcial(baza: Baza, triunfo: Optional[Palo]) -> int:
    """Devuelve el índice del jugador que va ganando la baza (parcial o completa)."""
    gan_j, gan_c = baza.cartas[0]
    for j, c in baza.cartas[1:]:
        # La carta c puede ganar si:
        # - Es del mismo palo que la ganadora actual y tiene mayor rango
        # - Es triunfo y la ganadora actual no lo es
        if c.palo == gan_c.palo:
            if c.rango(triunfo) > gan_c.rango(triunfo):
                gan_j, gan_c = j, c
        elif triunfo and c.palo == triunfo and gan_c.palo != triunfo:
            gan_j, gan_c = j, c
    return gan_j


def _companyero_ganando(baza: Baza, jugador: int, triunfo: Optional[Palo]) -> bool:
    """True si el compañero del jugador va ganando la baza actualmente."""
    if not baza.cartas:
        return False
    ganador = _ganador_parcial(baza, triunfo)
    return equipo_de(ganador) == equipo_de(jugador) and ganador != jugador


# ---------------------------------------------------------------------------
# Jugada de carta
# ---------------------------------------------------------------------------

def jugar_carta(estado: EstadoPartida, jugador: int, carta: Carta) -> EstadoPartida:
    """
    El jugador juega una carta.
    Abre una ventana para declarar bolot/rebolot al jugar
    Caballo o Rey de triunfo, sin dar puntos automáticamente.
    """
    estado.error = None

    if estado.fase != Fase.BAZAS:
        estado.error = "No es momento de jugar cartas"
        return estado

    if estado.turno != jugador:
        estado.error = f"No es el turno del jugador {jugador}"
        return estado

    if carta not in estado.manos[jugador]:
        estado.error = "El jugador no tiene esa carta"
        return estado

    jugables = cartas_jugables(estado, jugador)
    if carta not in jugables:
        estado.error = "No puedes jugar esa carta (incumple las reglas de seguir palo o fallar)"
        return estado

    # Los cantes olvidados al tirar se pierden. Los anuncios anteriores
    # guardan su foto de la mano de la primera baza, aunque esa carta salga.
    numero_baza = len(estado.bazas_jugadas)
    if numero_baza == 1:
        estado.cantes_anunciados.pop(jugador, None)

    # Una carta de la pareja de triunfo abre una ventana real de cinco segundos.
    # Si el jugador no pulsó Bolot, la segunda carta no genera Rebolot.
    if estado.bolot_pendiente and (time.monotonic() > estado.bolot_pendiente[2] or estado.bolot_pendiente[0] == jugador):
        estado.bolot_pendiente = None
    triunfo = estado.triunfo
    if triunfo and carta.palo == triunfo and carta.valor in (Valor.CABALLO, Valor.REY):
        primera = _detectar_bolot(estado.manos[jugador], triunfo, jugador)
        if primera and not estado.bolot_primera_jugada[jugador]:
            estado.bolot_primera_jugada[jugador] = True
            if not estado.bolot_declarado[jugador]:
                estado.bolot_pendiente = (jugador, "bolot", time.monotonic() + 5)
        elif estado.bolot_primera_jugada[jugador] and estado.bolot_declarado[jugador] and not estado.rebolot_declarado[jugador]:
            estado.bolot_pendiente = (jugador, "rebolot", time.monotonic() + 5)

    # Jugar la carta
    estado.manos[jugador].remove(carta)
    estado.baza_actual.cartas.append((jugador, carta))

    if len(estado.baza_actual.cartas) == 4:
        _resolver_baza(estado)
    else:
        estado.turno = siguiente_turno(jugador)

    return estado


# ---------------------------------------------------------------------------
# Resolución de baza
# ---------------------------------------------------------------------------

def _resolver_baza(estado: EstadoPartida) -> None:
    """Cierra la baza actual, asigna puntos y prepara la siguiente."""
    baza = estado.baza_actual
    triunfo = estado.triunfo

    ganador = _ganador_parcial(baza, triunfo)
    baza.ganador = ganador
    baza.puntos = sum(c.puntos_en_juego(triunfo) for _, c in baza.cartas)

    eq_ganador = equipo_de(ganador)
    estado.puntos_mano[eq_ganador] += baza.puntos
    estado.ultimas_ganadas_por = eq_ganador

    estado.bazas_jugadas.append(baza)
    estado.baza_actual = Baza()

    # Todos han podido anunciar. Fijar el ganador ANTES de enseñar;
    # los anuncios se consumen después y no deben cambiar el choque.
    if len(estado.bazas_jugadas) == 1:
        anuncios: List[List[Cante]] = [[], []]
        for j, cantes in estado.cantes_anunciados.items():
            anuncios[equipo_de(j)].extend(cantes)
        estado.equipo_ganador_cantes = _resolver_cantes_todos(
            anuncios, estado.triunfo, estado.mano_idx)

    # Resolver únicamente los cantes anunciados y enseñados. Al terminar
    # la segunda baza ya pasaron todos los turnos de exhibición.
    if len(estado.bazas_jugadas) == 2:
        _procesar_cantes_pre_segunda(estado)

    if len(estado.bazas_jugadas) == 8:
        # Última baza: sumar las 10 de últimas
        estado.puntos_mano[eq_ganador] += PUNTOS_ULTIMAS
        _fin_mano(estado)
    else:
        estado.turno = ganador


def _procesar_cantes_pre_segunda(estado: EstadoPartida) -> None:
    """
    Puntúa los cantes enseñados a tiempo por el ganador del choque,
    fijado al terminar la primera baza. Bolot/rebolot van aparte.
    """
    cantes_por_equipo: List[List[Cante]] = [[], []]

    for j in range(4):
        cantes_por_equipo[equipo_de(j)].extend(estado.cantes_ensenados.get(j, []))

    eq_gana = estado.equipo_ganador_cantes
    if eq_gana is not None:
        for cante in cantes_por_equipo[eq_gana]:
            # Solo cuentan los anunciados y enseñados a tiempo
            estado.cantes.append(cante)
            estado.cantes_equipo[eq_gana] += cante.puntos
    estado.cantes_anunciados.clear()
    estado.cantes_ensenados.clear()


# ---------------------------------------------------------------------------
# Fin de mano y puntuación
# ---------------------------------------------------------------------------

def _fin_mano(estado: EstadoPartida) -> None:
    """
    Calcula y asigna los puntos de la mano a los totales del juego.

    Si la pareja que "va" no alcanza la mayoría de puntos en juego
    (estar puestos), todos los puntos van al equipo contrario.

    Si una pareja hace capote (la otra no hace ninguna baza), añade 100 puntos
    extra y no se cuentan las 10 de últimas.
    """
    estado.fase = Fase.FIN_MANO

    if estado.quien_va is None:
        # Mano nula (todos pasaron en subasta) → nadie puntúa
        return

    eq_va = equipo_de(estado.quien_va)
    eq_no_va = 1 - eq_va

    # Comprobar capote: ¿alguna pareja no ha ganado ninguna baza?
    bazas_por_equipo = [0, 0]
    for baza in estado.bazas_jugadas:
        if baza.ganador is not None:
            bazas_por_equipo[equipo_de(baza.ganador)] += 1

    capote_eq = None
    if bazas_por_equipo[eq_va] == 0:
        capote_eq = eq_no_va   # el equipo que no va hizo capotá al equipo que va
    elif bazas_por_equipo[eq_no_va] == 0:
        capote_eq = eq_va      # el equipo que va hizo capotá al equipo que no va
    estado.capota_equipo = capote_eq

    # Puntos totales en juego (cartas + cantes)
    puntos_en_juego_va = estado.puntos_mano[eq_va] + estado.cantes_equipo[eq_va]
    puntos_en_juego_nova = estado.puntos_mano[eq_no_va] + estado.cantes_equipo[eq_no_va]
    total_en_juego = puntos_en_juego_va + puntos_en_juego_nova

    # La pareja que va necesita estrictamente más que la mitad
    mitad = total_en_juego / 2
    va_gana = puntos_en_juego_va > mitad

    if va_gana:
        if capote_eq == eq_va:
            # Capote del equipo que va: todas las bazas, sin contar últimas, +100
            pts_bazas = estado.puntos_mano[eq_va] - PUNTOS_ULTIMAS  # quitar las 10 de últimas
            estado.puntos_totales[eq_va] += pts_bazas + estado.cantes_equipo[eq_va] + 100
            # El equipo que no va no hace bazas → 0 puntos de bazas, pero sí sus cantes
            estado.puntos_totales[eq_no_va] += estado.cantes_equipo[eq_no_va]
        else:
            # Victoria normal: cada equipo suma lo suyo
            estado.puntos_totales[eq_va]   += puntos_en_juego_va
            estado.puntos_totales[eq_no_va] += puntos_en_juego_nova
    else:
        # Están puestos: todos los puntos de bazas van al equipo que no va
        if capote_eq == eq_no_va:
            # Capote del equipo que no va: se lleva todas las bazas sin últimas, +100
            pts_bazas = estado.puntos_mano[eq_no_va] - PUNTOS_ULTIMAS
            estado.puntos_totales[eq_no_va] += (
                pts_bazas
                + estado.puntos_mano[eq_va]   # bazas del equipo que va (0 si capote real)
                + estado.cantes_equipo[eq_no_va]
                + 100
            )
        else:
            # Puestos sin capote: eq_no_va se lleva todas las bazas
            estado.puntos_totales[eq_no_va] += (
                estado.puntos_mano[eq_va]
                + estado.puntos_mano[eq_no_va]
                + estado.cantes_equipo[eq_no_va]
            )
        # Los cantes del equipo que va se pierden (están puestos)


