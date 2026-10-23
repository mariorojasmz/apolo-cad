import { describe, expect, it } from "vitest";
import { podarLayout } from "./podarLayout";

/* Un layout guardado con el panel de una extensión que este bundle ya no trae (plan
   núcleo-abierto-extensiones-privadas, D5): se quita antes de restaurar y el resto se conserva. */

const CONOCIDOS = new Set(["viewport", "tree", "properties", "bom"]);
const conocido = (c: string) => CONOCIDOS.has(c);

/** Lo que guarda Dockview (`toJSON`): viewport al centro, árbol a la izquierda y, abajo, un grupo
   con BOM y el panel de la extensión; además, un flotante sólo con el de la extensión. */
function guardado() {
  return {
    grid: {
      root: {
        type: "branch",
        data: [
          { type: "leaf", data: { id: "1", views: ["tree"], activeView: "tree" }, size: 200 },
          {
            type: "branch",
            data: [
              { type: "leaf", data: { id: "2", views: ["viewport"], activeView: "viewport" }, size: 500 },
              {
                type: "leaf",
                data: {
                  id: "3", views: ["hola.saludo", "bom"], activeView: "hola.saludo",
                  tabGroups: [{ id: "t", collapsed: false, panelIds: ["hola.saludo", "bom"] }],
                },
                size: 200,
              },
            ],
            size: 600,
          },
        ],
        size: 800,
      },
      width: 800, height: 700, orientation: "HORIZONTAL",
    },
    panels: {
      tree: { id: "tree", contentComponent: "tree", title: "Árbol" },
      viewport: { id: "viewport", contentComponent: "viewport", tabComponent: "locked", title: "Vista 3D" },
      bom: { id: "bom", contentComponent: "bom", title: "BOM" },
      "hola.saludo": { id: "hola.saludo", contentComponent: "hola.saludo", title: "Hola" },
      "hola.otro": { id: "hola.otro", contentComponent: "hola.otro", title: "Otro" },
    },
    floatingGroups: [{ data: { id: "4", views: ["hola.otro"], activeView: "hola.otro" }, position: { top: 0, left: 0 } }],
    activeGroup: "3",
  };
}

describe("layout guardado con un panel que ya no existe", () => {
  it("sin paneles desconocidos devuelve el mismo layout", () => {
    const l = guardado();
    const { layout, quitados } = podarLayout(l, () => true);
    expect(layout).toBe(l);
    expect(quitados).toEqual([]);
  });

  it("quita el panel de la extensión de `panels`, de su grupo y de sus pestañas", () => {
    const original = guardado();
    const { layout, quitados } = podarLayout(original, conocido);
    expect(quitados.sort()).toEqual(["hola.otro", "hola.saludo"]);
    const l = layout as ReturnType<typeof guardado>;
    expect(Object.keys(l.panels).sort()).toEqual(["bom", "tree", "viewport"]);
    const grupo = l.grid.root.data[1].data[1].data as { views: string[]; activeView: string; tabGroups: { panelIds: string[] }[] };
    expect(grupo.views).toEqual(["bom"]);
    expect(grupo.activeView).toBe("bom"); // el activo era el quitado: pasa al primero que queda
    expect(grupo.tabGroups[0].panelIds).toEqual(["bom"]);
    expect(l.floatingGroups[0].data.views).toEqual([]);
    expect("activeView" in l.floatingGroups[0].data).toBe(false);
    // lo demás, intacto; y el guardado original no se toca
    expect(l.grid.root.data[0].data).toEqual({ id: "1", views: ["tree"], activeView: "tree" });
    expect(l.activeGroup).toBe("3");
    expect(Object.keys(original.panels)).toHaveLength(5);
  });

  it("un panel sin componente se quita (Dockview lo montaría como «unknown»)", () => {
    const l = guardado();
    (l.panels as Record<string, unknown>).raro = { id: "raro", title: "?" };
    expect(podarLayout(l, () => true).quitados).toEqual(["raro"]);
  });

  it("lee el componente del formato viejo (`view.content.id`)", () => {
    const l = guardado();
    (l.panels as Record<string, unknown>).bom = { id: "bom", view: { content: { id: "bom" } } };
    expect(podarLayout(l, conocido).quitados).not.toContain("bom");
  });

  it("lo que no tiene forma de layout se devuelve igual", () => {
    for (const x of [null, 3, "x", [], { grid: {} }]) expect(podarLayout(x, conocido)).toEqual({ layout: x, quitados: [] });
  });
});
