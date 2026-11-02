/**
 * Módulo de baraja para Bolot (frontend mirror del backend)
 *
 * Baraja española recortada: As, 3, 7, 8, 9, Sota, Caballo, Rey
 * 4 palos × 8 cartas = 32 cartas
 */

export const PALOS = ["oros", "copas", "espadas", "bastos"];

export const VALORES = ["as", "tres", "siete", "ocho", "nueve", "sota", "caballo", "rey"];

export const NUMERO_CARTA = {
  as: 1, tres: 3, siete: 7, ocho: 8,
  nueve: 9, sota: 10, caballo: 11, rey: 12,
};

export const PUNTUACION = {
  as: 11, tres: 10, rey: 4,
  caballo: 3, sota: 2, nueve: 0, ocho: 0, siete: 0,
};

// De menor a mayor rango cuando ES triunfo
// 7 < 8 < Caballo < Rey < 3 < As < 9(Catorce) < Sota(Valet)
export const ORDEN_TRIUNFO = ["siete", "ocho", "caballo", "rey", "tres", "as", "nueve", "sota"];

// De menor a mayor rango cuando NO es triunfo
// 7 < 8 < 9 < Sota < Caballo < Rey < 3 < As
export const ORDEN_NO_TRIUNFO = ["siete", "ocho", "nueve", "sota", "caballo", "rey", "tres", "as"];

export const PUNTUACION_TRIUNFO = {
  ...PUNTUACION,
  sota: 20,   // Valet
  nueve: 14,  // Catorce
};

export const PUNTOS_TOTALES = 162; // 152 cartas + 10 últimas

/**
 * @typedef {{ palo: string, valor: string }} Carta
 */

/** Crea las 32 cartas de la baraja ordenadas. */
export function crearBaraja() {
  return PALOS.flatMap(palo =>
    VALORES.map(valor => ({ palo, valor }))
  );
}

/** Baraja un array (Fisher-Yates in-place, devuelve nueva copia). */
export function barajar(cartas) {
  const copia = [...cartas];
  for (let i = copia.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copia[i], copia[j]] = [copia[j], copia[i]];
  }
  return copia;
}

/**
 * Devuelve el rango numérico de una carta en el contexto del triunfo actual.
 * Las cartas de triunfo reciben un offset de 8 para superar siempre a las demás.
 * @param {Carta} carta
 * @param {string|null} triunfo  - palo que es triunfo, o null
 * @returns {number}
 */
export function rango(carta, triunfo = null) {
  if (triunfo !== null && carta.palo === triunfo) {
    return 8 + ORDEN_TRIUNFO.indexOf(carta.valor);
  }
  return ORDEN_NO_TRIUNFO.indexOf(carta.valor);
}

/**
 * Determina qué carta gana entre dos.
 * @param {Carta} cartaA - carta que lleva ventaja (la jugada primero)
 * @param {Carta} cartaB - carta retadora
 * @param {string|null} triunfo
 * @returns {Carta}
 */
export function cartaGanadora(cartaA, cartaB, triunfo = null) {
  if (cartaA.palo === cartaB.palo) {
    return rango(cartaA, triunfo) >= rango(cartaB, triunfo) ? cartaA : cartaB;
  }
  if (triunfo !== null && cartaB.palo === triunfo) return cartaB;
  return cartaA;
}

/** Etiqueta legible para mostrar en UI. */
export function etiqueta(carta) {
  const nombre = carta.valor.charAt(0).toUpperCase() + carta.valor.slice(1);
  const palo = carta.palo.charAt(0).toUpperCase() + carta.palo.slice(1);
  return `${nombre} de ${palo}`;
}

/** Puntos de una carta. */
export function puntos(carta) {
  return PUNTUACION[carta.valor] ?? 0;
}

