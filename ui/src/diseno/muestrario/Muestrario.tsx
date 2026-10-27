import { useRef, useState, type ReactNode } from "react";
import { suave } from "../movimiento";
import VacioTablero from "../../tablero/VacioTablero";
import VistaTablero from "../../tablero/VistaTablero";
import type { PanelTableroOut } from "../../tablero/tipos";
import { recorridoDe } from "../../tablero/vista";
import { AparatosTablero } from "../../tablero/DetalleTablero";
import VistaNeumatica from "../../neumatica/VistaNeumatica";
import type { PanelNeumaticaOut } from "../../neumatica/tipos";
import { APARATOS_MEZCLADORA, PANEL_CON_FALLAS, PANEL_EN_ORDEN, PANEL_SIN_ARMAR } from "./datosTablero";
import { BarraFallasDemo, PanelFallasDemo, PanelMandosDemo, PanelSenalesDemo } from "./FallasDemo";
import neumaticaMezcladora from "./neumaticaMezcladora.json";
import VueloDemo, { type Demo } from "./VueloDemo";
import MarcoCajon from "../../visor/MarcoCajon";
import { EXTENSION_PRUEBA } from "./extensionPrueba";
import PantallaDemo from "./PantallaDemo";
import VistaPruebas from "../../pruebas/VistaPruebas";
import { AHORA_MUESTRARIO, CORRIDAS_DEMO, DETALLE_PRUEBA, PANEL_PRUEBAS } from "./datosPruebas";
import "./muestrario.css";

/* Muestrario de diseño (plan V8.5 F3b-0, F3b): el panel «Tablero» REAL (`tablero/VistaTablero`)
   con datos de ejemplo (`datosTablero.ts`, la forma de la API) en sus cuatro estados, al ancho de
   un panel de Dockview, junto a un visor de ejemplo con el vuelo de cámara, la puerta y el
   recorrido de un conductor. Es la base de la revisión de diseño a ciegas (D14). Abajo,
   «Mandos» (la mezcladora de paletas: 8 mandos, 4 pilotos y 2 relés, plan nombres-por-funcion
   F3; `?mandos=` elige su estado), «Simular falla» y la barra de la sesión viva con datos de
   ejemplo (planes cosim-fallas D7 y mandos-de-seguridad). Al final, el cajón
   del visor con un panel de extensión de prueba que pide el ancho de una lámina
   (`extensionPrueba.tsx`, plan puntos-de-extension-entregables D7), y su chip en la barra y su
   pantalla sobre un panel de operador girado (plan plc-en-el-lazo D13).
   `?ancho=420` = una columna angosta; `?puerta=90` abre la puerta; `?conductor=c26` lo dibuja;
   `?detalle=1&item=largos` abre el detalle con ese ítem elegido (en el panel con fallas).
   Nombres por función (plan nombres-por-funcion F4), todo de la mezcladora: «Tablero · aparatos»,
   «Neumática» (`?simbolo=-RZ1` elige un aparato del esquema), «Pruebas» con títulos humanizados,
   «Señales» (`?senales=<texto>` filtra y despliega) y, dentro de «Mandos», «Provocar atasco» y el
   accionamiento manual (`?manual=0` lo pliega). */

const q = () => new URLSearchParams(window.location.search);
const NEUMATICA_MEZCLADORA = neumaticaMezcladora as unknown as PanelNeumaticaOut;

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
  const inicial = { detalle: q().get("detalle") === "1", item: q().get("item") ?? undefined };
  const vista = (p: PanelTableroOut) => (
    <VistaTablero panel={p} conductor={conductor} onConductor={dibujar(p)} inicial={p === PANEL_CON_FALLAS ? inicial : undefined}
      onEncuadrar={(piezas, puntos) => demo.current?.ir(piezas, puntos)}
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
        <VueloDemo puntosIniciales={recorridoDe(PANEL_CON_FALLAS, q().get("conductor"))?.flat()} alListo={(d) => {
          demo.current = d;
          const c = q().get("conductor");
          if (c) d.recorrido(recorridoDe(PANEL_CON_FALLAS, c));
        }} />
      </Marco>
      <Marco rotulo="Tablero · aparatos de la mezcladora">
        <div className="tablero">
          <div className="tb-detalle"><AparatosTablero aparatos={APARATOS_MEZCLADORA} encuadrar={() => {}} /></div>
        </div>
      </Marco>
      <Marco rotulo="Neumática · compuerta de la mezcladora">
        <NeumaticaDemo />
      </Marco>
      <Marco rotulo="Pruebas · una abierta y otra corriendo">
        <PruebasDemo />
      </Marco>
      <Marco rotulo="Pruebas · sin escenarios">
        <VistaPruebas panel={{ veredicto: null, escenarios: [] }} abierto={null} detalle={null} corridas={{}} fallos={{}}
          acciones={ACCIONES_NULAS} />
      </Marco>
      <Marco rotulo="Mandos · mezcladora de paletas">
        <PanelMandosDemo />
      </Marco>
      <Marco rotulo="Señales · mezcladora de paletas">
        <PanelSenalesDemo />
      </Marco>
      <Marco rotulo="Mandos · simular falla">
        <PanelFallasDemo />
      </Marco>
      <Marco rotulo="Barra de la sesión viva · fallas activas y chip de extensión" doble>
        <BarraFallasDemo />
      </Marco>
      <Marco rotulo="Visor · pantalla de extensión en el panel de operador" ancho>
        <PantallaDemo />
      </Marco>
      <Marco rotulo="Visor · panel de extensión al ancho de una lámina" ancho entero>
        <CajonDeExtension />
      </Marco>
    </main>
  );
}

const ACCIONES_NULAS = { alternar: () => {}, correr: () => {}, enVivo: () => {}, verLugar: () => {} };

/** El panel «Pruebas» (plan visor-para-evaluar D5) con datos de ejemplo: una prueba abierta con lo
   que falló y el producto trabado, y otra corriendo (el reloj fijo para la captura). */
function PruebasDemo() {
  const [abierto, setAbierto] = useState<string | null>(DETALLE_PRUEBA.nombre);
  return (
    <VistaPruebas panel={PANEL_PRUEBAS} abierto={abierto} detalle={abierto === DETALLE_PRUEBA.nombre ? DETALLE_PRUEBA : null}
      corridas={CORRIDAS_DEMO} fallos={{}} ahora={AHORA_MUESTRARIO}
      acciones={{ ...ACCIONES_NULAS, alternar: (n) => setAbierto(abierto === n ? null : n) }} />
  );
}

/** «Neumática» de la compuerta de la mezcladora (plan nombres-por-funcion F4): lo que devuelve
   `GET /api/neumatica` sobre un circuito como el suyo (`neumaticaMezcladora.json`, generado con
   `services/neumatica_panel.panel`), con el detalle abierto y un aparato elegido en el esquema
   (`?simbolo=-RZ1` por defecto; clic en otro lo cambia). */
function NeumaticaDemo() {
  const [elegido, setElegido] = useState<string>(() => q().get("simbolo") ?? "-RZ1");
  return (
    <section className="panel-tablero">
      <VistaNeumatica panel={NEUMATICA_MEZCLADORA} lector={null} elegidos={new Set([elegido])} onEncuadrar={() => {}}
        onElegirSimbolo={(s) => setElegido(s.designacion)} inicial={{ detalle: true }} />
    </section>
  );
}

/** El cajón derecho del visor con el panel de la extensión de prueba (`ancho: "lamina"`), con
   el CSS real de los cajones sobre un fondo que hace de 3D. */
function CajonDeExtension() {
  const [abierto, setAbierto] = useState(true);
  const panel = EXTENSION_PRUEBA.paneles![0];
  const { Componente } = panel;
  return (
    <div className="app modo-visor mu-capa">
      <div className="capa-visor">
        {abierto ? (
          <MarcoCajon lado="der" titulo={panel.titulo} ancho={panel.ancho} onCerrar={() => setAbierto(false)}>
            <Componente />
          </MarcoCajon>
        ) : (
          <button type="button" className="mu-reabrir" onClick={() => setAbierto(true)}>
            Abrir {panel.rotulo.toLowerCase()}
          </button>
        )}
      </div>
    </div>
  );
}

/** El marco del muestrario (no es parte de los componentes): rótulo y fondo de panel. */
function Marco({ rotulo, ancho, doble, entero, children }: {
  rotulo: string; ancho?: boolean; doble?: boolean; entero?: boolean; children: ReactNode;
}) {
  return (
    <section className={`mu-marco${ancho ? " ancho" : ""}${doble ? " doble" : ""}${entero ? " entero" : ""}`} aria-label={rotulo}>
      <p className="mu-rotulo">{rotulo}</p>
      <div className="mu-panel">{children}</div>
    </section>
  );
}
