import { useEffect, useRef } from "react";
import { movimientoReducido } from "../diseno/movimiento";
import { useStore } from "../state/store";
import { EVENTO_RESTAURAR } from "../viewport/atenuar";
import { pedirEncuadre } from "../viewport/pedirEncuadre";
import { cargarTablero, useTablero } from "./estado";
import VacioTablero from "./VacioTablero";
import VistaTablero from "./VistaTablero";
import { duracionPuerta, valorPuertaEn } from "./vista";

/* Panel «Tablero» (plan V8.5 D13): lo que el agente leyó del tablero armado, para que la persona
   lo evalúe en el visor. Lee la API (`estado.ts`) cada vez que el documento cambia; el clic en un
   ítem vuela la cámara a sus piezas y las selecciona (`pedirEncuadre`), el deslizador mueve la
   junta de la puerta como cualquier junta (`setJointValue`; el visor la posa con
   `applyKinematicPoses`) y un conductor elegido se dibuja en el 3D (`recorrido3d.ts`). */

export default function PanelTablero() {
  const scene = useStore((s) => s.scene);
  const panel = useTablero((s) => s.panel);
  const leido = useTablero((s) => s.leido);
  const error = useTablero((s) => s.error);
  const conductor = useTablero((s) => s.conductor);
  const junta = panel?.puerta?.junta ?? "";
  const valorPuerta = useStore((s) => s.jointValues[junta] ?? 0);
  const anim = useRef<number | null>(null);

  // el documento cambió (también un cambio del agente): se vuelve a leer, sin martillar la API
  useEffect(() => {
    const t = window.setTimeout(() => void cargarTablero(), 250);
    return () => window.clearTimeout(t);
  }, [scene]);
  // al cerrar el panel, el recorrido deja de dibujarse
  useEffect(() => () => useTablero.getState().set({ conductor: null }), []);
  useEffect(() => () => { if (anim.current !== null) cancelAnimationFrame(anim.current); }, []);
  // lo que se atenuó para ver el tablero vuelve al cerrar el panel
  useEffect(() => () => { window.dispatchEvent(new Event(EVENTO_RESTAURAR)); }, []);

  if (!panel) {
    if (error) return <section className="history"><p className="estado-aviso">No pudimos leer el tablero: {error}</p></section>;
    if (!leido) return <section className="history"><p className="hint">Leyendo el tablero…</p></section>;
    return <section className="history"><VacioTablero /></section>;
  }

  const encuadrar = (piezas: readonly string[], puntos?: readonly (readonly number[])[]) =>
    pedirEncuadre(piezas, { animar: true, seleccionar: true, puntos, despejar: true });
  const gabinete = panel.gabinete?.pieza;
  // abrir desde cerrada: la cámara mira la puerta de frente, en lo que se ve del visor, y
  // esquiva o atenúa lo que tape el gabinete (plan visor-para-evaluar D13–D15)
  const verInterior = () => {
    if (gabinete) pedirEncuadre([gabinete], { animar: true, frente: panel.puerta?.pieza, despejar: true });
  };
  const mover = (v: number) => {
    if (valorPuerta === 0 && v > 0) verInterior();
    useStore.getState().setJointValue(junta, v);
  };
  const animar = (destino: number) => {
    if (anim.current !== null) cancelAnimationFrame(anim.current);
    const desde = useStore.getState().jointValues[junta] ?? 0;
    if (desde === 0 && destino > 0) verInterior();
    const dura = duracionPuerta(movimientoReducido());
    const t0 = performance.now();
    const paso = (ahora: number) => {
      const f = dura > 0 ? (ahora - t0) / dura : 1;
      useStore.getState().setJointValue(junta, valorPuertaEn(desde, destino, f));
      anim.current = f < 1 ? requestAnimationFrame(paso) : null;
    };
    anim.current = requestAnimationFrame(paso);
  };
  return (
    <section className="history panel-tablero">
      <VistaTablero panel={panel} conductor={conductor}
        onConductor={(id) => useTablero.getState().set({ conductor: id })}
        onEncuadrar={encuadrar}
        puerta={panel.puerta ? { valor: valorPuerta, min: panel.puerta.min_deg, max: panel.puerta.max_deg,
          onCambio: mover, onAnimar: animar } : undefined} />
    </section>
  );
}
