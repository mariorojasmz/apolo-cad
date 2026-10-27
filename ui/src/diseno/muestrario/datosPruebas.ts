import type { DetallePrueba, PanelPruebasOut } from "../../pruebas/tipos";
import type { Corrida } from "../../pruebas/vista";

/* Datos de ejemplo del panel «Pruebas» (plan visor-para-evaluar D5) con la forma de
   `GET /api/pruebas`: la revisión a ciegas los ve en el muestrario sin una API. */

export const PANEL_PRUEBAS: PanelPruebasOut = {
  veredicto: { severidad: "falla", frase: "2 de 5 pasan · 1 falla · 1 vencido · 1 sin correr" },
  escenarios: [
    { nombre: "desvío a la rampa", estado: "falla", rotulo: "Falla", severidad: "falla", fecha: "2026-10-26T14:03:00",
      balance: "12 entraron · 11 rampa · 1 trabados", estimado_s: 38, n_fallidas: 1,
      descripcion: "el desviador manda cada caja a la rampa" },
    { nombre: "parada de emergencia", estado: "vencido", rotulo: "Vencido", severidad: "aviso",
      fecha: "2026-10-24T09:12:00", ultimo: "Pasa", motivo: "la máquina cambió desde que se corrió", estimado_s: 12 },
    { nombre: "arranque en frío", estado: "sin_correr", rotulo: "Sin correr", severidad: "sin_evaluar" },
    { nombre: "marcha nominal", estado: "pasa", rotulo: "Pasa", severidad: "bien", fecha: "2026-10-26T13:58:00",
      balance: "12 entraron · 12 rampa · 0 trabados", estimado_s: 37 },
    { nombre: "cambio de formato", estado: "pasa", rotulo: "Pasa", severidad: "bien", fecha: "2026-10-26T13:40:00",
      balance: "8 entraron · 8 rampa · 0 trabados", estimado_s: 29 },
  ],
};

export const DETALLE_PRUEBA: DetallePrueba = {
  ...PANEL_PRUEBAS.escenarios[0],
  n_aserciones: 2,
  fallidas: [{ asercion: "flujo.cuadra al_final", cifra: "al final vale falso — caja 7 trabada" }],
  incidencias: [
    { tipo: "trabados", producto: "caja 7", que: "trabado", hora_s: 41.2, punto_mm: [3010, 0, 960],
      pieza: "c1_banda", cerca_de: "Faja de banda · Banda" },
  ],
};

/** Una corrida a la mitad, con el reloj fijo para la captura. */
export const AHORA_MUESTRARIO = new Date(2026, 9, 26, 14, 10).getTime();
export const CORRIDAS_DEMO: Record<string, Corrida> = {
  "marcha nominal": { jobId: "demo", estado: "corriendo", desde: AHORA_MUESTRARIO - 15_000, estimadoS: 37 },
};
