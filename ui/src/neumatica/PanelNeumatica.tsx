import { useEffect, useMemo, useState } from "react";
import { useStore } from "../state/store";
import { pedirEncuadre } from "../viewport/pedirEncuadre";
import { useVivo } from "../vivo/estado";
import { elegidosPor, type Lector } from "./esquema";
import { cargarNeumatica, useNeumatica } from "./estado";
import type { SimboloEsquema } from "./tipos";
import VacioNeumatica from "./VacioNeumatica";
import VistaNeumatica from "./VistaNeumatica";

/* Panel «Neumática» (plan V8.9 D12): lo que el agente leyó del circuito de aire, para que la
   persona lo evalúe en el visor. Lee la API (`estado.ts`) cada vez que el documento cambia; el
   clic en un ítem o en un símbolo vuela la cámara a sus piezas y las selecciona (`pedirEncuadre`),
   y lo elegido en el 3D se marca en el esquema. Con la sesión viva abierta, el esquema lee sus
   señales (a lo sumo 10 veces por segundo, las de `useVivo`). */

export default function PanelNeumatica() {
  const scene = useStore((s) => s.scene);
  const panel = useNeumatica((s) => s.panel);
  const leido = useNeumatica((s) => s.leido);
  const error = useNeumatica((s) => s.error);
  const seleccion = useStore((s) => s.selection);
  const [aMano, setAMano] = useState<string | null>(null);
  const fase = useVivo((s) => s.fase);
  const vivo = fase === "corriendo" || fase === "pausa" || fase === "fin";
  const lecturas = useVivo((s) => (vivo ? s.lecturas : null));
  const textos = useVivo((s) => (vivo ? s.textos : null));

  // el documento cambió (también un cambio del agente): se vuelve a leer, sin martillar la API
  useEffect(() => {
    const t = window.setTimeout(() => void cargarNeumatica(), 250);
    return () => window.clearTimeout(t);
  }, [scene]);

  const simbolos = panel?.esquema?.simbolos;
  const elegidos = useMemo(() => {
    const s = elegidosPor(simbolos ?? [], seleccion);
    if (aMano) s.add(aMano);
    return s;
  }, [simbolos, seleccion, aMano]);
  const lector: Lector | null = useMemo(() => (lecturas && textos ? {
    num: (n) => lecturas[n],
    texto: (n) => textos[n],
  } : null), [lecturas, textos]);

  if (!panel) {
    if (error) return <section className="history"><p className="estado-aviso">No pudimos leer el circuito de aire: {error}</p></section>;
    if (!leido) return <section className="history"><p className="hint">Leyendo el circuito de aire…</p></section>;
    return null;
  }
  if (!panel.hay_aire) return <section className="history"><VacioNeumatica /></section>;

  const encuadrar = (piezas: readonly string[]) => {
    if (piezas.length) pedirEncuadre(piezas, { animar: true, seleccionar: true });
  };
  const elegirSimbolo = (s: SimboloEsquema) => {
    // un aparato sin pieza 3D (una válvula sin ligar) se marca sólo en el esquema
    setAMano(s.piezas.length ? null : s.designacion);
    encuadrar(s.piezas);
  };
  return (
    <section className="history panel-tablero">
      <VistaNeumatica panel={panel} lector={lector} elegidos={elegidos} onEncuadrar={encuadrar}
        onElegirSimbolo={elegirSimbolo} />
    </section>
  );
}
