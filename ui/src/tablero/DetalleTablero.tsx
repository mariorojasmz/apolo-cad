import { useState, type ReactNode } from "react";
import IconoSeveridad from "../diseno/IconoSeveridad";
import ItemsAtencion from "../diseno/ItemsAtencion";
import { cifra } from "../diseno/cifra";
import VerDetalle from "../ui/VerDetalle";
import type { ConductorTablero, PanelTableroOut } from "./tipos";
import { conductoresListados, itemsDeAtencion, largoConductor, perdidasDeclaradas, rotuloConductor, type AccionesTablero } from "./vista";

/* El «Detalle» del panel «Tablero» (plan V8.5 D13): lo que está bien, los conductores con su largo
   (clic → su recorrido en el 3D), las canaletas con su llenado, los aparatos y el calentamiento,
   que sigue sin evaluar. Sólo se ve a pedido; cada fila que señala algo encuadra su pieza. */

/** Cuántos conductores se ven antes de «Ver los N». */
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
  return (
    <div className="tb-detalle">
      {d.bien.length > 0 && (
        <Seccion titulo="Lo que cumple">
          <ItemsAtencion items={itemsDeAtencion(d.bien, acciones)} rotulo="Lo que cumple en el tablero" />
        </Seccion>
      )}
      <Conductores panel={panel} acciones={acciones} conductor={conductor} filtro={filtro} quitarFiltro={quitarFiltro} />
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
      <Seccion titulo="Aparatos">
        <ul className="tb-filas">
          {d.aparatos.map((a) => (
            <li key={a.designacion}>
              <Fila principal={a.designacion} secundario={a.nombre}
                onClick={a.pieza ? () => acciones.encuadrar([a.pieza!]) : undefined} />
            </li>
          ))}
        </ul>
      </Seccion>
      <Seccion titulo="Calentamiento">
        <p className="tb-calor">
          <IconoSeveridad severidad="sin_evaluar" tamano={15} />
          <span>{d.calentamiento.motivo}</span>
        </p>
        <p className="tb-nota">{perdidasDeclaradas(d.calentamiento.perdidas_W, d.calentamiento.sin_dato)}</p>
      </Seccion>
      {d.supuestos.length > 0 && (
        <VerDetalle resumen="Supuestos del cálculo">
          <ul>{d.supuestos.map((s) => <li key={s}>{s}</li>)}</ul>
        </VerDetalle>
      )}
    </div>
  );
}

function Conductores({ panel, acciones, conductor, filtro, quitarFiltro }: Omit<Props, "panel"> & { panel: PanelTableroOut }) {
  const [todos, setTodos] = useState(false);
  const lista = conductoresListados(panel, filtro);
  const total = panel.detalle?.conductores.length ?? 0;
  const vistos = todos || filtro ? lista : lista.slice(0, VISIBLES);
  const elegir = (c: ConductorTablero) => {
    const otro = conductor === c.id ? null : c.id;
    acciones.dibujar(otro);
    if (otro && c.piezas.length) acciones.encuadrar(c.piezas);
  };
  return (
    <Seccion titulo={filtro ? `Conductores · ${lista.length} de ${total}` : `Conductores · ${total}`}>
      {filtro && (
        <button type="button" className="tb-enlace" onClick={quitarFiltro}>Ver todos los conductores</button>
      )}
      <ul className="tb-filas">
        {vistos.map((c) => (
          <li key={c.id}>
            <Fila principal={rotuloConductor(c)} secundario={c.origen === "declarado" ? "escrito a mano" : undefined}
              cifra={largoConductor(c)} elegida={conductor === c.id} onClick={() => elegir(c)} />
          </li>
        ))}
      </ul>
      {!filtro && !todos && lista.length > VISIBLES && (
        <button type="button" className="tb-enlace" onClick={() => setTodos(true)}>Ver los {lista.length}</button>
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

interface FilaProps {
  principal: string;
  secundario?: string;
  cifra?: string;
  elegida?: boolean;
  onClick?: () => void;
}

function Fila({ principal, secundario, cifra: valor, elegida, onClick }: FilaProps) {
  const cuerpo = (
    <>
      <span className="tb-principal">{principal}</span>
      {secundario && <span className="tb-secundario">{secundario}</span>}
      {valor && <span className="tb-cifra">{valor}</span>}
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
