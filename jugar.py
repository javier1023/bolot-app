"""
Juego interactivo de Bolot.
Tú eres el Jugador 0 (Equipo 0, junto con el Jugador 2).
Los jugadores 1, 2 y 3 son la máquina.
"""

import sys
import os
import io

# Forzar UTF-8 en la consola de Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.stdin  = io.TextIOWrapper(sys.stdin.buffer,  encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from models.game import (
    nueva_partida, votar_subasta, jugar_carta, cartas_jugables,
    equipo_de, EstadoPartida, Fase,
)
from models.deck import Carta, Palo, Valor

JUGADOR_HUMANO = 0

# ---------------------------------------------------------------------------
# Helpers de visualización
# ---------------------------------------------------------------------------

PALOS_ES = {
    "oros": "Oros  ", "copas": "Copas ", "espadas": "Espadas", "bastos": "Bastos",
}
VALORES_CORTOS = {
    "siete": "7", "ocho": "8", "nueve": "9", "tres": "3",
    "sota": "J", "caballo": "C", "rey": "R", "as": "A",
}


def carta_str(c: Carta) -> str:
    v = VALORES_CORTOS.get(c.valor.value, c.valor.value)
    p = c.palo.value[:3].capitalize()
    return f"{v}-{p}"


def separador():
    print("─" * 60)


def mostrar_estado(estado: EstadoPartida):
    separador()
    triunfo = estado.triunfo.value if estado.triunfo else (
        f"{estado.triunfo_propuesto.value} (propuesto)" if estado.triunfo_propuesto else "—"
    )
    print(f"  Triunfo: {triunfo}   |   Fase: {estado.fase.value}")
    print(f"  Puntos totales → Eq0 (tú+J2): {estado.puntos_totales[0]}   Eq1 (J1+J3): {estado.puntos_totales[1]}")
    print(f"  Puntos esta mano → Eq0: {estado.puntos_mano[0]}   Eq1: {estado.puntos_mano[1]}")
    if estado.cantes_equipo[0] or estado.cantes_equipo[1]:
        print(f"  Cantes → Eq0: {estado.cantes_equipo[0]}   Eq1: {estado.cantes_equipo[1]}")
    separador()

    # Carta en mesa (subasta)
    if estado.carta_mesa:
        print(f"  Carta en mesa: [{carta_str(estado.carta_mesa)}]")

    # Baza actual
    if estado.baza_actual.cartas:
        en_mesa = "  ".join(f"J{j}:[{carta_str(c)}]" for j, c in estado.baza_actual.cartas)
        print(f"  Mesa: {en_mesa}")

    # Mano del jugador humano
    mano = estado.manos[JUGADOR_HUMANO]
    mano_str = "  ".join(f"{i+1}.[{carta_str(c)}]" for i, c in enumerate(mano))
    print(f"\n  Tu mano: {mano_str}\n")


# ---------------------------------------------------------------------------
# IA simple: elige la carta más alta jugable; en triunfo prioriza el mínimo
# ---------------------------------------------------------------------------

def ia_elegir_carta(estado: EstadoPartida, jugador: int) -> Carta:
    jugables = cartas_jugables(estado, jugador)
    triunfo = estado.triunfo

    # Si hay opciones que no son triunfo, elige la de mayor rango
    no_triunfo = [c for c in jugables if c.palo != triunfo]
    if no_triunfo:
        return max(no_triunfo, key=lambda c: c.rango(triunfo))

    # Solo triunfo disponible: elige el mínimo para no gastar
    return min(jugables, key=lambda c: c.rango(triunfo))


def ia_elegir_subasta(estado: EstadoPartida, jugador: int):
    """La máquina decide si va o no en la subasta."""
    mano = estado.manos[jugador]
    triunfo_prop = estado.triunfo_propuesto

    # Cuenta puntos y triunfos en la mano
    triunfos = [c for c in mano if c.palo == triunfo_prop]
    puntos = sum(c.puntos for c in mano)

    # Heurística simple: va si tiene ≥3 triunfos o ≥30 puntos en mano
    if len(triunfos) >= 3 or puntos >= 30:
        return "voy", None
    return "no_voy", None


# ---------------------------------------------------------------------------
# Turno humano: subasta
# ---------------------------------------------------------------------------

def turno_humano_subasta(estado: EstadoPartida) -> EstadoPartida:
    mostrar_estado(estado)
    es_segundas = estado.fase == Fase.SUBASTA_SEGUNDAS

    if es_segundas:
        print("  SUBASTA DE SEGUNDAS — puedes proponer un palo distinto al de la carta boca arriba.")
    else:
        print(f"  SUBASTA DE PRIMERAS — carta boca arriba: [{carta_str(estado.carta_mesa)}]")
        print(f"  Triunfo propuesto: {estado.triunfo_propuesto.value}")

    print("  ¿Qué haces?  [v] Voy   [n] No voy")
    while True:
        resp = input("  > ").strip().lower()
        if resp in ("v", "voy"):
            if es_segundas:
                palos = [p for p in Palo if p != estado.triunfo_propuesto]
                print("  Elige palo de triunfo:")
                for i, p in enumerate(palos):
                    print(f"    {i+1}. {p.value}")
                while True:
                    try:
                        idx = int(input("  > ")) - 1
                        palo = palos[idx]
                        break
                    except (ValueError, IndexError):
                        print("  Opción inválida.")
                estado = votar_subasta(estado, JUGADOR_HUMANO, "voy", palo)
            else:
                estado = votar_subasta(estado, JUGADOR_HUMANO, "voy")
            if estado.error:
                print(f"  Error: {estado.error}")
            else:
                print(f"  ¡Vas! Triunfo: {estado.triunfo.value}")
            return estado
        elif resp in ("n", "no_voy", "no"):
            estado = votar_subasta(estado, JUGADOR_HUMANO, "no_voy")
            print("  Pasas.")
            return estado
        else:
            print("  Escribe 'v' para ir o 'n' para pasar.")


# ---------------------------------------------------------------------------
# Turno humano: jugar carta
# ---------------------------------------------------------------------------

def turno_humano_carta(estado: EstadoPartida) -> EstadoPartida:
    mostrar_estado(estado)
    jugables = cartas_jugables(estado, JUGADOR_HUMANO)
    mano = estado.manos[JUGADOR_HUMANO]

    print("  Cartas jugables:", "  ".join(
        f"{mano.index(c)+1}.[{carta_str(c)}]" for c in jugables
    ))

    while True:
        try:
            idx = int(input("  Elige número de carta > ")) - 1
            carta = mano[idx]
            if carta not in jugables:
                print("  No puedes jugar esa carta ahora.")
                continue
            estado = jugar_carta(estado, JUGADOR_HUMANO, carta)
            if estado.error:
                print(f"  Error: {estado.error}")
                continue
            return estado
        except (ValueError, IndexError):
            print("  Número inválido.")


# ---------------------------------------------------------------------------
# Bucle principal
# ---------------------------------------------------------------------------

def jugar_mano(puntos_totales):
    estado = nueva_partida()
    estado.puntos_totales = list(puntos_totales)

    print("\n" + "═" * 60)
    print("  NUEVA MANO")
    print("═" * 60)

    # ── Subasta ──────────────────────────────────────────────
    while estado.fase in (Fase.SUBASTA_PRIMERAS, Fase.SUBASTA_SEGUNDAS):
        j = estado.turno

        if j == JUGADOR_HUMANO:
            estado = turno_humano_subasta(estado)
        else:
            accion, palo = ia_elegir_subasta(estado, j)
            if estado.fase == Fase.SUBASTA_SEGUNDAS and accion == "voy":
                # IA elige el palo con más cartas distinto al propuesto
                mano_ia = estado.manos[j]
                palos_validos = [p for p in Palo if p != estado.triunfo_propuesto]
                palo = max(palos_validos, key=lambda p: sum(1 for c in mano_ia if c.palo == p))
            estado = votar_subasta(estado, j, accion, palo)
            if not estado.error:
                if accion == "voy":
                    print(f"\n  J{j} (máquina) dice: ¡VOY! — triunfo: {estado.triunfo.value}")
                else:
                    print(f"  J{j} (máquina) pasa.")

        if estado.error:
            print(f"  Error inesperado: {estado.error}")
            break

    if estado.fase == Fase.FIN_MANO:
        print("\n  Todos pasaron — mano nula, nadie puntúa.")
        return estado.puntos_totales

    # Quién va
    quien = estado.quien_va
    print(f"\n  {'Tú vas' if quien == JUGADOR_HUMANO else f'J{quien} (máquina) va'} — Triunfo: {estado.triunfo.value}")
    input("  [Enter para empezar a jugar]")

    # ── Bazas ─────────────────────────────────────────────────
    baza_num = 0
    while estado.fase == Fase.BAZAS:
        j = estado.turno

        # Inicio de baza
        if not estado.baza_actual.cartas:
            baza_num += 1
            print(f"\n  ── Baza {baza_num} ──")

        if j == JUGADOR_HUMANO:
            estado = turno_humano_carta(estado)
            if not estado.error:
                carta_jugada = estado.baza_actual.cartas[-1][1] if estado.baza_actual.cartas else estado.bazas_jugadas[-1].cartas[JUGADOR_HUMANO if len(estado.bazas_jugadas[-1].cartas) > JUGADOR_HUMANO else 0][1]
                # Busca la última carta jugada por el humano
                ultima_baza = estado.bazas_jugadas[-1] if estado.baza_actual.cartas == [] else estado.baza_actual
                for jj, cc in ultima_baza.cartas:
                    if jj == JUGADOR_HUMANO:
                        print(f"  Tú juegas: [{carta_str(cc)}]")
                        break
        else:
            carta = ia_elegir_carta(estado, j)
            estado = jugar_carta(estado, j, carta)
            print(f"  J{j} juega: [{carta_str(carta)}]")

        if estado.error:
            print(f"  Error: {estado.error}")
            break

        # Fin de baza
        if estado.baza_actual.cartas == [] and estado.bazas_jugadas:
            ultima = estado.bazas_jugadas[-1]
            eq = equipo_de(ultima.ganador)
            quien_gano = "Tú ganas" if ultima.ganador == JUGADOR_HUMANO else (
                "Tu compañero (J2) gana" if ultima.ganador == 2 else f"J{ultima.ganador} (máquina) gana"
            )
            print(f"  → {quien_gano} la baza  ({ultima.puntos} pts)")

    # ── Fin de mano ──────────────────────────────────────────
    separador()
    print("  FIN DE MANO")
    eq_va = equipo_de(estado.quien_va)
    va_str = "Tú fuiste" if estado.quien_va == JUGADOR_HUMANO else f"J{estado.quien_va} (máquina) fue"
    print(f"  {va_str}  (Eq{eq_va})")
    print(f"  Puntos de cartas → Eq0: {estado.puntos_mano[0]}   Eq1: {estado.puntos_mano[1]}")
    if any(estado.cantes_equipo):
        print(f"  Cantes          → Eq0: {estado.cantes_equipo[0]}   Eq1: {estado.cantes_equipo[1]}")
    if estado.cantes:
        for c in estado.cantes:
            dueno = "tuyo" if c.jugador == JUGADOR_HUMANO else f"J{c.jugador}"
            print(f"    {c.tipo} ({c.puntos}pts) — {dueno}")
    print(f"\n  PUNTOS TOTALES → Eq0 (tú+J2): {estado.puntos_totales[0]}   Eq1 (J1+J3): {estado.puntos_totales[1]}")
    separador()

    return estado.puntos_totales


def main():
    print("=" * 60)
    print("         BOLOT -- Juego de cartas")
    print("   Tu = J0 (Eq0)   Companero = J2 (Eq0)")
    print("   Rivales = J1 y J3 (Eq1)")
    print("=" * 60)

    try:
        objetivo = int(input("¿Objetivo de puntos? [1000 / 1500, Enter=1000]: ").strip() or "1000")
    except ValueError:
        objetivo = 1000

    puntos = [0, 0]

    while puntos[0] < objetivo and puntos[1] < objetivo:
        puntos = jugar_mano(puntos)
        print(f"\n  Marcador: Eq0={puntos[0]}  Eq1={puntos[1]}  (objetivo {objetivo})")
        if puntos[0] >= objetivo or puntos[1] >= objetivo:
            break
        cont = input("  ¿Jugar otra mano? [Enter=sí / q=salir]: ").strip().lower()
        if cont == "q":
            break

    print("\n" + "=" * 60)
    if puntos[0] >= objetivo and puntos[0] > puntos[1]:
        print("  !!GANASTEIS TU Y TU COMPANERO!!")
    elif puntos[1] >= objetivo:
        print("  Gano la maquina (Eq1). Suerte la proxima!")
    else:
        print("  Partida interrumpida.")
    print(f"  Resultado final: Eq0={puntos[0]}  Eq1={puntos[1]}")
    print("=" * 60)


if __name__ == "__main__":
    main()

