import { useMemo, useRef, useState, type ReactNode } from "react";
import { PanelsTopLeft } from "lucide-react";
import VerDetalle from "../../ui/VerDetalle";
import { queAtender, veredictoDe } from "../atencion";
import Deslizador from "../Deslizador";
import EstadoVacio from "../EstadoVacio";
import ItemsAtencion from "../ItemsAtencion";
import Veredicto from "../Veredicto";
import { itemsTablero } from "./datos";
import VueloDemo, { type Demo } from "./VueloDemo";
import "./muestrario.css";

/* Muestrario de diseño (plan V8.5 F3b-0): las piezas comunes con los datos de ejemplo del panel
   «Tablero», al ancho de un panel de Dockview, junto a un visor de ejemplo con el vuelo de
   cámara. Es la base de la revisión de diseño a ciegas (D14); F3b arma el panel real. */

export default function Muestrario() {
  const demo = useRef<Demo | null>(null);
  const [puerta, setPuerta] = useState(() => Number(new URLSearchParams(window.location.search).get("puerta") ?? 0));
  const items = useMemo(() => itemsTablero((pieza) => demo.current?.ir(pieza)), []);
  const v = veredictoDe(items, "El tablero cumple");
  const bien = items.filter((it) => it.severidad === "bien");
  const moverPuerta = (g: number) => { setPuerta(g); demo.current?.puerta(g); };
  const ancho = Number(new URLSearchParams(window.location.search).get("ancho")) || 0;
  return (
    <main className={`muestrario${ancho ? " angosto" : ""}`} style={ancho ? { width: ancho } : undefined}>
      <Marco rotulo="Tablero · con cosas por atender">
        <Veredicto severidad={v.severidad} frase={v.frase} nota="Revisamos 13 de 14 reglas" />
        <ItemsAtencion items={queAtender(items)} rotulo="Lo que pide atención en el tablero" />
        <Deslizador rotulo="Puerta" valor={puerta} min={0} max={110} unidad="°" onCambio={moverPuerta} />
        <div className="mu-detalle">
          <VerDetalle resumen="Detalle">
            <ul>{bien.map((it) => <li key={it.clave}>{it.frase}: {it.cifra}</li>)}</ul>
          </VerDetalle>
        </div>
      </Marco>
      <div className="mu-columna">
        <Marco rotulo="Tablero · todo en orden">
          <Veredicto severidad="bien" frase="El tablero cumple" nota="Revisamos 14 reglas del tablero" />
          <Deslizador rotulo="Puerta" valor={puerta} min={0} max={110} unidad="°" onCambio={moverPuerta} />
        </Marco>
        <Marco rotulo="Tablero · sin armar">
          <EstadoVacio icono={<PanelsTopLeft size={28} strokeWidth={1.5} />} titulo="Aquí vas a ver el tablero armado"
            accion={{ rotulo: "Copiar el pedido", onClick: () => {} }}>
            Pídele al agente que arme el tablero desde el circuito.
          </EstadoVacio>
        </Marco>
      </div>
      <Marco rotulo="Visor · clic en un ítem para volar" ancho>
        <VueloDemo alListo={(d) => { demo.current = d; }} />
      </Marco>
    </main>
  );
}

/** El marco del muestrario (no es parte de los componentes): rótulo y fondo de panel. */
function Marco({ rotulo, ancho, children }: { rotulo: string; ancho?: boolean; children: ReactNode }) {
  return (
    <section className={`mu-marco${ancho ? " ancho" : ""}`} aria-label={rotulo}>
      <p className="mu-rotulo">{rotulo}</p>
      <div className="mu-panel">{children}</div>
    </section>
  );
}
