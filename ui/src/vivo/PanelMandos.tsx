import { createContext, useContext, useEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { api } from "../api";
import VerDetalle from "../ui/VerDetalle";
import { abreYCierra, estadoDeMando, estadoDesdeValor, senalDeEstado, valorVisto } from "./accionar";
import { useVivo } from "./estado";
import { lecturasDe, textoLectura } from "./lecturas";
import { alApretar, alSoltar, colorFisico, encendido, esMomentaneo, girar, nombreConEstado, rotuloAccion, type Accion } from "./mandos";
import type { MandoVivo, PilotoVivo } from "./protocolo";
import { abrirSesion, accionar, reiniciarSesion } from "./sesion";
import { abrirPanel } from "./abrirPanel";
import EventosVivos from "./EventosVivos";
import FallasVivas from "./FallasVivas";
import "./vivo.css";

/* Panel «Mandos» de la máquina viva (plan V8.4 D4): el camino PRINCIPAL para manejar la
   máquina, tenga o no la botonera modelada. Sin sesión: elegir el escenario y abrirla. Con
   sesión: cada mando del tablero con su color físico (pulsador = mientras lo mantienes
   apretado; seta = queda retenida hasta liberarla), los pilotos encendidos en su color y las
   lecturas del motor, el variador, el contador y el relé de seguridad; «Provocar atasco» y el paso
   a «Señales» y «PLC». */

/** Cómo se manda la acción de un mando: por el WebSocket; el muestrario la simula. */
export const AccionarMando = createContext<(a: Accion, m: MandoVivo) => void>(accionar);

export default function PanelMandos() {
  const fase = useVivo((s) => s.fase);
  const problema = useVivo((s) => s.problema);
  const escenario = useVivo((s) => s.escenario);
  return (
    <section className="history panel-mandos">
      {fase === "cerrada" && <Apertura />}
      {fase === "abriendo" && <p className="hint">Preparando la simulación de «{escenario}»…</p>}
      {fase === "error" && problema && (
        <div className="mandos-problema">
          <p className="estado-aviso">{problema.texto}</p>
          <div className="kin-actions">
            <button className="primary" onClick={() => void reiniciarSesion(!!problema.reemplazable)}>
              {problema.reemplazable ? "Reemplazar la otra sesión" : "Abrir de nuevo"}
            </button>
            <button onClick={() => useVivo.getState().set({ fase: "cerrada", problema: null })}>Elegir otro escenario</button>
          </div>
          {problema.detalle && (
            <VerDetalle resumen="Detalle técnico">
              <p className="hint">{problema.detalle}</p>
            </VerDetalle>
          )}
        </div>
      )}
      {(fase === "corriendo" || fase === "pausa" || fase === "fin") && <Tablero />}
    </section>
  );
}

function Apertura() {
  const [nombres, setNombres] = useState<string[] | null>(null);
  const [elegido, setElegido] = useState("");
  const [fallo, setFallo] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    api.escenarios()
      .then((r) => {
        if (!vivo) return;
        const ns = r.escenarios.map((e) => e.nombre);
        setNombres(ns);
        setElegido(ns.includes("marcha") ? "marcha" : ns[0] ?? "");
      })
      .catch((e) => vivo && setFallo(e instanceof Error ? e.message : String(e)));
    return () => {
      vivo = false;
    };
  }, []);
  if (fallo) return <p className="estado-aviso">No pudimos leer los escenarios: {fallo}</p>;
  if (!nombres) return <p className="hint">Buscando los escenarios…</p>;
  if (!nombres.length) {
    return (
      <p className="hint">
        Aquí vas a manejar la máquina con los botones de su tablero. Hace falta un escenario: pídele al agente que
        declare uno.
      </p>
    );
  }
  return (
    <div className="mandos-apertura">
      <h3>Máquina viva</h3>
      <p className="hint">Aprietas sus botones y la ves andar en tiempo real.</p>
      <div className="kin-actions">
        {nombres.length > 1 && (
          <select value={elegido} onChange={(e) => setElegido(e.target.value)} aria-label="Escenario">
            {nombres.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        )}
        <button className="primary" disabled={!elegido} onClick={() => void abrirSesion(elegido)}>
          Abrir la sesión viva
        </button>
      </div>
    </div>
  );
}

function Tablero() {
  const inicio = useVivo((s) => s.inicio);
  const rechazo = useVivo((s) => s.rechazo);
  const fase = useVivo((s) => s.fase);
  if (!inicio) return null;
  const quieto = fase === "fin";
  return (
    <>
      {rechazo && <p className="estado-aviso">{rechazo}</p>}
      <ListaMandos quieto={quieto} />
      {inicio.pilotos.length > 0 && (
        <>
          <h3>Pilotos</h3>
          <ul className="lista-mandos">
            {inicio.pilotos.map((p) => <FilaPiloto key={p.designacion} p={p} />)}
          </ul>
        </>
      )}
      <Lecturas />
      <EventosVivos quieto={quieto} />
      <FallasVivas quieto={quieto} />
      <h3>Medir</h3>
      <div className="kin-actions">
        <button onClick={() => void abrirPanel("senales")}>Ver las señales</button>
        <button onClick={() => void abrirPanel("plc")}>Ver el programa del PLC</button>
      </div>
    </>
  );
}

/** «Mandos»: cada mando del tablero con su control. */
export function ListaMandos({ quieto }: { quieto: boolean }) {
  const mandos = useVivo((s) => s.inicio?.mandos);
  if (!mandos) return null;
  return (
    <>
      <h3>Mandos</h3>
      {mandos.length ? (
        <ul className="lista-mandos">
          {mandos.map((m) => <FilaMando key={m.designacion} m={m} quieto={quieto} />)}
        </ul>
      ) : (
        <p className="hint">El tablero no tiene mandos que se aprieten.</p>
      )}
    </>
  );
}

/** El color físico como variables CSS de la tapa (y el fondo amarillo de la seta). */
function tapa(color: string | null, fondo?: string): CSSProperties {
  return {
    "--tapa": colorFisico(color) ?? "var(--panel3)",
    "--fondo-tapa": colorFisico(fondo) ?? "transparent",
  } as CSSProperties;
}

function FilaMando({ m, quieto }: { m: MandoVivo; quieto: boolean }) {
  // selectores PRIMITIVOS: un objeto nuevo por lectura re-renderizaría sin fin
  const senal = senalDeEstado(m);
  const v = useVivo((s) => (senal ? valorVisto(s, senal) : undefined));
  const estado = estadoDesdeValor(m, v);
  const accionado = v !== undefined && v >= 0.5 && !abreYCierra(m);
  return (
    <li className="fila-mando">
      <span className={`tapa-mando tapa-${m.tipo}${accionado ? " accionada" : ""}`} style={tapa(m.color, m.fondo)} aria-hidden />
      <div className="fila-mando-nombre">
        <strong>{m.designacion}</strong>
        <span className="hint">{nombreConEstado(m, estado)}{m.pieza ? " · también con clic en el 3D" : ""}</span>
      </div>
      <div className="fila-mando-control">
        {m.tipo === "selector" ? (
          <Selector m={m} quieto={quieto} />
        ) : m.tipo === "pulsador" ? (
          <>
            {(m.actuadores?.length ?? 0) > 1
              ? m.actuadores!.map((a) => <BotonMando key={a} m={m} actuador={a} rotulo={a} quieto={quieto} />)
              : <BotonMando m={m} rotulo={rotuloAccion(m, estado)} quieto={quieto} activo={accionado} />}
            {m.potenciometro && <Potenciometro m={m} quieto={quieto} />}
          </>
        ) : (
          <BotonMando m={m} rotulo={rotuloAccion(m, estado)} quieto={quieto}
            activo={m.tipo === "seta" ? estado.retenida : abreYCierra(m) ? estado.cerrado === false : undefined} />
        )}
      </div>
    </li>
  );
}

/** Un botón que se comporta como el mando: el pulsador con resorte vuelve al soltar. */
function BotonMando({ m, rotulo, actuador, quieto, activo }: {
  m: MandoVivo; rotulo: string; actuador?: string; quieto: boolean; activo?: boolean;
}) {
  const accionar = useContext(AccionarMando);
  const [abajo, setAbajo] = useState(false);
  const abajoRef = useRef(false); // el soltar puede llegar dos veces antes del re-render
  const apretar = () => {
    const a = alApretar(m, { ...estadoDeMando(m, useVivo.getState()), actuador });
    if (a) accionar(a, m);
    abajoRef.current = true;
    setAbajo(true);
  };
  const soltar = () => {
    if (!abajoRef.current) return;
    abajoRef.current = false;
    setAbajo(false);
    const a = alSoltar(m, { actuador });
    if (a) accionar(a, m);
  };
  const tecla = (e: KeyboardEvent, bajar: boolean) => {
    if (e.key !== " " && e.key !== "Enter") return;
    e.preventDefault();
    if (bajar && !e.repeat && !abajoRef.current) apretar();
    if (!bajar) soltar();
  };
  return (
    <button
      type="button"
      className={`boton-mando${abajo || activo ? " apretado" : ""}`}
      disabled={quieto}
      aria-pressed={activo ?? abajo}
      aria-label={`${rotulo} ${m.designacion}`}
      onPointerDown={(e) => {
        if (e.button !== 0) return;
        try {
          e.currentTarget.setPointerCapture(e.pointerId); // soltar fuera del botón también suelta
        } catch {
          /* puntero sin captura (sintético): basta el pointerup */
        }
        apretar();
      }}
      onPointerUp={soltar}
      onPointerCancel={soltar}
      onLostPointerCapture={esMomentaneo(m) ? soltar : undefined}
      onKeyDown={(e) => tecla(e, true)}
      onKeyUp={(e) => tecla(e, false)}
    >
      {rotulo}
    </button>
  );
}

function Selector({ m, quieto }: { m: MandoVivo; quieto: boolean }) {
  const accionar = useContext(AccionarMando);
  const [pos, setPos] = useState<string | null>(null);
  return (
    <div className="selector-mando" role="group" aria-label={`Posiciones de ${m.designacion}`}>
      {(m.posiciones ?? []).map((p) => (
        <button key={p} type="button" disabled={quieto} aria-pressed={pos === p} className={pos === p ? "apretado" : ""}
          onClick={() => {
            setPos(p);
            accionar(girar(m, p), m);
          }}>
          {p}
        </button>
      ))}
    </div>
  );
}

function Potenciometro({ m, quieto }: { m: MandoVivo; quieto: boolean }) {
  const accionar = useContext(AccionarMando);
  const valor = useVivo((s) => s.lecturas[`${m.designacion}.potenciometro`]);
  return (
    <input type="range" min={0} max={1} step={0.01} disabled={quieto} value={valor ?? 0}
      aria-label={`Potenciómetro de ${m.designacion}`}
      onChange={(e) => accionar(girar(m, Number(e.target.value)), m)} />
  );
}

function FilaPiloto({ p }: { p: PilotoVivo }) {
  const on = useVivo((s) => encendido(s.lecturas[p.senal]));
  return (
    <li className="fila-mando">
      <span className={`lampara${on ? " encendida" : ""}`} style={tapa(p.color)} aria-hidden />
      <div className="fila-mando-nombre">
        <strong>{p.designacion}</strong>
        <span className="hint">Piloto</span>
      </div>
      <span className="estado-piloto">{on ? "Encendido" : "Apagado"}</span>
    </li>
  );
}

/** «Lecturas»: lo que mide cada aparato (`lecturas.ts`) y su falla, si el aparato la publica. */
export function Lecturas() {
  const inicio = useVivo((s) => s.inicio);
  const lecturas = useVivo((s) => s.lecturas);
  const textos = useVivo((s) => s.textos);
  if (!inicio) return null;
  const filas = lecturasDe(inicio, Object.keys(lecturas).length ? Object.keys(lecturas) : inicio.senales);
  if (!filas.length) return null;
  return (
    <>
      <h3>Lecturas</h3>
      <ul className="lista-mandos">
        {filas.map((l) => {
          const falla = textos[`${l.designacion}.falla`];
          const nota = textoLectura(l, (s) => lecturas[s], true);
          return (
            <li key={l.designacion} className="fila-mando fila-lectura">
              <div className="fila-mando-nombre">
                <strong>{l.designacion}</strong>
                <span className="hint">{l.rotulo}</span>
              </div>
              <span className="valor-lectura">
                {textoLectura(l, (s) => lecturas[s])}
              </span>
              {nota && <span className="hint nota-lectura">{nota}</span>}
              {falla && <span className="estado-aviso falla-lectura">Falla: {falla}</span>}
            </li>
          );
        })}
      </ul>
    </>
  );
}
