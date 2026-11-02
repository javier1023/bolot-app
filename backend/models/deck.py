"""
Módulo de la baraja para Bolot.

Baraja española recortada: se eliminan el 2, 4, 5 y 6.
Quedan 8 cartas por palo × 4 palos = 32 cartas.
  As, 3, 7, 8, 9, Sota, Caballo, Rey

Puntuación base (palo NO triunfo):
  As      → 11 pts
  3       → 10 pts
  Rey     → 4 pts
  Caballo → 3 pts
  Sota    → 2 pts
  9, 8, 7 → 0 pts

Puntuación especial cuando el palo ES triunfo:
  Sota (Valet)   → 20 pts
  Nueve (Catorce) → 14 pts
  (el resto mantiene su puntuación base)

Orden cuando el palo ES triunfo (de menor a mayor):
  7 < 8 < Caballo < Rey < 3 < As < 9(Catorce) < Sota(Valet)

Orden cuando el palo NO es triunfo (de menor a mayor):
  7 < 8 < 9 < Sota < Caballo < Rey < 3 < As

Puntos en juego por mano:
  152 (cartas) + 10 (últimas) = 162
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional
import random


class Palo(str, Enum):
    OROS = "oros"
    COPAS = "copas"
    ESPADAS = "espadas"
    BASTOS = "bastos"


class Valor(str, Enum):
    AS = "as"
    TRES = "tres"
    SIETE = "siete"
    OCHO = "ocho"
    NUEVE = "nueve"
    SOTA = "sota"
    CABALLO = "caballo"
    REY = "rey"


# Número impreso en la carta (para mostrar en UI)
NUMERO_CARTA: Dict[Valor, int] = {
    Valor.AS: 1,
    Valor.TRES: 3,
    Valor.SIETE: 7,
    Valor.OCHO: 8,
    Valor.NUEVE: 9,
    Valor.SOTA: 10,
    Valor.CABALLO: 11,
    Valor.REY: 12,
}

# Puntos base de cada carta (independiente del triunfo)
PUNTUACION: Dict[Valor, int] = {
    Valor.AS: 11,
    Valor.TRES: 10,
    Valor.REY: 4,
    Valor.CABALLO: 3,
    Valor.SOTA: 2,
    Valor.NUEVE: 0,
    Valor.OCHO: 0,
    Valor.SIETE: 0,
}

# Puntos especiales cuando la carta pertenece al palo de triunfo
PUNTUACION_TRIUNFO: Dict[Valor, int] = {
    **PUNTUACION,
    Valor.SOTA: 20,   # Valet
    Valor.NUEVE: 14,  # Catorce
}

# Orden cuando el palo ES triunfo (índice más alto = carta más fuerte)
# 7 < 8 < Caballo < Rey < 3 < As < 9(Catorce) < Sota(Valet)
ORDEN_TRIUNFO: List[Valor] = [
    Valor.SIETE,
    Valor.OCHO,
    Valor.CABALLO,
    Valor.REY,
    Valor.TRES,
    Valor.AS,
    Valor.NUEVE,   # Catorce
    Valor.SOTA,    # Valet
]

# Orden cuando el palo NO es triunfo (índice más alto = carta más fuerte)
# 7 < 8 < 9 < Sota < Caballo < Rey < 3 < As
ORDEN_NO_TRIUNFO: List[Valor] = [
    Valor.SIETE,
    Valor.OCHO,
    Valor.NUEVE,
    Valor.SOTA,
    Valor.CABALLO,
    Valor.REY,
    Valor.TRES,
    Valor.AS,
]

# Puntos base totales de la baraja (sin contar valores especiales de triunfo)
PUNTOS_BASE = sum(PUNTUACION.values()) * len(Palo)  # 120

# Puntos en juego en una mano con triunfo (Sota=20, Nueve=14 en triunfo)
# 120 + (20-2) + (14-0) = 152; más 10 de últimas = 162
PUNTOS_CON_TRIUNFO = 152
PUNTOS_ULTIMAS = 10
PUNTOS_TOTALES = PUNTOS_CON_TRIUNFO + PUNTOS_ULTIMAS  # 162


@dataclass(frozen=True)
class Carta:
    palo: Palo
    valor: Valor

    @property
    def puntos(self) -> int:
        """Puntos base de la carta (sin contexto de triunfo)."""
        return PUNTUACION[self.valor]

    def puntos_en_juego(self, triunfo: Optional[Palo] = None) -> int:
        """
        Puntos reales de la carta según el triunfo actual.
        Sota y Nueve del palo de triunfo tienen valores especiales.
        """
        if triunfo is not None and self.palo == triunfo:
            return PUNTUACION_TRIUNFO[self.valor]
        return PUNTUACION[self.valor]

    @property
    def numero(self) -> int:
        return NUMERO_CARTA[self.valor]

    def rango(self, triunfo: Optional[Palo] = None) -> int:
        """
        Devuelve el rango de la carta en el contexto del triunfo actual.
        Rango más alto = carta más fuerte.
        Las cartas de triunfo reciben un offset (8) para que siempre superen
        a las de palo no triunfo.
        """
        base = len(ORDEN_TRIUNFO)  # 8
        if triunfo is not None and self.palo == triunfo:
            return base + ORDEN_TRIUNFO.index(self.valor)
        return ORDEN_NO_TRIUNFO.index(self.valor)

    def __str__(self) -> str:
        return f"{self.valor.value.capitalize()} de {self.palo.value.capitalize()}"

    def to_dict(self) -> dict:
        return {
            "palo": self.palo.value,
            "valor": self.valor.value,
            "numero": self.numero,
            "puntos_base": self.puntos,
        }


def crear_baraja() -> List[Carta]:
    """Devuelve las 32 cartas de la baraja ordenadas por palo y valor."""
    return [
        Carta(palo=palo, valor=valor)
        for palo in Palo
        for valor in Valor
    ]


def barajar(cartas: List[Carta]) -> List[Carta]:
    """Devuelve una copia barajada de la lista de cartas."""
    copia = list(cartas)
    random.shuffle(copia)
    return copia


def carta_ganadora(carta_a: Carta, carta_b: Carta, triunfo: Optional[Palo] = None) -> Carta:
    """
    Determina qué carta gana entre dos.
    carta_a se asume ganadora actual (jugada primero o ya liderando la baza).
    - Si carta_b es del mismo palo que carta_a, gana la de mayor rango.
    - Si carta_b es triunfo y carta_a no, carta_b puede ganar.
    - Si carta_b es de otro palo distinto al de carta_a y no es triunfo, gana carta_a.
    """
    if carta_a.palo == carta_b.palo or (
        triunfo is not None and carta_b.palo == triunfo
    ):
        return carta_a if carta_a.rango(triunfo) > carta_b.rango(triunfo) else carta_b
    return carta_a

