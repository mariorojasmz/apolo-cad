import type { DetallePrueba, PanelPruebasOut } from "../../pruebas/tipos";
import type { Corrida } from "../../pruebas/vista";

/* Datos de ejemplo del panel «Pruebas» (plan visor-para-evaluar D5) con la forma de
   `GET /api/pruebas`: la revisión a ciegas los ve en el muestrario sin una API. Son los escenarios
   de la mezcladora de paletas (plan nombres-por-funcion F4): el `titulo` humanizado que suma
   `services/pruebas_panel.py` (D14) y el id en `nombre`, con la descripción tal como la escribió el
   modelador (trae designaciones: es su texto, `set_scenario` lo avisa). */

export const PANEL_PRUEBAS: PanelPruebasOut = {
  veredicto: { severidad: "falla", frase: "3 de 6 pasan · 1 falla · 1 vencido · 1 sin correr" },
  escenarios: [
    { nombre: "descargar_sin_recipiente", titulo: "Descargar sin recipiente", estado: "falla", rotulo: "Falla",
      severidad: "falla", fecha: "2026-10-26T14:03:00", estimado_s: 21, n_fallidas: 1,
      descripcion: "Sin recipiente acoplado (-B4 abierto), la compuerta no tiene que abrir aunque el PLC lo pida." },
    { nombre: "abrir_tapa_en_marcha", titulo: "Abrir tapa en marcha", estado: "vencido", rotulo: "Vencido",
      severidad: "aviso", fecha: "2026-10-24T09:12:00", ultimo: "Pasa", motivo: "la máquina cambió desde que se corrió",
      estimado_s: 14 },
    { nombre: "rearme_con_tapa_abierta", titulo: "Rearme con tapa abierta", estado: "sin_correr", rotulo: "Sin correr",
      severidad: "sin_evaluar" },
    { nombre: "ciclo_nominal", titulo: "Ciclo nominal", estado: "pasa", rotulo: "Pasa", severidad: "bien",
      fecha: "2026-10-26T13:58:00", estimado_s: 37 },
    { nombre: "parada_de_emergencia", titulo: "Parada de emergencia", estado: "pasa", rotulo: "Pasa", severidad: "bien",
      fecha: "2026-10-26T13:40:00", estimado_s: 12 },
    { nombre: "descarga_completa", titulo: "Descarga completa", estado: "pasa", rotulo: "Pasa", severidad: "bien",
      fecha: "2026-10-26T13:31:00", estimado_s: 29 },
  ],
};

export const DETALLE_PRUEBA: DetallePrueba = {
  ...PANEL_PRUEBAS.escenarios[0],
  n_aserciones: 2,
  // como lo escribe `services/pruebas_frases.py` (F5b): en llano arriba; la expresión, a pedido
  fallidas: [{ asercion: "-MM1.x_mm < 5 siempre", cifra: "deja de cumplirse en t = 3.4 s (vale 12)",
    frase: "La carrera del cilindro de compuerta (-MM1) tenía que estar siempre por debajo de 5 mm",
    paso: "A los 3,4 s estaba en 12 mm" }],
  incidencias: [],
};

/** Una corrida a la mitad, con el reloj fijo para la captura. */
export const AHORA_MUESTRARIO = new Date(2026, 9, 26, 14, 10).getTime();
export const CORRIDAS_DEMO: Record<string, Corrida> = {
  ciclo_nominal: { jobId: "demo", estado: "corriendo", desde: AHORA_MUESTRARIO - 15_000, estimadoS: 37 },
};
