import type {
  AparatoTablero, CableTablero, CalentamientoTablero, ConductorTablero, ItemTablero, PanelTableroOut,
} from "../../tablero/tipos";

/* Datos de EJEMPLO del panel «Tablero» (plan V8.5 F3b) con la forma exacta de
   `GET /api/tablero/{ubicacion}`, para el muestrario (revisión a ciegas, D14) y los tests de
   `tablero/`. Las cifras imitan la faja piloto (TABLERO-5040), recortada a 6 aparatos y 12
   conductores (y dos cables de campo, F4b) para que el ejemplo sea coherente consigo mismo; las piezas son las del visor de ejemplo (`VueloDemo.tsx`: mm de su mundo, la puerta en −Y). */

const PIEZA = { canaletaArriba: "canaleta-h", canaletaAbajo: "canaleta-b", puerta: "puerta", gabinete: "fondo",
  variador: "variador", prensa: "prensaestopas", seta: "seta" } as const;
const aparato = (i: number) => `aparato-${i}`;
/** Lo que gira junto al larguero del visor de ejemplo. */
const PIEZA_TAMBOR = "tambor";

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

/** El largo de una polilínea (m). */
const largoDe = (pts: number[][]) => pts.slice(1).reduce((s, p, i) => s + Math.hypot(...p.map((x, k) => x - pts[i][k])), 0) / 1000;

/** Un cable de campo de ejemplo (F4b): sale por el prensaestopas del lateral derecho, baja por la
   pata, corre por el larguero y llega a su aparato (la estructura del visor de ejemplo). */
function cable(id: string, designacion: string, ref: string, nombre: string, adentro: number, puntos: number[][],
  extra: Partial<CableTablero> = {}): CableTablero {
  const afuera = Math.round(largoDe(puntos) * 1000) / 1000;
  const reserva = 0.3;
  return { id, designacion, ref, nombre, calculado: true, largo_m: Math.round((adentro + afuera + reserva) * 1000) / 1000,
    partes_m: { adentro, afuera, reserva }, piezas: [], recorrido: [puntos], ...extra };
}

/** -W1, al motor: sano (a más de 10 mm de lo que gira). */
const W1 = cable("c19", "-W1", "CABLE-4G2.5", "Cable flexible 4G2,5", 0.379, [
  [246, -30, 70], [300, -30, 70], [670, -30, 80], [670, -30, 880], [700, -25, 900], [2650, -25, 900], [2700, -200, 950],
]);

/** -W2, al sensor del tambor: pasa sobre el tambor a 4 mm de su cara. */
const W2 = cable("c20", "-W2", "CABLE-3X0.75", "Cable de sensor 3x0,75", 0.412, [
  [246, -10, 70], [300, -10, 70], [670, -10, 80], [670, 25, 880], [700, 25, 1000], [2650, 25, 1000],
  [2690, 25, 1016.5], [2810, 25, 1016.5], [2850, 25, 1016.5],
], { piezas: [PIEZA_TAMBOR] });

const it = (p: Partial<ItemTablero> & Pick<ItemTablero, "clave" | "severidad" | "frase">): ItemTablero =>
  ({ piezas: [], conductores: [], ...p });

/** El calentamiento de la piloto (V8.5 F3): 157 W en la caja de 500 × 400 sin ventilar. */
const CALOR = it({ clave: "calentamiento", severidad: "falla", frase: "El tablero se calienta de más",
  valor: 98, unidad: "°C", piezas: [PIEZA.gabinete, PIEZA.variador],
  detalle: "Arriba llega a 98 °C y Interruptor general (-Q1) admite 50 °C. Ventílalo con al menos 33 m³/h.",
  tecnico: "+TAB1 pierde 156.9 W en Ae = 0.564 m²: el aire llega a 90 °C a media altura y 98 °C arriba (ambiente 35 °C)." });

const CALOR_DETALLE = {
  estado: "falla" as const, perdidas_W: 156.9, perdidas: { aparatos_W: 128, conductores_W: 28.9 },
  sin_dato: ["-S1", "-S2", "-S0", "-X0"], ambiente_C: 35, T_media_C: 89.9, T_arriba_C: 98.5,
  peor: { designacion: "-Q1", T_C: 98.5, T_max_C: 50 }, sugerencia: { caudal_m3h: 32.7 },
};

/** Con el ventilador de 33 m³/h declarado: cumple. */
const CALOR_VENTILADO = {
  estado: "bien" as const, perdidas_W: 156.9, perdidas: { aparatos_W: 128, conductores_W: 28.9 },
  sin_dato: ["-S1", "-S2", "-S0", "-X0"], ambiente_C: 35, T_media_C: 49.6, T_arriba_C: 49.6,
  ventilacion_m3h: 33, peor: { designacion: "-Q1", T_C: 49.6, T_max_C: 50 },
};

const PRENSAS = {
  cara: "inferior",
  prensas: [
    { cable: "c19", designacion: "-W1", diametro_mm: 9.8, ref: "PRENSA-M16", rosca: "M16x1,5", nombre: "Prensaestopas M16×1,5 (cable Ø4–10)" },
    { cable: "c20", designacion: "-W2", diametro_mm: 6, ref: "PRENSA-M16", rosca: "M16x1,5", nombre: "Prensaestopas M16×1,5 (cable Ø4–10)" },
  ],
};

/** Lo que miden los conductores del ejemplo dentro del tablero (m). */
const TOTAL_M = CONDUCTORES.reduce((s, c) => s + c.ruteado_m, 0);

const BIEN: ItemTablero[] = [
  it({ clave: "puerta", severidad: "bien", frase: "La puerta abre sin chocar", valor: 110, unidad: "°", piezas: [PIEZA.puerta],
    detalle: "Revisamos 111 ángulos de su recorrido." }),
  it({ clave: "largo", severidad: "bien", frase: "Conductores dentro del tablero", valor: Math.round(TOTAL_M * 10) / 10,
    unidad: "m", decimales: 1, detalle: `${CONDUCTORES.length} conductores con su recorrido por las canaletas.` }),
];

const DETALLE = {
  // la piloto no declara rótulos: los da su tipo (`services/nombres_aparatos.py`, origen «tipo»)
  aparatos: [
    { designacion: "-Q1", ref: "SECC-25A-3P", nombre: "Seccionador rotativo 3P 25 A", zona: "puerta", fila: "puerta", pieza: PIEZA.seta,
      rotulo: "Interruptor general", origen: "tipo" },
    { designacion: "-F1", ref: "ITM-C16-3P", nombre: "ITM 3P C16", zona: "placa", fila: "alimentacion", pieza: aparato(1),
      rotulo: "Interruptor automático", origen: "tipo" },
    { designacion: "-F2", ref: "ITM-C2-2P", nombre: "ITM 2P C2", zona: "placa", fila: "alimentacion", pieza: aparato(2),
      rotulo: "Interruptor automático", origen: "tipo" },
    { designacion: "-T1", ref: "FUENTE-24VDC-5A", nombre: "Fuente 24 VDC 5 A", zona: "placa", fila: "control", pieza: aparato(3),
      rotulo: "Fuente", origen: "tipo" },
    { designacion: "-K1", ref: "PLC-14DI-10DO-24VDC", nombre: "PLC 14 DI / 10 DO 24 VDC", zona: "placa", fila: "control", pieza: aparato(4),
      rotulo: "PLC", origen: "tipo" },
    { designacion: "-T2", ref: "VFD-2K2-220", nombre: "Variador 2.2 kW 220V 3F", zona: "placa", fila: "columna", pieza: PIEZA.variador,
      rotulo: "Variador", origen: "tipo" },
  ],
  conductores: CONDUCTORES,
  calentamiento: CALOR_DETALLE as CalentamientoTablero,
  prensaestopas: PRENSAS,
  supuestos: ["Ø de un hilo de cable = el del conductor suelto de su sección"],
};

const BASE = {
  ubicacion: "+TAB1", comando: "c55", armado: true,
  gabinete: { ref: "TABLERO-5040", nombre: "Tablero de control 500x400x200", pieza: PIEZA.gabinete, medidas_mm: [500, 200, 400] },
  puerta: { junta: "c55_puerta", pieza: PIEZA.puerta, min_deg: 0, max_deg: 110, bisagra: "izquierda" },
};

const NOTA = "Caja de 500 × 400 mm · 6 aparatos · 12 conductores";

/** Con cosas por atender: una canaleta que no da, otra llena, largos a mano y un conductor suelto. */
export const PANEL_CON_FALLAS: PanelTableroOut = {
  ...BASE,
  veredicto: { severidad: "falla", frase: "2 cosas por corregir y 4 por revisar", nota: NOTA },
  items: [
    it({ clave: "canaleta-1", severidad: "falla", frase: "Los conductores no entran en la canaleta de abajo", valor: 112,
      unidad: "%", piezas: [PIEZA.canaletaAbajo], conductores: ["c41", "c42", "c51", "c52", "c53"],
      detalle: "847 de 756 mm² con 5 conductores; el tope es 50 %." }),
    CALOR,
    it({ clave: "canaleta-0", severidad: "aviso", frase: "La canaleta de arriba va muy llena", valor: 64, unidad: "%",
      piezas: [PIEZA.canaletaArriba], conductores: ["c26", "c27", "c28", "c33"],
      detalle: "484 de 756 mm² con 4 conductores; el tope es 50 %." }),
    it({ clave: "largos", severidad: "aviso", frase: "Conductores con un largo puesto a mano que no cuadra con su recorrido",
      valor: 6, piezas: [aparato(0), aparato(1), aparato(2), aparato(3), PIEZA.variador],
      conductores: ["c26", "c33", "c39", "c40", "c41", "c42"],
      detalle: "La BOM compra el largo puesto a mano. Si nadie lo midió, pídele al agente que lo quite." }),
    it({ clave: "sin-cable", severidad: "aviso", frase: "Conductor que sale del tablero sin ir dentro de un cable", valor: 1,
      piezas: [aparato(0), PIEZA.prensa], conductores: ["c22"],
      detalle: "Afuera del tablero un conductor suelto no está protegido: pídele al agente que lo lleve dentro de un cable." }),
    it({ clave: "cable-giro-c20", severidad: "aviso", frase: "El cable -W2 pasa muy cerca de una pieza que gira", valor: 4,
      unidad: "mm", piezas: [PIEZA_TAMBOR], conductores: [W2.id],
      detalle: "Pasa a 4 mm de «Tambor motriz»; pedimos al menos 10 mm. Pídele al agente que lo lleve por la estructura, lejos de lo que gira.",
      tecnico: "-W2 (CABLE-3X0.75, Ø5) pasa a 4 mm de «Tambor motriz» (tambor), que gira o se mueve, en el tramo 7 de su recorrido; la holgura mínima es 10 mm." }),
  ],
  detalle: {
    ...DETALLE,
    cables: [W1, W2],
    bien: BIEN,
    canaletas: [
      { nombre: "Canaleta de arriba", pieza: PIEZA.canaletaArriba, orientacion: "h", llenado: 0.64, ocupado_mm2: 484, util_mm2: 756, conductores: 4 },
      { nombre: "Canaleta de abajo", pieza: PIEZA.canaletaAbajo, orientacion: "h", llenado: 1.12, ocupado_mm2: 847, util_mm2: 756, conductores: 5 },
    ],
  },
};

/** Sin fallas: con el ventilador declarado, el calentamiento también cumple (F3). */
export const PANEL_EN_ORDEN: PanelTableroOut = {
  ...BASE,
  veredicto: { severidad: "bien", frase: "El tablero cumple", nota: NOTA },
  items: [],
  detalle: {
    ...DETALLE,
    calentamiento: CALOR_VENTILADO as CalentamientoTablero,
    conductores: CONDUCTORES.map((c) => ({ ...c, origen: "ruteo" as const, largo_m: c.ruteado_m, declarado_m: undefined, sale: undefined })),
    cables: [W1],
    bien: [...BIEN, it({ clave: "canaletas", severidad: "bien", frase: "La canaleta más llena", valor: 13, unidad: "%",
      piezas: [PIEZA.canaletaArriba], detalle: "Es la canaleta de arriba; el tope es 50 %." }),
    it({ clave: "cables-giro", severidad: "bien", frase: "Los cables de campo no tocan lo que gira", conductores: [W1.id],
      detalle: "Ninguno pasa a menos de 10 mm de una pieza que gira." }),
    it({ clave: "calentamiento", severidad: "bien", frase: "Temperatura arriba en el tablero", valor: 50, unidad: "°C",
      piezas: [PIEZA.gabinete], detalle: "El más justo es Interruptor general (-Q1): 50 de 50 °C admisibles." }),
    it({ clave: "prensaestopas", severidad: "bien", frase: "Prensaestopas", valor: 2, piezas: [PIEZA.gabinete],
      detalle: "Uno por cable que sale, en la cara de abajo: 2 M16." })],
    canaletas: [
      { nombre: "Canaleta de arriba", pieza: PIEZA.canaletaArriba, orientacion: "h", llenado: 0.135, ocupado_mm2: 102, util_mm2: 756, conductores: 12 },
      { nombre: "Canaleta de abajo", pieza: PIEZA.canaletaAbajo, orientacion: "h", llenado: 0.036, ocupado_mm2: 27, util_mm2: 756, conductores: 2 },
    ],
  },
};

/** «Aparatos» del tablero de la mezcladora de paletas (plan nombres-por-funcion F4, informe § 3.3):
   lo que hace cada uno como lo suma `services/tablero_panel.py` (rótulo declarado, derivado de lo
   que vigila un relé de seguridad o el de su tipo si es único), con su designación y su catálogo. */
const ap = (designacion: string, ref: string, nombre: string, rotulo: string, origen = "declarado", zona = "puerta"): AparatoTablero =>
  ({ designacion, ref, nombre, rotulo, origen, zona, fila: zona, pieza: `c400_d_${designacion}` });
export const APARATOS_MEZCLADORA: AparatoTablero[] = [
  ap("-Q1", "SECC-3P-25A", "Seccionador rotativo 3P 25 A", "Interruptor general", "tipo"),
  ap("-S0", "ESTOP-40-2NC", "Seta de emergencia Ø40 2NC", "Parada de emergencia", "tipo"),
  ap("-S1", "PULS-22-VERDE-NA", "Pulsador Ø22 verde 1NA", "Marcha"),
  ap("-S2", "PULS-22-ROJO-NC", "Pulsador Ø22 rojo 1NC", "Paro"),
  ap("-S3", "PULS-22-AZUL-NA", "Pulsador Ø22 azul 1NA", "Rearme de seguridad"),
  ap("-S4", "SEL-22-2P", "Selector Ø22 2 posiciones", "Modo"),
  ap("-P1", "PIL-22-VERDE", "Piloto LED Ø22 verde 24 V", "Marcha"),
  ap("-P2", "PIL-22-ROJO", "Piloto LED Ø22 rojo 24 V", "Falla"),
  ap("-P3", "PIL-22-AMBAR", "Piloto LED Ø22 ámbar 24 V", "Tapa abierta"),
  ap("-P4", "PIL-22-AMBAR", "Piloto LED Ø22 ámbar 24 V", "Recipiente no acoplado"),
  ap("-F1", "ITM-C2-2P", "ITM 2P C2", "Interruptor automático", "tipo", "placa"),
  ap("-Q2", "GM-2.5-4A", "Guardamotor 2,5–4 A", "Guardamotor", "tipo", "placa"),
  ap("-KM1", "CONT-9A-24VDC", "Contactor 9 A bobina 24 VDC", "Contactor", "tipo", "placa"),
  ap("-T1", "FUENTE-24VDC-2.5A", "Fuente 24 VDC 2,5 A", "Fuente", "tipo", "placa"),
  ap("-K1", "PLC-14DI-10DO-24VDC", "PLC compacto 14 DI / 10 DO 24 VDC", "PLC", "tipo", "placa"),
  ap("-K2", "RS-2C-24VDC", "Relé de seguridad 2 canales 24 VDC", "Seguridad de parada de emergencia y tapa del tanque",
    "derivado", "placa"),
  ap("-K3", "RS-2C-24VDC", "Relé de seguridad 2 canales 24 VDC", "Seguridad de recipiente bajo la descarga", "derivado", "placa"),
];

/** Un tablero que una carga tolerante no pudo armar. */
export const PANEL_SIN_ARMAR: PanelTableroOut = {
  ubicacion: "+TAB1", comando: "c55", armado: false,
  veredicto: { severidad: "falla", frase: "No se pudo armar el tablero",
    nota: "Pídele al agente que lo revise; el motivo está en el detalle técnico." },
  items: [it({ clave: "armado", severidad: "falla", frase: "El tablero no se pudo armar",
    detalle: "Pídele al agente que revise el armado del tablero.",
    tecnico: "Tablero +TAB1: en el TABLERO-5040 no entra: faltan 168 mm de alto; con «auto» entra en el GAB-6040." })],
};
