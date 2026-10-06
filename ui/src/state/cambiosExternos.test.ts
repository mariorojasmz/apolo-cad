import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DocumentOut, FeatureOut, Mesh, SceneOut } from "../types";
import { api } from "../api";
import { cambiosExternos, EVENTO_CAMBIOS_EXTERNOS, publicarCambiosExternos } from "./cambiosExternos";
import { useStore } from "./store";

/* Qué publica el refresco como cambio del agente (plan modo-visor, D8): sólo un refresco
   no-completo, con el mismo epoch y el mismo proyecto, que trae algo nuevo, cambiado o
   eliminado. La segunda parte prueba el cableado en `store.refresh` con la API simulada. */

vi.mock("../api", () => ({
  api: {
    scene: vi.fn(),
    sceneDelta: vi.fn(),
    kinematics: vi.fn(() => Promise.reject(new Error("sin API en el test"))),
    constraints: vi.fn(() => Promise.reject(new Error("sin API en el test"))),
  },
  connectWs: vi.fn(),
}));

const DOC: DocumentOut = {
  name: "prueba", commands: [], can_undo: false, can_redo: false, variables: [],
  configurations: [], groups: [], project_id: 1,
};
const MALLA: Mesh = { positions: [0, 0, 0, 1, 0, 0, 0, 1, 0], indices: [0, 1, 2] };

/** Pieza completa (geometría nueva o escena entera). */
function pieza(id: string, rev = 1): FeatureOut {
  return {
    id, name: `Pieza ${id}`, visible: true, color: "#888888", volume_mm3: 1000,
    bbox: { min: [0, 0, 0], max: [10, 10, 10] }, mesh: MALLA, mesh_key: null, matrix: null,
    command_id: `cmd_${id}`, command_type: "create_box", component: null, cut_length: null,
    group: null, is_guide: false, rev,
  };
}
/** Entrada `same` del delta: sin geometría. */
function igual(id: string, extra: Partial<FeatureOut> = {}): FeatureOut {
  return { ...pieza(id), mesh: null, bbox: { min: [], max: [] }, same: true, ...extra };
}
const escena = (features: FeatureOut[], epoch = "e1", project_id = 1): SceneOut =>
  ({ features, definitions: {}, document: { ...DOC, project_id }, epoch });

const PREV = escena([pieza("a"), pieza("b"), pieza("c")]);
const DELTA = escena([igual("a"), pieza("b", 2), pieza("n")]);

describe("cambiosExternos", () => {
  it("publica las nuevas, las cambiadas y las eliminadas", () => {
    expect(cambiosExternos(PREV, DELTA)).toEqual({ nuevos: ["n"], cambiados: ["b"], eliminados: ["c"] });
  });

  it("sólo eliminadas también se publica", () => {
    expect(cambiosExternos(PREV, escena([igual("a"), igual("b")])))
      .toEqual({ nuevos: [], cambiados: [], eliminados: ["c"] });
  });

  it("un refresco completo (sin escena previa) no publica", () => {
    expect(cambiosExternos(null, DELTA)).toBeNull();
  });

  it("con otro epoch (la API reinició) no publica aunque todo venga distinto", () => {
    expect(cambiosExternos(PREV, escena([pieza("a", 1), pieza("b", 1)], "e2"))).toBeNull();
  });

  it("con otro proyecto no publica", () => {
    expect(cambiosExternos(PREV, escena([pieza("a", 7)], "e1", 2))).toBeNull();
  });

  it("si nada cambió de geometría (sólo color o nombre) no publica", () => {
    const delta = escena([igual("a", { color: "#ff0000" }), igual("b", { name: "Otro" }), igual("c")]);
    expect(cambiosExternos(PREV, delta)).toBeNull();
  });
});

describe("publicarCambiosExternos", () => {
  it("despacha el evento con los cambios en el destino", () => {
    const destino = new EventTarget();
    const recibidos: unknown[] = [];
    destino.addEventListener(EVENTO_CAMBIOS_EXTERNOS, (e) => recibidos.push((e as CustomEvent).detail));
    publicarCambiosExternos(PREV, DELTA, destino);
    publicarCambiosExternos(null, DELTA, destino); // completo: nada
    expect(recibidos).toEqual([{ nuevos: ["n"], cambiados: ["b"], eliminados: ["c"] }]);
  });

  it("sin destino (node, sin window) no revienta", () => {
    expect(() => publicarCambiosExternos(PREV, DELTA, undefined)).not.toThrow();
  });
});

describe("store.refresh publica sólo el refresco no-completo", () => {
  let ventana: EventTarget;
  let recibidos: unknown[];

  beforeEach(() => {
    ventana = new EventTarget();
    recibidos = [];
    ventana.addEventListener(EVENTO_CAMBIOS_EXTERNOS, (e) => recibidos.push((e as CustomEvent).detail));
    vi.stubGlobal("window", ventana);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("refresh() con el mismo epoch publica lo que trajo el delta", async () => {
    vi.mocked(api.sceneDelta).mockResolvedValue(DELTA);
    useStore.setState({ scene: PREV });
    await useStore.getState().refresh();
    expect(recibidos).toEqual([{ nuevos: ["n"], cambiados: ["b"], eliminados: ["c"] }]);
    expect(useStore.getState().scene?.features.map((f) => f.id)).toEqual(["a", "b", "n"]);
  });

  it("refresh(true) (la reconexión) no publica nada", async () => {
    vi.mocked(api.scene).mockResolvedValue(escena([pieza("a", 9), pieza("z")]));
    useStore.setState({ scene: PREV });
    await useStore.getState().refresh(true);
    expect(recibidos).toEqual([]);
    expect(useStore.getState().scene?.features.map((f) => f.id)).toEqual(["a", "z"]);
  });
});
