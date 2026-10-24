import { useRef, useState, type ReactNode } from "react";
import { suave } from "../movimiento";
import VacioTablero from "../../tablero/VacioTablero";
import VistaTablero from "../../tablero/VistaTablero";
import type { PanelTableroOut } from "../../tablero/tipos";
import { recorridoDe } from "../../tablero/vista";
import { PANEL_CON_FALLAS, PANEL_EN_ORDEN, PANEL_SIN_ARMAR } from "./datosTablero";
import { BarraFallasDemo, PanelFallasDemo, PanelMandosDemo } from "./FallasDemo";
import VueloDemo, { type Demo } from "./VueloDemo";
import "./muestrario.css";

/* Muestrario de diseño (plan V8.5 F3b-0, F3b): el panel «Tablero» REAL (`tablero/VistaTablero`)
   con datos de ejemplo (`datosTablero.ts`, la forma de la API) en sus cuatro estados, al ancho de
   un panel de Dockview, junto a un visor de ejemplo con el vuelo de cámara, la puerta y el
   recorrido de un conductor. Es la base de la revisión de diseño a ciegas (D14). Abajo,
   «Mandos» (con el resguardo y el relé de seguridad), «Simular falla» y la barra de la sesión
   viva con datos de ejemplo (planes cosim-fallas D7 y mandos-de-seguridad).
   `?ancho=420` = una columna angosta; `?puerta=90` abre la puerta; `?conductor=c26` lo dibuja. */

const q = () => new URLSearchParams(window.location.search);

export default function Muestrario() {
  const demo = useRef<Demo | null>(null);
  const [puerta, setPuerta] = useState(() => Number(q().get("puerta") ?? 0));
  const [conductor, setConductor] = useState<string | null>(() => q().get("conductor"));
  const moverPuerta = (g: number) => { setPuerta(g); demo.current?.puerta(g); };
  const animarPuerta = (destino: number) => { // como el panel real: ≈ 320 ms con la curva suave
    const desde = puerta, t0 = performance.now();
    const paso = (ahora: number) => {
      const f = Math.min(1, (ahora - t0) / 320);
      moverPuerta(desde + (destino - desde) * suave(f));
      if (f < 1) requestAnimationFrame(paso);
    };
    requestAnimationFrame(paso);
  };
  const dibujar = (p: PanelTableroOut) => (id: string | null) => {
    setConductor(id);
    demo.current?.recorrido(recorridoDe(p, id));
  };
  const ancho = Number(q().get("ancho")) || 0;
  const vista = (p: PanelTableroOut) => (
    <VistaTablero panel={p} conductor={conductor} onConductor={dibujar(p)}
      onEncuadrar={(piezas) => demo.current?.ir(piezas)}
      puerta={p.puerta ? { valor: puerta, min: p.puerta.min_deg, max: p.puerta.max_deg, onCambio: moverPuerta,
        onAnimar: animarPuerta } : undefined} />
  );
  return (
    <main className={`muestrario${ancho ? " angosto" : ""}`} style={ancho ? { width: ancho } : undefined}>
      <Marco rotulo="Tablero · con cosas por atender">{vista(PANEL_CON_FALLAS)}</Marco>
      <div className="mu-columna">
        <Marco rotulo="Tablero · sin fallas">{vista(PANEL_EN_ORDEN)}</Marco>
        <Marco rotulo="Tablero · no se pudo armar">{vista(PANEL_SIN_ARMAR)}</Marco>
        <Marco rotulo="Tablero · sin armar"><VacioTablero /></Marco>
      </div>
      <Marco rotulo="Visor · clic en un ítem para volar" ancho>
        <VueloDemo alListo={(d) => {
          demo.current = d;
          const c = q().get("conductor");
          if (c) d.recorrido(recorridoDe(PANEL_CON_FALLAS, c));
        }} />
      </Marco>
      <Marco rotulo="Mandos · resguardo y relé de seguridad">
        <PanelMandosDemo />
      </Marco>
      <Marco rotulo="Mandos · simular falla">
        <PanelFallasDemo />
      </Marco>
      <Marco rotulo="Barra de la sesión viva · fallas activas" doble>
        <BarraFallasDemo />
      </Marco>
    </main>
  );
}

/** El marco del muestrario (no es parte de los componentes): rótulo y fondo de panel. */
function Marco({ rotulo, ancho, doble, children }: { rotulo: string; ancho?: boolean; doble?: boolean; children: ReactNode }) {
  return (
    <section className={`mu-marco${ancho ? " ancho" : ""}${doble ? " doble" : ""}`} aria-label={rotulo}>
      <p className="mu-rotulo">{rotulo}</p>
      <div className="mu-panel">{children}</div>
    </section>
  );
}
