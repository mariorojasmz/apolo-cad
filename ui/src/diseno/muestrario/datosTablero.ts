import type { ConductorTablero, ItemTablero, PanelTableroOut } from "../../tablero/tipos";

/* Datos de EJEMPLO del panel «Tablero» (plan V8.5 F3b) con la forma exacta de
   `GET /api/tablero/{ubicacion}`, para el muestrario (revisión a ciegas, D14) y los tests de
   `tablero/`. Las cifras imitan la faja piloto (TABLERO-5040, 12 aparatos, 33 conductores); las
   piezas son las del visor de ejemplo (`VueloDemo.tsx`: mm de su mundo, la puerta en −Y). */

const PIEZA = { canaletaArriba: "canaleta-h", canaletaAbajo: "canaleta-b", puerta: "puerta", gabinete: "fondo",
  variador: "variador", prensa: "prensaestopas", seta: "seta" } as const;
const aparato = (i: number) => `aparato-${i}`;

/** Un conductor de ejemplo: del borne de arriba de un aparato de la fila, por la canaleta de
   arriba, hasta el variador (en la columna de la izquierda). */
function conductor(id: string, puntos: string[], i: number, largo: number, extra: Partial<ConductorTablero> = {}): ConductorTablero {
  const x = -150 + i * 60;
  const recorrido = [[
    [x, 40, 452], [x, 58, 520], [-210, 58, 520], [-210, 58, 300], [-170, 40, 300],
  ]];
  return { id, puntos, largo_m: largo, origen: "ruteo", ruteado_m: largo, piezas: [aparato(i), PIEZA.variador], recorrido, ...extra };
}

const CONDUCTORES: ConductorTablero[] = [
  conductor("c26", ["-F1:2", "-T2:L1"], 1, 0.5, { origen: "declarado", ruteado_m: 0.491, declarado_m: 0.5 }),
  conductor("c27", ["-F1:4", "-T2:L2"], 1, 0.474),
  conductor("c28", ["-F1:6", "-T2:L3"], 1, 0.457),
  conductor("c33", ["-Q1:2", "-F1:1", "-F2:1"], 0, 0.6, { origen: "declarado", ruteado_m: 1.53, declarado_m: 0.6 }),
  conductor("c39", ["-F2:2", "-T1:L"], 2, 0.4, { origen: "declarado", ruteado_m: 0.53, declarado_m: 0.4 }),
  conductor("c40", ["-F2:4", "-T1:N"], 2, 0.4, { origen: "declarado", ruteado_m: 0.55, declarado_m: 0.4 }),
  conductor("c41", ["-T1:L+", "-K1:L+", "-S1:13", "-S2:11", "-H1:X1"], 3, 1.5,
    { origen: "declarado", ruteado_m: 3.07, declarado_m: 1.5 }),
  conductor("c42", ["-T1:M", "-K1:M", "-H1:X2", "-H2:X2"], 3, 1.5, { origen: "declarado", ruteado_m: 2.71, declarado_m: 1.5 }),
  conductor("c51", ["-T2:RA", "-K1:I0.4"], 4, 0.481),
  conductor("c52", ["-K1:Q0.0", "-T2:DI1"], 4, 0.521),
  conductor("c22", ["-G1:L1", "-Q1:1"], 0, 2, { origen: "declarado", ruteado_m: 1.036, declarado_m: 2, sale: true,
    piezas: [aparato(0), PIEZA.prensa], recorrido: [[[-150, 40, 452], [-150, 58, 520], [210, 58, 520], [210, 58, 80], [262, 0, 70]]] }),
  conductor("c53", ["-K1:Q0.3", "-T2:DI3"], 5, 0.526),
];

const it = (p: Partial<ItemTablero> & Pick<ItemTablero, "clave" | "severidad" | "frase">): ItemTablero =>
  ({ piezas: [], conductores: [], ...p });

const CALOR = it({ clave: "calentamiento", severidad: "sin_evaluar", frase: "Falta evaluar el calentamiento",
  piezas: [PIEZA.gabinete],
  detalle: "Para calcularlo hacen falta las curvas de la norma IEC/TR 60890; mientras no estén, no damos una cifra estimada." });

const BIEN: ItemTablero[] = [
  it({ clave: "puerta", severidad: "bien", frase: "La puerta abre sin chocar", valor: 110, unidad: "°", piezas: [PIEZA.puerta],
    detalle: "Revisamos 111 ángulos de su recorrido." }),
  it({ clave: "largo", severidad: "bien", frase: "Conductores dentro del tablero", valor: 28.3, unidad: "m", decimales: 1,
    detalle: "33 conductores con su recorrido por las canaletas." }),
];

const DETALLE = {
  aparatos: [
    { designacion: "-Q1", ref: "SECC-25A-3P", nombre: "Seccionador rotativo 3P 25 A", zona: "puerta", fila: "puerta", pieza: PIEZA.seta },
    { designacion: "-F1", ref: "ITM-C16-3P", nombre: "ITM 3P C16", zona: "placa", fila: "alimentacion", pieza: aparato(1) },
    { designacion: "-F2", ref: "ITM-C2-2P", nombre: "ITM 2P C2", zona: "placa", fila: "alimentacion", pieza: aparato(2) },
    { designacion: "-T1", ref: "FUENTE-24VDC-5A", nombre: "Fuente 24 VDC 5 A", zona: "placa", fila: "control", pieza: aparato(3) },
    { designacion: "-K1", ref: "PLC-14DI-10DO-24VDC", nombre: "PLC 14 DI / 10 DO 24 VDC", zona: "placa", fila: "control", pieza: aparato(4) },
    { designacion: "-T2", ref: "VFD-2K2-220", nombre: "Variador 2.2 kW 220V 3F", zona: "placa", fila: "columna", pieza: PIEZA.variador },
  ],
  conductores: CONDUCTORES,
  calentamiento: { estado: "sin_evaluar" as const, motivo: CALOR.detalle!, perdidas_W: 128, sin_dato: ["-S1", "-S2", "-S0", "-X0"] },
  supuestos: ["Ø de un hilo de cable = el del conductor suelto de su sección"],
};

const BASE = {
  ubicacion: "+TAB1", comando: "c55", armado: true,
  gabinete: { ref: "TABLERO-5040", nombre: "Tablero de control 500x400x200", pieza: PIEZA.gabinete, medidas_mm: [500, 200, 400] },
  puerta: { junta: "c55_puerta", pieza: PIEZA.puerta, min_deg: 0, max_deg: 110, bisagra: "izquierda" },
};

const NOTA = "Gabinete de 500 × 400 mm · 12 aparatos · 33 conductores";

/** Con cosas por atender: una canaleta que no da, otra llena, largos a mano y un conductor suelto. */
export const PANEL_CON_FALLAS: PanelTableroOut = {
  ...BASE,
  veredicto: { severidad: "falla", frase: "1 cosa por corregir y 3 por revisar", nota: NOTA },
  items: [
    it({ clave: "canaleta-1", severidad: "falla", frase: "Los conductores no entran en la canaleta de abajo", valor: 112,
      unidad: "%", piezas: [PIEZA.canaletaAbajo], conductores: ["c41", "c42", "c51", "c52", "c53"],
      detalle: "847 de 756 mm² con 21 conductores; el tope es 50 %." }),
    it({ clave: "canaleta-0", severidad: "aviso", frase: "La canaleta de arriba va muy llena", valor: 64, unidad: "%",
      piezas: [PIEZA.canaletaArriba], conductores: ["c26", "c27", "c28", "c33"],
      detalle: "484 de 756 mm² con 12 conductores; el tope es 50 %." }),
    it({ clave: "largos", severidad: "aviso", frase: "Hay largos escritos a mano que no cuadran con el recorrido", valor: 6,
      unidad: "conductores", piezas: [aparato(0), aparato(1), aparato(2), aparato(3), PIEZA.variador],
      conductores: ["c26", "c33", "c39", "c40", "c41", "c42"],
      detalle: "La BOM compra el largo escrito a mano. Si nadie lo midió, pídele al agente que lo quite." }),
    it({ clave: "sin-cable", severidad: "aviso", frase: "Hay conductores que salen del tablero sin cable", valor: 1,
      unidad: "conductor", piezas: [aparato(0), PIEZA.prensa], conductores: ["c22"],
      detalle: "Afuera del tablero un conductor suelto no está protegido: pídele al agente que lo lleve dentro de un cable." }),
    CALOR,
  ],
  detalle: {
    ...DETALLE,
    bien: BIEN,
    canaletas: [
      { nombre: "Canaleta de arriba", pieza: PIEZA.canaletaArriba, orientacion: "h", llenado: 0.64, ocupado_mm2: 484, util_mm2: 756, conductores: 12 },
      { nombre: "Canaleta de abajo", pieza: PIEZA.canaletaAbajo, orientacion: "h", llenado: 1.12, ocupado_mm2: 847, util_mm2: 756, conductores: 21 },
    ],
  },
};

/** Sin fallas: sólo el calentamiento queda sin evaluar (F3 espera la norma). */
export const PANEL_EN_ORDEN: PanelTableroOut = {
  ...BASE,
  veredicto: { severidad: "sin_evaluar", frase: "1 cosa sin evaluar", nota: NOTA },
  items: [CALOR],
  detalle: {
    ...DETALLE,
    conductores: CONDUCTORES.map((c) => ({ ...c, origen: "ruteo" as const, largo_m: c.ruteado_m, declarado_m: undefined, sale: undefined })),
    bien: [...BIEN, it({ clave: "canaletas", severidad: "bien", frase: "La canaleta más llena", valor: 13, unidad: "%",
      piezas: [PIEZA.canaletaArriba], detalle: "Es la canaleta de arriba; el tope es 50 %." })],
    canaletas: [
      { nombre: "Canaleta de arriba", pieza: PIEZA.canaletaArriba, orientacion: "h", llenado: 0.135, ocupado_mm2: 102, util_mm2: 756, conductores: 12 },
      { nombre: "Canaleta de abajo", pieza: PIEZA.canaletaAbajo, orientacion: "h", llenado: 0.036, ocupado_mm2: 27, util_mm2: 756, conductores: 2 },
    ],
  },
};

/** Un tablero que una carga tolerante no pudo armar. */
export const PANEL_SIN_ARMAR: PanelTableroOut = {
  ubicacion: "+TAB1", comando: "c55", armado: false,
  veredicto: { severidad: "falla", frase: "1 cosa por corregir" },
  items: [it({ clave: "armado", severidad: "falla", frase: "El tablero no se pudo armar",
    detalle: "Pídele al agente que revise el armado del tablero.",
    tecnico: "Tablero +TAB1: en el TABLERO-5040 no entra: faltan 168 mm de alto; con «auto» entra en el GAB-6040." })],
};
