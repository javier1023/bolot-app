"""
Gestión de salas multijugador para Bolot.

Una sala contiene 4 slots (0-3):
  Equipo A: slots 0 y 2
  Equipo B: slots 1 y 3

El anfitrión ocupa siempre el slot 0.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import WebSocket

from .game import EstadoPartida


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SLOTS_EQUIPO_A = {0, 2}
SLOTS_EQUIPO_B = {1, 3}


def _slots_libres_equipo(jugadores: Dict[int, str], equipo: str) -> List[int]:
    slots = SLOTS_EQUIPO_A if equipo == "A" else SLOTS_EQUIPO_B
    return [s for s in sorted(slots) if s not in jugadores]


# ---------------------------------------------------------------------------
# Dataclass Sala
# ---------------------------------------------------------------------------

@dataclass
class Sala:
    codigo: str
    anfitrion_slot: int                        # siempre 0
    jugadores: Dict[int, str]                  # slot → nombre
    conexiones: Dict[int, Optional[WebSocket]] # slot → WebSocket (None si desconectado)
    objetivo: int                              # 1000 o 1500
    estado: Optional[EstadoPartida] = None     # None hasta que empiece la partida
    iniciada: bool = False
    con_limite: bool = False                   # True = turno con límite de 20s
    espectadores: Dict[str, Optional[WebSocket]] = field(default_factory=dict)  # nombre → ws

    def slots_ocupados(self) -> List[int]:
        return sorted(self.jugadores.keys())

    def num_jugadores(self) -> int:
        return len(self.jugadores)

    def completa(self) -> bool:
        return len(self.jugadores) == 4

    def slot_libre(self, equipo: str) -> Optional[int]:
        """Devuelve el primer slot libre del equipo dado, o None si está lleno."""
        libres = _slots_libres_equipo(self.jugadores, equipo)
        return libres[0] if libres else None

    def equipo_de_slot(self, slot: int) -> str:
        return "A" if slot in SLOTS_EQUIPO_A else "B"

    def nombre_jugador(self, slot: int) -> str:
        return self.jugadores.get(slot, f"J{slot}")

    def to_dict(self, mi_slot: Optional[int] = None) -> dict:
        equipos = {
            "A": {s: self.jugadores.get(s) for s in [0, 2]},
            "B": {s: self.jugadores.get(s) for s in [1, 3]},
        }
        return {
            "codigo": self.codigo,
            "equipos": equipos,
            "objetivo": self.objetivo,
            "iniciada": self.iniciada,
            "completa": self.completa(),
            "mi_slot": mi_slot,
            "con_limite": self.con_limite,
        }

    async def broadcast(self, mensaje: dict) -> None:
        """Envía un mensaje JSON a todos los jugadores conectados."""
        import json
        texto = json.dumps(mensaje, ensure_ascii=False)
        for slot, ws in self.conexiones.items():
            if ws is not None:
                try:
                    await ws.send_text(texto)
                except Exception:
                    self.conexiones[slot] = None

    async def broadcast_estado(self) -> None:
        """Envía el estado del juego filtrado a cada jugador y espectadores."""
        if self.estado is None:
            return
        nombres = {s: self.jugadores.get(s, f"J{s}") for s in range(4)}
        import json

        for slot, ws in self.conexiones.items():
            if ws is not None:
                try:
                    datos = self.estado.to_dict_para(slot, nombres)
                    datos["con_limite"] = self.con_limite
                    await ws.send_text(json.dumps({"tipo": "estado", "estado": datos}, ensure_ascii=False))
                except Exception:
                    self.conexiones[slot] = None

        # Espectadores: reciben estado con todas las manos ocultas (slot 4 no existe → todo oculto)
        datos_espect = self.estado.to_dict_para(4, nombres)
        datos_espect["con_limite"] = self.con_limite
        datos_espect["espectador"] = True
        texto_espect = json.dumps({"tipo": "estado", "estado": datos_espect}, ensure_ascii=False)
        for nombre, ws in list(self.espectadores.items()):
            if ws is not None:
                try:
                    await ws.send_text(texto_espect)
                except Exception:
                    self.espectadores[nombre] = None


# ---------------------------------------------------------------------------
# Registro global de salas
# ---------------------------------------------------------------------------

salas: Dict[str, Sala] = {}


def generar_codigo() -> str:
    """Genera un código de 4 letras mayúsculas único entre salas activas."""
    while True:
        codigo = "".join(random.choices(string.ascii_uppercase, k=4))
        if codigo not in salas:
            return codigo


def crear_sala(nombre_anfitrion: str, objetivo: int, con_limite: bool = False) -> Sala:
    codigo = generar_codigo()
    sala = Sala(
        codigo=codigo,
        anfitrion_slot=0,
        jugadores={0: nombre_anfitrion},
        conexiones={0: None},
        objetivo=objetivo,
        con_limite=con_limite,
    )
    salas[codigo] = sala
    return sala


def obtener_sala(codigo: str) -> Optional[Sala]:
    return salas.get(codigo.upper())

