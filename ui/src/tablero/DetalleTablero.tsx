import { useState, type ReactNode } from "react";
import { ChevronRight } from "lucide-react";
import IconoSeveridad from "../diseno/IconoSeveridad";
import ItemsAtencion from "../diseno/ItemsAtencion";
import { cifra } from "../diseno/cifra";
import NombreAparato from "../diseno/NombreAparato";
import VerDetalle from "../ui/VerDetalle";
import type { AparatoTablero, CableTablero, ConductorTablero, PanelTableroOut } from "./tipos";
import {
  cablesListados, conductoresListados, filasCalor, itemsDeAtencion, largoCable, largoConductor, partesCable,
  perdidasCalor, puntosDe, rotuloConductor, supuestosDe, type AccionesTablero,
} from "./vista";

/* El «Detalle» del panel «Tablero» (plan V8.5 D13): lo que está bien, los conductores con su largo
   (clic → su recorrido en el 3D), las canaletas con su llenado, los aparatos, el calentamiento
   (IEC 60890: la temperatura a media altura y arriba, o por qué no se evaluó) y los prensaestopas
   de los cables que salen. Sólo se ve a pedido; cada fila que señala algo encuadra su pieza. */

/** Cuántos conductores se ven antes de «Ver N más». */
const VISIBLES = 8;

interface Props {
  panel: PanelTableroOut;
  acciones: AccionesTablero;
  conductor: string | null;
  /** Los conductores del ítem elegido (null: todos). */
  filtro: readonly string[] | null;
  quitarFiltro: () => void;
}

export default function DetalleTablero({ panel, acciones, conductor, filtro, quitarFiltro }: Props) {
  const d = panel.detalle;
  if (!d) return null;
  const supuestos = supuestosDe(panel);
  return (
    <div className="tb-detalle">
      {d.bien.length > 0 && (
        <Seccion titulo="Lo que cumple">
          <ItemsAtencion items={itemsDeAtencion(d.bien, acciones, panel)} rotulo="Lo que cumple en el tablero" />
        </Seccion>
      )}
      <Conductores panel={panel} acciones={acciones} conductor={conductor} filtro={filtro} quitarFiltro={quitarFiltro} />
      <Cables panel={panel} acciones={acciones} conductor={conductor} filtro={filtro} quitarFiltro={quitarFiltro} />
      <Seccion titulo="Canaletas">
        <ul className="tb-filas">
          {d.canaletas.map((k, i) => (
            <li key={`${k.pieza ?? "k"}-${i}`}>
              <Fila principal={k.nombre} cifra={cifra(k.llenado * 100, 0, "%")}
                onClick={k.pieza ? () => acciones.encuadrar([k.pieza!]) : undefined} />
            </li>
          ))}
        </ul>
      </Seccion>
      <AparatosTablero aparatos={d.aparatos} encuadrar={acciones.encuadrar} />
      <Seccion titulo="Calentamiento">
        {d.calentamiento.estado === "sin_evaluar" ? (
          <p className="tb-calor">
            <IconoSeveridad severidad="sin_evaluar" tamano={15} />
            <span>{d.calentamiento.motivo}</span>
          </p>
        ) : (
          <ul className="tb-filas">
            {filasCalor(d.calentamiento, d.aparatos).map(([rotulo, valor]) => (
              <li key={rotulo}><Fila principal={rotulo} cifra={valor} /></li>
            ))}
          </ul>
        )}
        <p className="tb-nota">{perdidasCalor(d.calentamiento)}</p>
      </Seccion>
      {(d.prensaestopas?.prensas.length ?? 0) > 0 && (
        <Seccion titulo="Prensaestopas">
          <ul className="tb-filas">
            {d.prensaestopas!.prensas.map((p) => (
              <li key={p.cable}>
                <Fila principal={p.designacion} secundario={p.ref ? p.nombre : "Ningún prensaestopas lo sujeta"}
                  cifra={p.diametro_mm !== undefined ? `Ø${cifra(p.diametro_mm, 1, "mm")}` : undefined} />
              </li>
            ))}
          </ul>
        </Seccion>
      )}
      {supuestos.length > 0 && (
        <VerDetalle resumen="Supuestos del recorrido">
          <ul>{supuestos.map((s) => <li key={s}>{s}</li>)}</ul>
        </VerDetalle>
      )}
    </div>
  );
}

/** «Aparatos»: cada uno por lo que hace (plan nombres-por-funcion D9), con la designación y el
   nombre del catálogo detrás, chicos («Seguridad del recipiente  -K3 · Relé de seguridad…»); sin
   rótulo del servidor, la designación manda y el catálogo la sigue. Clic → su pieza en el 3D. */
export function AparatosTablero({ aparatos, encuadrar }: {
  aparatos: readonly AparatoTablero[]; encuadrar: (piezas: string[]) => void;
}) {
  return (
    <Seccion titulo="Aparatos">
      <ul className="tb-filas">
        {aparatos.map((a) => (
          <li key={a.designacion}>
            <Fila principal={<span className="cabeza-aparato"><NombreAparato a={a} detalle={a.nombre} /></span>}
              onClick={a.pieza ? () => encuadrar([a.pieza!]) : undefined} />
          </li>
        ))}
      </ul>
    </Seccion>
  );
}

/** Elegir una fila con recorrido: lo dibuja y el encuadre lo muestra entero; otra vez, lo quita. */
function alternar(acciones: AccionesTablero, conductor: string | null, c: ConductorTablero | CableTablero) {
  const otro = conductor === c.id ? null : c.id;
  acciones.dibujar(otro);
  if (otro) acciones.encuadrar(c.piezas, puntosDe(c.recorrido));
}

function Conductores({ panel, acciones, conductor, filtro, quitarFiltro }: Props) {
  const [todos, setTodos] = useState(false);
  const lista = conductoresListados(panel, filtro);
  const total = panel.detalle?.conductores.length ?? 0;
  const vistos = todos || filtro ? lista : lista.slice(0, VISIBLES);
  if (filtro && !lista.length) return null; // el ítem elegido sólo toca cables de campo
  const elegir = (c: ConductorTablero) => alternar(acciones, conductor, c);
  return (
    <Seccion titulo={filtro ? `Conductores · ${lista.length} de ${total}` : `Conductores · ${total}`}>
      <ul className="tb-filas">
        {vistos.map((c) => (
          <li key={c.id}>
            <Fila principal={<Bornes c={c} />} bajo={c.origen === "declarado" ? "Largo puesto a mano" : undefined}
              cifra={largoConductor(c)} elegida={conductor === c.id} onClick={() => elegir(c)} />
          </li>
        ))}
      </ul>
      {filtro && (
        <button type="button" className="tb-enlace" onClick={quitarFiltro}>Ver los {total} conductores</button>
      )}
      {!filtro && !todos && lista.length > VISIBLES && (
        <button type="button" className="tb-enlace" onClick={() => setTodos(true)}>Ver {lista.length - VISIBLES} más</button>
      )}
    </Seccion>
  );
}

/** Los cables de campo que salen del tablero: su largo (dentro + afuera + reserva); clic → su
   recorrido en el 3D, entero en el encuadre. */
function Cables({ panel, acciones, conductor, filtro, quitarFiltro }: Props) {
  const total = panel.detalle?.cables?.length ?? 0;
  const lista = cablesListados(panel, filtro);
  if (!total || (filtro && !lista.length)) return null;
  const sinConductores = !!filtro && !conductoresListados(panel, filtro).length;
  return (
    <Seccion titulo={filtro && lista.length < total ? `Cables de campo · ${lista.length} de ${total}` : `Cables de campo · ${total}`}>
      <ul className="tb-filas">
        {lista.map((c) => (
          <li key={c.id}>
            <Fila principal={c.designacion} secundario={c.nombre} bajo={partesCable(c) || undefined}
              cifra={largoCable(c)} elegida={conductor === c.id}
              onClick={c.recorrido?.length || c.piezas.length ? () => alternar(acciones, conductor, c) : undefined} />
          </li>
        ))}
      </ul>
      {sinConductores && lista.length < total && (
        <button type="button" className="tb-enlace" onClick={quitarFiltro}>Ver los {total} cables</button>
      )}
    </Seccion>
  );
}

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="tb-seccion" aria-label={titulo}>
      <h4 className="tb-titulo">{titulo}</h4>
      {children}
    </section>
  );
}

/** Los bornes de un conductor; cada designación entera en su línea (no se corta en «-H1»). */
function Bornes({ c }: { c: ConductorTablero }) {
  return (
    <span aria-label={rotuloConductor(c)}>
      {c.puntos.map((p, i) => (
        <span key={`${p}-${i}`}>
          {i > 0 && " → "}
          <span className="tb-borne">{p}</span>
        </span>
      ))}
    </span>
  );
}

interface FilaProps {
  principal: ReactNode;
  /** Junto a lo principal, en gris («ITM 3P C16»). */
  secundario?: string;
  /** Una segunda línea, en gris y más chica («Largo puesto a mano»). */
  bajo?: string;
  cifra?: string;
  elegida?: boolean;
  onClick?: () => void;
}

function Fila({ principal, secundario, bajo, cifra: valor, elegida, onClick }: FilaProps) {
  const cuerpo = (
    <>
      <span className="tb-principal">
        {principal}
        {secundario && <span className="tb-secundario">{secundario}</span>}
        {bajo && <span className="tb-bajo">{bajo}</span>}
      </span>
      <span className="tb-cifra">{valor ?? ""}</span>
      {onClick && <ChevronRight className="tb-ir" size={14} aria-hidden="true" />}
    </>
  );
  if (!onClick) return <div className="tb-fila">{cuerpo}</div>;
  return (
    <button type="button" className={`tb-fila${elegida ? " elegida" : ""}`} onClick={onClick}
      {...(elegida !== undefined ? { "aria-pressed": elegida } : {})}>
      {cuerpo}
    </button>
  );
}
