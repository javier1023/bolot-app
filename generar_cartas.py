"""
Genera las 32 cartas de la baraja española recortada en formato SVG.
Guarda los archivos en frontend/public/cards/
"""

from pathlib import Path

CARDS_DIR = Path(__file__).parent / "frontend" / "public" / "cards"
CARDS_DIR.mkdir(parents=True, exist_ok=True)

PALOS = ["oros", "copas", "espadas", "bastos"]
VALORES = {
    "as": ("A", 1), "tres": ("3", 3), "siete": ("7", 7), "ocho": ("8", 8),
    "nueve": ("9", 9), "sota": ("J", 10), "caballo": ("C", 11), "rey": ("R", 12),
}

COLORES = {
    "oros":    {"fill": "#B8860B", "light": "#FFD700", "bg": "#FFFDE7"},
    "copas":   {"fill": "#8B0000", "light": "#E53935", "bg": "#FFF0F0"},
    "espadas": {"fill": "#1A237E", "light": "#3949AB", "bg": "#F0F0FF"},
    "bastos":  {"fill": "#1B5E20", "light": "#388E3C", "bg": "#F0FFF0"},
}

# Símbolos SVG para cada palo (paths centrados en 0,0)
SIMBOLOS = {
    "oros": """
      <circle cx="0" cy="0" r="22" fill="{light}" stroke="{fill}" stroke-width="3.5"/>
      <circle cx="0" cy="0" r="13" fill="{fill}" opacity="0.25"/>
      <circle cx="0" cy="0" r="6" fill="{fill}" opacity="0.5"/>
    """,
    "copas": """
      <path d="M0,-22 C-18,-22 -26,-8 -20,4 C-14,16 -6,20 0,28
               C6,20 14,16 20,4 C26,-8 18,-22 0,-22 Z"
            fill="{light}" stroke="{fill}" stroke-width="2.5"/>
      <rect x="-5" y="28" width="10" height="10" rx="2" fill="{fill}" opacity="0.5"/>
      <rect x="-12" y="38" width="24" height="5" rx="2.5" fill="{fill}" opacity="0.4"/>
    """,
    "espadas": """
      <line x1="0" y1="-28" x2="0" y2="28" stroke="{fill}" stroke-width="4" stroke-linecap="round"/>
      <line x1="-16" y1="-6" x2="16" y2="-6" stroke="{fill}" stroke-width="3.5" stroke-linecap="round"/>
      <line x1="-10" y1="4" x2="10" y2="4" stroke="{fill}" stroke-width="2.5" stroke-linecap="round"/>
      <polygon points="0,-28 -7,-14 7,-14" fill="{light}" stroke="{fill}" stroke-width="1.5"/>
    """,
    "bastos": """
      <line x1="0" y1="-26" x2="0" y2="26" stroke="{fill}" stroke-width="6" stroke-linecap="round"/>
      <circle cx="-10" cy="-10" r="7" fill="{light}" stroke="{fill}" stroke-width="2.5"/>
      <circle cx="10" cy="-10" r="7" fill="{light}" stroke="{fill}" stroke-width="2.5"/>
      <circle cx="0" cy="6" r="7" fill="{light}" stroke="{fill}" stroke-width="2.5"/>
    """,
}

NOMBRES_PALO = {"oros": "Oros", "copas": "Copas", "espadas": "Espadas", "bastos": "Bastos"}

def simbolo_svg(palo, x, y, escala=1.0):
    c = COLORES[palo]
    s = SIMBOLOS[palo].format(**c)
    return f'<g transform="translate({x},{y}) scale({escala})">{s}</g>'

def card_svg(palo, valor):
    lbl, num = VALORES[valor]
    c = COLORES[palo]
    nombre = NOMBRES_PALO[palo]
    bg = c["bg"]
    fill = c["fill"]
    light = c["light"]

    # Puntos de la carta (para badge)
    PTS = {"as": 11, "tres": 10, "sota": 2, "caballo": 3, "rey": 4}
    pts = PTS.get(valor, 0)

    # Símbolo central (grande) y dos esquinas (pequeños)
    sym_center = simbolo_svg(palo, 60, 88, escala=1.05)
    sym_tl = simbolo_svg(palo, 18, 36, escala=0.45)
    sym_br = simbolo_svg(palo, 102, 140, escala=0.45)

    pts_badge = ""
    if pts > 0:
        pts_badge = f'''
      <rect x="86" y="148" width="24" height="14" rx="4" fill="rgba(0,0,0,0.55)"/>
      <text x="98" y="159" font-family="Arial,sans-serif" font-size="9"
            font-weight="bold" fill="{light}" text-anchor="middle">{pts}pts</text>'''

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 168" width="120" height="168">
  <!-- Fondo -->
  <defs>
    <linearGradient id="bg{palo}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="white"/>
      <stop offset="100%" stop-color="{bg}"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="116" height="164" rx="9" ry="9"
        fill="url(#bg{palo})" stroke="{fill}" stroke-width="2.5"/>

  <!-- Línea decorativa interior -->
  <rect x="5" y="5" width="110" height="158" rx="7" ry="7"
        fill="none" stroke="{fill}" stroke-width="0.8" opacity="0.3"/>

  <!-- Valor esquina superior izquierda -->
  <text x="10" y="22" font-family="Georgia,serif" font-size="19"
        font-weight="bold" fill="{fill}">{lbl}</text>

  <!-- Símbolo esquina superior izquierda -->
  {sym_tl}

  <!-- Nombre del palo (pequeño) -->
  <text x="10" y="54" font-family="Arial,sans-serif" font-size="7"
        fill="{fill}" opacity="0.6">{nombre}</text>

  <!-- Símbolo central grande -->
  {sym_center}

  <!-- Valor esquina inferior derecha (rotado) -->
  <g transform="rotate(180,60,84)">
    <text x="110" y="82" font-family="Georgia,serif" font-size="19"
          font-weight="bold" fill="{fill}" text-anchor="end">{lbl}</text>
  </g>

  <!-- Símbolo esquina inferior derecha -->
  {sym_br}

  <!-- Badge de puntos -->
  {pts_badge}
</svg>'''
    return svg


def card_back_svg():
    return '''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 168" width="120" height="168">
  <defs>
    <linearGradient id="bgback" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#1a3a6e"/>
      <stop offset="100%" stop-color="#0d1f40"/>
    </linearGradient>
    <pattern id="dots" x="0" y="0" width="12" height="12" patternUnits="userSpaceOnUse">
      <circle cx="6" cy="6" r="2" fill="rgba(255,255,255,0.08)"/>
    </pattern>
  </defs>
  <rect x="2" y="2" width="116" height="164" rx="9" ry="9" fill="url(#bgback)"/>
  <rect x="2" y="2" width="116" height="164" rx="9" ry="9" fill="url(#dots)"/>
  <rect x="7" y="7" width="106" height="154" rx="6" ry="6"
        fill="none" stroke="rgba(255,215,0,0.4)" stroke-width="1.5"/>
  <text x="60" y="90" font-family="Georgia,serif" font-size="38"
        text-anchor="middle" dominant-baseline="middle"
        fill="rgba(255,215,0,0.25)">B</text>
</svg>'''


# Generar todas las cartas
print("Generando cartas SVG...\n")
count = 0
for palo in PALOS:
    for valor in VALORES:
        num = VALORES[valor][1]
        filename = f"{palo}_{num}.svg"
        dest = CARDS_DIR / filename
        dest.write_text(card_svg(palo, valor), encoding="utf-8")
        print(f"  [OK] {filename}")
        count += 1

# Dorso
(CARDS_DIR / "dorso.svg").write_text(card_back_svg(), encoding="utf-8")
print(f"  [OK] dorso.svg")

print(f"\n{count} cartas + dorso generados en {CARDS_DIR}")

