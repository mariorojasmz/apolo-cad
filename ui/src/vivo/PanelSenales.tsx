import { useMemo, useState } from "react";
import { ChartLine, Gauge } from "lucide-react";
import NombreAparato from "../diseno/NombreAparato";
import { abrirPanel } from "./abrirPanel";
import { arbolDeSenales, filtrarArbol, textosDelArbol, type RamaSenales } from "./arbolSenales";
import { useVivo } from "./estado";
import { alternarMultimetro, alternarOsciloscopio, useInstrumentos } from "./medicion";
import { colorDato } from "./paleta";
import { useTiposPlc } from "./tiposPlc";
import { leerValor, magnitud, medidaDe } from "./unidades";
import { manualPersona, posicionPersona } from "../neumatica/manual";
import { rotuloAire } from "../neumatica/senales";
import "./vivo.css";

/* Panel «Señales» de la máquina viva (plan V8.4 D7): el árbol del tablero, dispositivo →
   señales, con el valor de cada una. Cada señal se ancla al MULTÍMETRO o se suma al
   OSCILOSCOPIO (los dos van sobre el 3D, `Instrumentos.tsx`). */

/** `filtroInicial`: lo que arranca escrito en el buscador (el muestrario, para su captura). */
export default function PanelSenales({ filtroInicial = "" }: { filtroInicial?: string }) {
  const fase = useVivo((s) => s.fase);
  if (fase !== "corriendo" && fase !== "pausa" && fase !== "fin") {
    return (
      <section className="history panel-mandos">
        <p className="hint">Aquí vas a ver lo que mide la máquina mientras corre: abre la sesión viva para empezar.</p>
        <div className="kin-actions">
          <button className="primary" onClick={() => void abrirPanel("mandos")}>Abrir la sesión viva</button>
        </div>
      </section>
    );
  }
  return <Arbol filtroInicial={filtroInicial} />;
}

function Arbol({ filtroInicial }: { filtroInicial: string }) {
  const inicio = useVivo((s) => s.inicio);
  const n = useVivo((s) => Object.keys(s.lecturas).length); // primitivo: llegan señales nuevas
  const nt = useVivo((s) => Object.keys(s.textos).length);
  const [filtro, setFiltro] = useState(filtroInicial);
  const { ramas, deTexto } = useMemo(() => {
    if (!inicio) return { ramas: [], deTexto: new Set<string>() };
    const st = useVivo.getState();
    const textos = textosDelArbol(inicio, Object.keys(st.textos)); // la posición de las válvulas (V8.9)
    return { ramas: arbolDeSenales(inicio, [...inicio.senales, ...Object.keys(st.lecturas), ...textos]),
      deTexto: new Set(textos) };
  }, [inicio, n, nt]); // `n`, `nt`: el árbol crece con las señales que llegan después
  const vistas = filtrarArbol(ramas, filtro);
  const tipos = useTiposPlc();
  return (
    <section className="history panel-mandos panel-senales">
      <input type="search" value={filtro} onChange={(e) => setFiltro(e.target.value)}
        placeholder="Ejemplo: -M1 o rpm" aria-label="Buscar una señal" />
      {!vistas.length && <p className="hint">Ninguna señal coincide con «{filtro}».</p>}
      {vistas.map((r) => <Rama key={r.clave} r={r} abierta={!!filtro.trim()} tipos={tipos} deTexto={deTexto} />)}
    </section>
  );
}

function Rama({ r, abierta, tipos, deTexto }: {
  r: RamaSenales; abierta: boolean; tipos: Map<string, string>; deTexto: ReadonlySet<string>;
}) {
  const valvulas = useVivo((s) => s.inicio?.valvulas);
  const lados = (senal: string) => valvulas?.find((v) => senal.startsWith(`${v.designacion}.`))?.lados ?? [];
  return (
    <details className="rama-senales" open={abierta || undefined}>
      <summary>
        {/* «Seguridad del recipiente -K3»: lo que hace, con la designación detrás (nombres-por-funcion
            D13). Sin la cuenta de señales a la derecha (F5b): en este panel la derecha es el VALOR, y
            un número suelto ahí se leía como una lectura; se ven al abrir la fila. */}
        <span className="cabeza-aparato">
          <NombreAparato a={{ designacion: r.designacion ?? r.titulo, rotulo: r.designacion ? r.titulo : undefined }} />
        </span>
      </summary>
      <ul className="lista-senales">
        {r.senales.map((s) => deTexto.has(s)
          ? <FilaTexto key={s} senal={s} lados={lados(s)} />
          : <FilaSenal key={s} senal={s} agrupada={r.clave.startsWith("#")} tipo={tipos.get(s)} />)}
      </ul>
    </details>
  );
}

/** Una señal de texto (la posición de una válvula, su accionamiento manual): su valor en
 *  palabras, sin multímetro ni osciloscopio. */
function FilaTexto({ senal, lados }: { senal: string; lados: readonly string[] }) {
  const v = useVivo((s) => s.textos[senal]);
  const m = magnitud(senal);
  const valor = m === "manual" ? manualPersona(v) : m === "posicion" ? posicionPersona(v, lados) : v ?? "—";
  return (
    <li className="fila-senal">
      <span className="nombre-senal" title={senal}>{rotuloAire(m) ?? m}</span>
      <span className="valor-senal">{valor}</span>
    </li>
  );
}

function FilaSenal({ senal, agrupada, tipo }: { senal: string; agrupada: boolean; tipo?: string }) {
  const v = useVivo((s) => s.lecturas[senal]);
  const enMultimetro = useInstrumentos((s) => s.multimetro === senal);
  const color = useInstrumentos((s) => s.trazos.find((x) => x.senal === senal)?.color ?? -1);
  const m = medidaDe(senal, tipo);
  return (
    <li className="fila-senal">
      <span className="nombre-senal" title={senal}>{agrupada ? senal : rotuloAire(magnitud(senal)) ?? magnitud(senal)}</span>
      <span className="valor-senal">{leerValor(v, m)}</span>
      <button type="button" className={`inst-icono${enMultimetro ? " apretado" : ""}`} aria-pressed={enMultimetro}
        aria-label={`${enMultimetro ? "Soltar" : "Anclar"} ${senal} ${enMultimetro ? "del" : "al"} multímetro`}
        title="Multímetro" onClick={() => alternarMultimetro(senal)}>
        <Gauge size={14} />
      </button>
      <button type="button" className={`inst-icono${color >= 0 ? " apretado" : ""}`} aria-pressed={color >= 0}
        aria-label={`${color >= 0 ? "Quitar" : "Sumar"} ${senal} ${color >= 0 ? "del" : "al"} osciloscopio`}
        title="Osciloscopio" onClick={() => alternarOsciloscopio(senal)}>
        {color >= 0 ? <span className="muestra-color" style={{ background: colorDato(color) }} /> : <ChartLine size={14} />}
      </button>
    </li>
  );
}
