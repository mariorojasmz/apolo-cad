import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { EVENTO_CAMBIOS_EXTERNOS } from "../state/cambiosExternos";
import { useStore } from "../state/store";
import type { DocumentOut, SceneOut } from "../types";
import { escucharCambiosExternos } from "./cambiosExternos";
import { useVisor } from "./estado";

/* El visor recibe los cambios externos que publica la store y los marca (plan modo-visor, D8). */

const cambio = (detail: unknown) => new CustomEvent(EVENTO_CAMBIOS_EXTERNOS, { detail });
const DOC: DocumentOut = {
  name: "prueba", commands: [], can_undo: false, can_redo: false, variables: [],
  configurations: [], groups: [], project_id: 1,
};
const escena = (project_id: number): SceneOut =>
  ({ features: [], definitions: {}, document: { ...DOC, project_id }, epoch: "e1" });

let origen: EventTarget;
let dejar: () => void;

beforeEach(() => {
  useStore.setState({ scene: escena(1) });
  useVisor.setState({ aviso: null, marcados: [], nuevas: [], pulso: 0 });
  origen = new EventTarget();
  dejar = escucharCambiosExternos(origen);
});
afterEach(() => dejar());

describe("escucharCambiosExternos", () => {
  it("un cambio externo arma el aviso, las marcas y las nuevas; las eliminadas se cuentan", () => {
    origen.dispatchEvent(cambio({ nuevos: ["n1"], cambiados: ["c2", "c3"], eliminados: ["x", "y"] }));
    const s = useVisor.getState();
    expect(s.aviso).toMatchObject({ nuevos: ["n1"], cambiados: ["c2", "c3"], eliminados: 2 });
    expect(s.marcados).toEqual(["n1", "c2", "c3"]);
    expect(s.nuevas).toEqual(["n1"]);
    expect(s.pulso).toBeGreaterThan(0);
  });

  it("al dejar de escuchar, un cambio nuevo ya no marca nada", () => {
    dejar();
    origen.dispatchEvent(cambio({ nuevos: ["n1"], cambiados: [], eliminados: [] }));
    expect(useVisor.getState().aviso).toBeNull();
  });

  it("un evento sin detalle se ignora", () => {
    origen.dispatchEvent(cambio(null));
    expect(useVisor.getState().aviso).toBeNull();
  });

  it("otro proyecto olvida las marcas; el mismo proyecto las conserva", () => {
    origen.dispatchEvent(cambio({ nuevos: ["c1"], cambiados: ["c2"], eliminados: [] }));
    useStore.setState({ scene: escena(1) }); // otra escena del MISMO proyecto
    expect(useVisor.getState().marcados).toEqual(["c1", "c2"]);
    useStore.setState({ scene: escena(2) });
    expect(useVisor.getState()).toMatchObject({ aviso: null, marcados: [], nuevas: [] });
  });
});
