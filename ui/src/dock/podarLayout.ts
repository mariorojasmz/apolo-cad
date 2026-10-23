/* El layout guardado de Dockview puede traer un panel que este bundle ya no tiene: el de una
   extensión que se quitó, o el de otra UI servida en el mismo origen (plan
   núcleo-abierto-extensiones-privadas, D5). Dockview no lo rechaza al restaurar: lo monta con un
   componente `undefined` y React revienta al dibujarlo. Aquí se quita ANTES de `fromJSON`; el
   resto del layout se conserva. Lógica pura, sin Dockview: se prueba sola. */

type Json = Record<string, unknown>;

const esObjeto = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);

/** El componente de un panel serializado (`contentComponent`, o `view.content.id` del formato viejo). */
function componenteDe(panel: unknown): string | undefined {
  if (!esObjeto(panel)) return undefined;
  if (typeof panel.contentComponent === "string") return panel.contentComponent;
  const view = panel.view;
  const content = esObjeto(view) ? view.content : undefined;
  return esObjeto(content) && typeof content.id === "string" ? content.id : undefined;
}

/** Quita los ids de `fuera` de cada grupo (`views`, `activeView`) y de cada grupo de pestañas
   (`panelIds`), en todo el árbol: grilla, flotantes, ventanas emergentes y bordes. */
function podarReferencias(nodo: unknown, fuera: Set<string>): unknown {
  if (Array.isArray(nodo)) return nodo.map((n) => podarReferencias(n, fuera));
  if (!esObjeto(nodo)) return nodo;
  const out: Json = {};
  for (const [k, v] of Object.entries(nodo)) out[k] = podarReferencias(v, fuera);
  if (Array.isArray(out.views)) {
    out.views = out.views.filter((id) => !fuera.has(String(id)));
    if (typeof out.activeView === "string" && fuera.has(out.activeView)) {
      const primero = (out.views as unknown[])[0];
      if (typeof primero === "string") out.activeView = primero;
      else delete out.activeView;
    }
  }
  if (Array.isArray(out.panelIds)) out.panelIds = out.panelIds.filter((id) => !fuera.has(String(id)));
  return out;
}

export interface LayoutPodado {
  /** El layout sin los paneles desconocidos (el mismo objeto si no había ninguno). */
  layout: unknown;
  /** Ids de los paneles que se quitaron. */
  quitados: string[];
}

/** Quita del layout serializado los paneles cuyo componente no reconoce `conocido`. Un layout que
   no tiene la forma esperada se devuelve igual: `fromJSON` decide (y `DockShell` cae al layout
   por defecto si falla). */
export function podarLayout(layout: unknown, conocido: (componente: string) => boolean): LayoutPodado {
  if (!esObjeto(layout) || !esObjeto(layout.panels)) return { layout, quitados: [] };
  const quitados = Object.entries(layout.panels)
    .filter(([, panel]) => {
      const c = componenteDe(panel);
      return c === undefined || !conocido(c);
    })
    .map(([id]) => id);
  if (!quitados.length) return { layout, quitados };
  const fuera = new Set(quitados);
  const podado = podarReferencias(layout, fuera) as Json;
  podado.panels = Object.fromEntries(Object.entries(layout.panels).filter(([id]) => !fuera.has(id)));
  return { layout: podado, quitados };
}
