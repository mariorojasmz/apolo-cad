import { useEffect } from "react";
import { useStore } from "../state/store";
import { pedirEncuadre } from "../viewport/pedirEncuadre";
import { alternarPrueba, cargarPruebas, correrPrueba, usePruebas, verEnVivo } from "./estado";
import VistaPruebas, { type AccionesPruebas } from "./VistaPruebas";

/* Panel «Pruebas» (plan visor-para-evaluar D1): el veredicto de los escenarios guardados, para
   que la persona lo evalúe en el visor. Lee la API cada vez que el documento cambia (un cambio
   vence las pruebas); el clic en un producto trabado vuela la cámara a su lugar. */

const ACCIONES: AccionesPruebas = {
  alternar: alternarPrueba,
  correr: (f) => void correrPrueba(f.nombre, f.estimado_s),
  enVivo: (n) => void verEnVivo(n),
  // el punto donde quedó el producto, con contexto alrededor (no la pieza entera: una banda de 6 m
  // no dice dónde); sin punto, la pieza
  verLugar: (i) => (i.punto_mm
    ? pedirEncuadre([], { animar: true, puntos: [i.punto_mm] })
    : pedirEncuadre(i.pieza ? [i.pieza] : [], { animar: true, seleccionar: true })),
};

export default function PanelPruebas() {
  const scene = useStore((s) => s.scene);
  const panel = usePruebas((s) => s.panel);
  const leido = usePruebas((s) => s.leido);
  const error = usePruebas((s) => s.error);
  const abierto = usePruebas((s) => s.abierto);
  const detalle = usePruebas((s) => s.detalle);
  const corridas = usePruebas((s) => s.corridas);
  const fallos = usePruebas((s) => s.fallos);

  // el documento cambió (también un cambio del agente): se vuelve a leer, sin martillar la API
  useEffect(() => {
    const t = window.setTimeout(() => void cargarPruebas(), 250);
    return () => window.clearTimeout(t);
  }, [scene]);

  let cuerpo;
  if (panel) {
    cuerpo = <VistaPruebas panel={panel} abierto={abierto} detalle={detalle} corridas={corridas} fallos={fallos} acciones={ACCIONES} />;
  } else if (error) {
    cuerpo = <p className="estado-aviso">No pudimos leer las pruebas: {error}</p>;
  } else {
    cuerpo = <p className="hint">{leido ? "" : "Leyendo las pruebas…"}</p>;
  }
  return <section className="history panel-pruebas">{cuerpo}</section>;
}
