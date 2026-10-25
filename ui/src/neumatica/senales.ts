/* Cómo se llaman, para la persona, las señales del aire en el árbol de «Señales» (plan V8.9 D7,
   D12; revisión a ciegas de F6: «bobina14», «posicion» o «pA_bar» crudos son jerga). El nombre de
   la señal sigue a la vista en el `title` y en el multímetro. Puro. */

const ROTULOS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^bobina(\d+)$/, (m) => `Bobina ${m[1]}`],
  [/^posicion$/, () => "Posición"],
  [/^manual$/, () => "A mano"],
  [/^x_mm$/, () => "Carrera"],
  [/^v_m_s$/, () => "Velocidad"],
  [/^pA_bar$/, () => "Presión de avance"],
  [/^pB_bar$/, () => "Presión de retroceso"],
  [/^F_N$/, () => "Fuerza"],
  [/^p_bar$/, () => "Presión"],
  [/^p_red_bar$/, () => "Presión de la red"],
  [/^Q_Nl_min$/, () => "Caudal"],
  [/^consumo_NL$/, () => "Aire consumido"],
  [/^abierta$/, () => "Abierta"],
];

/** El rótulo de una magnitud del aire («Bobina 14», «Presión de avance»), o undefined. */
export function rotuloAire(magnitud: string): string | undefined {
  for (const [re, f] of ROTULOS) {
    const m = magnitud.match(re);
    if (m) return f(m);
  }
  return undefined;
}
