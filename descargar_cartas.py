"""
Descarga las imágenes de la baraja española desde Wikimedia Commons.
Las guarda en frontend/public/cards/
"""

import os
import time
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

CARDS_DIR = Path(__file__).parent / "frontend" / "public" / "cards"
CARDS_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://commons.wikimedia.org/wiki/Special:FilePath/"

session = requests.Session()
session.headers.update({"User-Agent": "BolotGame/1.0"})

# Mapa: (palo, valor) -> nombre del archivo que queremos guardar localmente
# Intentamos varias convenciones de nombre en orden

PALOS   = ["oros", "copas", "espadas", "bastos"]
VALORES = ["as", "tres", "siete", "ocho", "nueve", "sota", "caballo", "rey"]
NUMS    = {"as": 1, "tres": 3, "siete": 7, "ocho": 8, "nueve": 9, "sota": 10, "caballo": 11, "rey": 12}

def candidatos(palo, valor):
    """Devuelve candidatos de nombre de archivo de Wikimedia a probar."""
    n = NUMS[valor]
    p = palo
    P = palo.capitalize()
    cands = []

    if valor == "as":
        cands += [f"Asde{p}.png", f"Asde{P}.png", f"As_de_{p}.png",
                  f"1de{p}.png", f"1{p}.png"]
    elif valor == "sota":
        cands += [f"S{p}.png", f"S{P}.png", f"Sota_de_{p}.png",
                  f"sota_{p}.png", f"{n}de{p}.png", f"{n}{p}.png"]
    elif valor == "caballo":
        cands += [f"C{p}.png", f"C{P}.png", f"Caballo_de_{p}.png",
                  f"{n}de{p}.png", f"{n}{p}.png"]
    elif valor == "rey":
        cands += [f"R{p}.png", f"R{P}.png", f"Rey_de_{p}.png",
                  f"{n}de{p}.png", f"{n}{p}.png"]
    else:
        cands += [f"{n}de{p}.png", f"{n}{p}.png", f"{n}De{P}.png",
                  f"{n}_{p}.png"]

    return cands

ok = 0
fail = 0

print(f"Descargando cartas en: {CARDS_DIR}\n")

for palo in PALOS:
    for valor in VALORES:
        dest_name = f"{palo}_{NUMS[valor]}.png"
        dest = CARDS_DIR / dest_name

        if dest.exists():
            print(f"  [ya existe] {dest_name}")
            ok += 1
            continue

        descargado = False
        for fname in candidatos(palo, valor):
            url = BASE + fname
            try:
                r = session.get(url, timeout=20, allow_redirects=True)
                ctype = r.headers.get("content-type", "")
                if r.status_code == 200 and "image" in ctype:
                    dest.write_bytes(r.content)
                    print(f"  [OK] {dest_name}  <-  {fname}")
                    ok += 1
                    descargado = True
                    time.sleep(0.2)
                    break
            except Exception as e:
                print(f"  [EXC] {fname}: {e}")
            time.sleep(0.1)

        if not descargado:
            print(f"  [FALLO] {palo} {valor} — ningún candidato funcionó")
            fail += 1

print(f"\nResultado: {ok} OK, {fail} fallidos")
if fail > 0:
    print("Puedes seguir jugando sin imágenes — las cartas usan texto como fallback.")
else:
    print("Todas las imágenes descargadas. Ejecuta el frontend con: cd frontend && npm run dev")

