import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { cifra } from "../diseno/cifra";
import ItemsAtencion from "../diseno/ItemsAtencion";
import Veredicto from "../diseno/Veredicto";
import VerDetalle from "../ui/VerDetalle";
import { itemsDeAtencion, type AccionesTablero } from "../tablero/vista";
import EsquemaNeumatica from "./EsquemaNeumatica";
import { rotuloCilindro, textoConsumo, textoFuerza, textoTiempo, type Lector } from "./esquema";
import type { CilindroDetalle, ItemNeumatica, PanelNeumaticaOut, SimboloEsquema } from "./tipos";
import "../tablero/tablero.css";
import "./neumatica.css";

/* La vista del panel «Neumática» (plan V8.9 D12): responde «¿está bien mi circuito de aire?»
   arriba (un veredicto), debajo sólo lo que pide atención (clic → la cámara vuela al aparato y la
   fila abre su frase debajo), el esquema ISO 1219 en línea (vivo con la sesión) y, a pedido, el
   detalle de cada cilindro. Recibe todo por props: la monta el panel real (`PanelNeumatica.tsx`). */

interface Props {
  panel: PanelNeumaticaOut;
  /** Las señales de la sesión viva, o null sin sesión. */
  lector: Lector | null;
  /** Los aparatos elegidos (por la selección del 3D o por un clic aquí). */
  elegidos: ReadonlySet<string>;
  onEncuadrar: (piezas: readonly string[]) => void;
  onElegirSimbolo: (s: SimboloEsquema) => void;
  inicial?: { detalle?: boolean; item?: string };
}

export default function VistaNeumatica({ panel, lector, elegidos, onEncuadrar, onElegirSimbolo, inicial }: Props) {
  const items = panel.items ?? [];
  const [elegido, setElegido] = useState<ItemNeumatica | null>(() => items.find((it) => it.clave === inicial?.item) ?? null);
  const [abierto, setAbierto] = useState(!!inicial?.detalle);
  const v = panel.veredicto;
  const acciones: AccionesTablero = { encuadrar: onEncuadrar, dibujar: () => {}, elegir: setElegido };
  const esquema = panel.esquema;
  const cilindros = panel.detalle?.cilindros ?? [];
  return (
    <div className="tablero neumatica">
      {v && <Veredicto severidad={v.severidad} frase={v.frase} nota={v.nota} />}
      <ItemsAtencion items={itemsDeAtencion(items, acciones)} rotulo="Lo que pide atención en el circuito de aire"
        elegida={elegido?.clave} debajo={elegido?.detalle ? <p aria-live="polite">{elegido.detalle}</p> : null} />
      {esquema && (
        <section className="tb-seccion nm-seccion" aria-label="Esquema">
          {esquema.error ? (
            <>
              <h3 className="tb-titulo">Esquema</h3>
              <p className="nm-nota">{esquema.error}</p>
            </>
          ) : (
            <EsquemaNeumatica esquema={esquema} lector={lector} elegidos={elegidos} onElegir={onElegirSimbolo}
              titulo={lector ? "Esquema en vivo" : "Esquema"} />
          )}
        </section>
      )}
      {cilindros.length > 0 && (
        <details className="tb-plegable" open={abierto} onToggle={(e) => setAbierto(e.currentTarget.open)}>
          <summary>Detalle</summary>
          {abierto && (
            <div className="tb-detalle">
              {cilindros.map((c) => <FichaCilindro key={c.designacion} c={c} onEncuadrar={onEncuadrar} />)}
              {panel.detalle?.maquina.NL_min !== undefined && (
                <MaquinaAire nl={panel.detalle.maquina.NL_min} sinFugas={panel.detalle.maquina.sin_fugas_NL_min} />
              )}
              <VerDetalle resumen="Detalle técnico">
                <ul className="nm-tecnico">
                  {items.filter((it) => it.tecnico).map((it) => <li key={it.clave}>{it.tecnico}</li>)}
                </ul>
              </VerDetalle>
            </div>
          )}
        </details>
      )}
    </div>
  );
}

function FichaCilindro({ c, onEncuadrar }: { c: CilindroDetalle; onEncuadrar: (piezas: readonly string[]) => void }) {
  const t = c.tiempo ? textoTiempo(c.tiempo) : null;
  const cabeza = (
    <>
      <span className="tb-principal"><strong>{c.designacion}</strong><span className="tb-secundario">{rotuloCilindro(c)}</span></span>
      <span />
      {c.piezas.length ? <ChevronRight className="tb-ir" size={14} aria-hidden="true" /> : <span />}
    </>
  );
  return (
    <div className="tb-seccion">
      {c.piezas.length ? (
        <button type="button" className="tb-fila nm-cabeza" onClick={() => onEncuadrar(c.piezas)}
          aria-label={`${c.designacion}: encontrarlo en el 3D`}>{cabeza}</button>
      ) : (
        <div className="tb-fila nm-cabeza">{cabeza}</div>
      )}
      <dl className="nm-cifras">
        {c.fuerza && <><dt>Fuerza a {cifra(c.fuerza.p_bar, Number.isInteger(c.fuerza.p_bar) ? 0 : 1, "bar")}</dt><dd>{textoFuerza(c.fuerza).map((t) => <span key={t} className="nm-linea">{t}</span>)}</dd></>}
        {c.consumo && <><dt>Consumo de aire</dt><dd>{textoConsumo(c.consumo)}</dd></>}
        {t && <><dt>Tiempo de carrera</dt><dd>{t.cifras}<span className="nm-origen">{t.origen}</span></dd></>}
      </dl>
    </div>
  );
}

function MaquinaAire({ nl, sinFugas }: { nl: number; sinFugas?: number }) {
  const conFugas = sinFugas !== undefined && Math.abs(nl - sinFugas) > 1e-6;
  return (
    <div className="tb-seccion">
      <h3 className="tb-titulo">La máquina</h3>
      <dl className="nm-cifras">
        <dt>Demanda de aire</dt>
        <dd>
          {cifra(nl, 1, "NL/min")}
          <span className="nm-origen">{conFugas ? "con las fugas declaradas" : "sin contar fugas"}</span>
        </dd>
      </dl>
    </div>
  );
}
