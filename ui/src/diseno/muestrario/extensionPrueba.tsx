/// <reference types="vite/client" />
import { FileText } from "lucide-react";
import type { Extension, VivoPantalla } from "../../extensiones/tipos";
import { inicioVivo, useFaseVivo, useValorVivo } from "../../extensiones/vivo";
import LAMINA from "./lamina-prueba.svg?raw";

/* Una extensión de PRUEBA de la UI. Su panel ancho (plan puntos-de-extension-entregables, D7)
   muestra en línea la lámina de esquema que la extensión falsa de la suite de Python dibuja con
   los trazos del núcleo (`tests/ext_prueba/esquema.py`; un test exige que este SVG esté al día).
   Su chip y su pantalla 3D (plan plc-en-el-lazo, D13) usan sólo la API declarada
   (`extensiones/vivo.ts` y lo que reciben): el chip lee la consigna del PLC y la pantalla del panel
   de operador la pinta y, al tocar «−10» o «+10», manda un `escribir` al PLC.
   Vive en el muestrario, no en `src/extensiones/`: el núcleo publica el registro vacío. */

export function PanelLamina() {
  return (
    <div className="lp-panel">
      <div className="lp-hoja" role="img" aria-label="Esquema de prueba, lámina 1 de 1"
        dangerouslySetInnerHTML={{ __html: LAMINA }} />
    </div>
  );
}

/** La variable del PROGRAM que escribe la pantalla y su señal (`<PLC>.Main.consigna`). */
export const VARIABLE = "Main.consigna";
const plcDe = (vivo: VivoPantalla) => vivo.inicio.dispositivos.find((d) => d.tipo === "plc")?.designacion ?? null;
const consigna = (vivo: VivoPantalla) => {
  const plc = plcDe(vivo);
  return plc ? vivo.valor(`${plc}.${VARIABLE}`) : undefined;
};

/** El chip: la consigna del PLC mientras corre la sesión. */
export function ChipConsigna() {
  const fase = useFaseVivo();
  const plc = inicioVivo()?.dispositivos.find((d) => d.tipo === "plc")?.designacion;
  const valor = useValorVivo(`${plc}.${VARIABLE}`);
  if (!plc || (fase !== "corriendo" && fase !== "pausa")) return null;
  return <span aria-label="Consigna de la pantalla de prueba">Consigna {valor === undefined ? "—" : `${Math.round(valor)} %`}</span>;
}

/** La franja de los botones: el 38 % de abajo, partido en «−10» y «+10». */
const FRANJA = 0.38;

export function dibujarConsigna(ctx: CanvasRenderingContext2D, vivo: VivoPantalla): void {
  const { ancho: w, alto: h, tema } = vivo;
  const m = Math.round(h * 0.05);
  ctx.fillStyle = tema.fondo;
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = tema.panel;
  ctx.fillRect(0, 0, w, Math.round(h * 0.16));
  ctx.fillStyle = tema.tenue;
  ctx.textBaseline = "middle";
  ctx.font = `600 ${Math.round(h * 0.07)}px ${tema.fuente}`;
  ctx.fillText(`${vivo.dispositivo.designacion} · Consigna de la faja`, m, Math.round(h * 0.08));
  const v = consigna(vivo);
  ctx.fillStyle = tema.texto;
  ctx.font = `600 ${Math.round(h * 0.26)}px ${tema.fuente}`;
  ctx.textAlign = "center";
  ctx.fillText(v === undefined ? "—" : `${Math.round(v)} %`, w / 2, h * 0.4);
  const y0 = Math.round(h * (1 - FRANJA)) + m, alto = h - y0 - m, ancho = w / 2 - 1.5 * m;
  ctx.font = `600 ${Math.round(h * 0.11)}px ${tema.fuente}`;
  ([["−10", m, tema.panel, tema.texto], ["+10", w / 2 + m / 2, tema.acento, tema.fondo]] as const).forEach(([rotulo, x, fondo, tinta]) => {
    ctx.fillStyle = fondo;
    ctx.fillRect(x, y0, ancho, alto);
    ctx.strokeStyle = tema.borde;
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y0, ancho, alto);
    ctx.fillStyle = tinta;
    ctx.fillText(rotulo, x + ancho / 2, y0 + alto / 2);
  });
  ctx.textAlign = "start";
}

/** Un toque en «−10» o «+10» escribe la consigna nueva (0–100) en el PLC; arriba no hace nada. */
export function tocarConsigna(x: number, y: number, vivo: VivoPantalla): void {
  const plc = plcDe(vivo);
  if (!plc || y < vivo.alto * (1 - FRANJA)) return;
  const nuevo = Math.max(0, Math.min(100, (consigna(vivo) ?? 0) + (x < vivo.ancho / 2 ? -10 : 10)));
  vivo.enviar({ accion: "escribir", dispositivo: plc, variable: VARIABLE, valor: nuevo });
}

export const EXTENSION_PRUEBA: Extension = {
  nombre: "prueba",
  paneles: [
    { id: "prueba.lamina", titulo: "Esquema de prueba", rotulo: "Esquema", Componente: PanelLamina, icono: FileText,
      ancho: "lamina" },
  ],
  chipsVivo: [{ id: "prueba.consigna", Componente: ChipConsigna }],
  pantallas3d: [{ id: "prueba.consigna", tipo: "hmi", dibujar: dibujarConsigna, tocar: tocarConsigna }],
};
