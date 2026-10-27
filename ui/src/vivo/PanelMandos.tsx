import { useEffect, useState } from "react";
import { api } from "../api";
import Veredicto from "../diseno/Veredicto";
import Pista from "../ui/Pista";
import VerDetalle from "../ui/VerDetalle";
import { useVivo } from "./estado";
import { CabezaAparato, FilaMando, FilaPiloto, leidasDe } from "./FilaMando";
import { lecturasDe, textoLectura } from "./lecturas";
import { gruposDeMandos, veredictoMandos } from "./nombresMandos";
import { abrirSesion, reiniciarSesion } from "./sesion";
import { abrirPanel } from "./abrirPanel";
import EventosVivos from "./EventosVivos";
import FallasVivas from "./FallasVivas";
import AccionamientoManual from "../neumatica/AccionamientoManual";
import "./vivo.css";
import "./mandos.css";

export { AccionarMando } from "./FilaMando";

/* Panel «Mandos» de la máquina viva (plan V8.4 D4): el camino PRINCIPAL para manejar la
   máquina, tenga o no la botonera modelada. Sin sesión: elegir el escenario y abrirla. Con
   sesión (plan nombres-por-funcion D9–D13): arriba el veredicto (sólo hechos leídos de las
   señales) y, una vez, que también se accionan en el 3D; después cada mando por lo que HACE
   —agrupados por propósito si son más de 5—, los pilotos y las lecturas, con la designación
   chica detrás; «Provocar atasco», el accionamiento manual de las electroválvulas (plegado, V8.9
   D12) y el paso a «Señales» y «PLC». La fila vive en `FilaMando.tsx`. */

/** El título humanizado de cada escenario («Ciclo nominal»), para «Preparando…» mientras abre. */
const titulos = new Map<string, string>();

export default function PanelMandos() {
  const fase = useVivo((s) => s.fase);
  const problema = useVivo((s) => s.problema);
  const escenario = useVivo((s) => s.escenario);
  return (
    <section className="history panel-mandos">
      {fase === "cerrada" && <Apertura />}
      {fase === "abriendo" && (
        <p className="hint">Preparando la simulación de «{(escenario && titulos.get(escenario)) || escenario}»…</p>
      )}
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
  const [escenarios, setEscenarios] = useState<{ nombre: string; titulo?: string }[] | null>(null);
  const [elegido, setElegido] = useState("");
  const [fallo, setFallo] = useState<string | null>(null);
  useEffect(() => {
    let vivo = true;
    api.escenarios()
      .then((r) => {
        if (!vivo) return;
        const es = r.escenarios;
        for (const e of es) if (e.titulo) titulos.set(e.nombre, e.titulo);
        setEscenarios(es);
        setElegido(es.some((e) => e.nombre === "marcha") ? "marcha" : es[0]?.nombre ?? "");
      })
      .catch((e) => vivo && setFallo(e instanceof Error ? e.message : String(e)));
    return () => {
      vivo = false;
    };
  }, []);
  if (fallo) return <p className="estado-aviso">No pudimos leer los escenarios: {fallo}</p>;
  if (!escenarios) return <p className="hint">Buscando los escenarios…</p>;
  if (!escenarios.length) {
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
        {escenarios.length > 1 && (
          <select value={elegido} onChange={(e) => setElegido(e.target.value)} aria-label="Escenario">
            {escenarios.map((e) => <option key={e.nombre} value={e.nombre}>{e.titulo || e.nombre}</option>)}
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
      <Pilotos />
      <Lecturas />
      <EventosVivos quieto={quieto} />
      <FallasVivas quieto={quieto} />
      <AccionamientoManual quieto={quieto} />
      <h3>Medir</h3>
      <div className="kin-actions">
        <button onClick={() => void abrirPanel("senales")}>Ver las señales</button>
        <button onClick={() => void abrirPanel("plc")}>Ver el programa del PLC</button>
      </div>
    </>
  );
}

/** «Mandos»: el veredicto, la pista del 3D y cada mando con su control, en grupos si son más de 5.
 *  El veredicto (D12, F5b) dice la causa y la acción siguiente, y su control va destacado en su
 *  fila (`paso`). */
export function ListaMandos({ quieto }: { quieto: boolean }) {
  const inicio = useVivo((s) => s.inicio);
  const lecturas = useVivo((s) => s.lecturas);
  const textos = useVivo((s) => s.textos);
  const mandos = inicio?.mandos;
  if (!inicio || !mandos) return null;
  if (!mandos.length) {
    return (
      <>
        <h3>Mandos</h3>
        <p className="hint">El tablero no tiene mandos que se aprieten.</p>
      </>
    );
  }
  const v = veredictoMandos(inicio, leidasDe({ lecturas, textos }));
  const paso = v?.paso;
  return (
    <>
      {v && <Veredicto severidad={v.severidad} frase={v.frase} nota={v.nota} />}
      {mandos.some((m) => m.pieza) && <Pista>También los accionas con clic en el 3D.</Pista>}
      {gruposDeMandos(mandos).map((g) => (
        <div key={g.clave} className="grupo-mandos">
          <h3>{g.titulo}</h3>
          <ul className="lista-mandos">
            {g.mandos.map((m) => (
              <FilaMando key={m.designacion} m={m} quieto={quieto}
                paso={paso?.designacion === m.designacion ? paso : undefined} />
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

/** «Pilotos»: cada lámpara por lo que avisa, con su color físico y si está encendida. */
export function Pilotos() {
  const pilotos = useVivo((s) => s.inicio?.pilotos);
  if (!pilotos?.length) return null;
  return (
    <>
      <h3>Pilotos</h3>
      <ul className="lista-mandos">
        {pilotos.map((p) => <FilaPiloto key={p.designacion} p={p} />)}
      </ul>
    </>
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
              <CabezaAparato a={l} />
              {/* cada parte («Carrera 200 mm», «avance 6,0 bar») entera: si no cabe, baja la parte */}
              <span className="valor-lectura">
                {textoLectura(l, (s) => lecturas[s]).split(" · ").map((p, i) => (
                  <span key={i}>{i > 0 && " · "}<span className="parte-lectura">{p}</span></span>
                ))}
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
