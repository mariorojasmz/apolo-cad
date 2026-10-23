import * as THREE from "three";
import { materialesDe } from "../viewport/zonas";
import { alApretar, alSoltar, colorFisico, encendido, type Accion, type EstadoMando } from "./mandos";
import type { MandoVivo, PilotoVivo } from "./protocolo";

/* Los mandos y pilotos que tienen pieza 3D (plan V8.4 D4 y D5; Bitácora de F0 § 3):
   - un mando ligado se aprieta con clic en SU pieza (raycast sobre todas las piezas visibles:
     cuenta sólo si es la primera que toca el rayo). El clic no selecciona ni gira la cámara:
     se toma en captura sobre el contenedor del canvas antes que la selección y la órbita;
   - un piloto ligado se enciende en su color FÍSICO (emisivo sobre una copia de su material;
     al terminar vuelve el original). Ningún proyecto de referencia tiene pilotos con pieza
     todavía: en la 77 los pilotos se ven en el panel. */

export interface Mandos3D {
  tick: (nowMs: number) => void;
  quitar: () => void;
}

export interface OpcionesMandos3D {
  contenedor: HTMLElement;
  canvas: HTMLCanvasElement;
  camara: () => THREE.Camera;
  meshes: Map<string, THREE.Mesh>;
  mandos: MandoVivo[];
  pilotos: PilotoVivo[];
  valor: (senal: string) => number | undefined;
  /** Estado del mando para decidir el mensaje (la seta retenida, el seccionador cerrado). */
  estado: (m: MandoVivo) => EstadoMando;
  enviar: (a: Accion, m: MandoVivo) => void;
}

const _ndc = new THREE.Vector2();
const _ray = new THREE.Raycaster();
const CADA_MS = 100;

/** El mando cuya pieza toca primero el rayo del puntero, o null. */
export function mandoBajoPuntero(
  ev: { clientX: number; clientY: number },
  canvas: HTMLCanvasElement,
  camara: THREE.Camera,
  meshes: Map<string, THREE.Mesh>,
  porPieza: Map<string, MandoVivo>,
): MandoVivo | null {
  const r = canvas.getBoundingClientRect();
  if (!r.width || !r.height) return null;
  _ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  _ray.setFromCamera(_ndc, camara);
  const visibles = [...meshes.values()].filter((m) => m.visible);
  const hit = _ray.intersectObjects(visibles, false)[0];
  if (!hit) return null;
  for (const [id, mesh] of meshes) if (mesh === hit.object) return porPieza.get(id) ?? null;
  return null;
}

export function instalarMandos3D(o: OpcionesMandos3D): Mandos3D {
  const porPieza = new Map<string, MandoVivo>();
  for (const m of o.mandos) if (m.pieza && o.meshes.has(m.pieza)) porPieza.set(m.pieza, m);
  let apretado: MandoVivo | null = null;
  let tragarClic = false;

  const onDown = (ev: PointerEvent) => {
    if (ev.button !== 0 || !porPieza.size) return;
    const m = mandoBajoPuntero(ev, o.canvas, o.camara(), o.meshes, porPieza);
    if (!m) return;
    ev.stopPropagation(); // ni selección ni órbita: es un botón de la máquina
    ev.preventDefault();
    tragarClic = true;
    const a = alApretar(m, o.estado(m));
    if (a) o.enviar(a, m);
    apretado = m;
  };
  const onUp = () => {
    if (!apretado) return;
    const a = alSoltar(apretado, o.estado(apretado));
    if (a) o.enviar(a, apretado);
    apretado = null;
  };
  const onClick = (ev: MouseEvent) => {
    if (!tragarClic) return;
    tragarClic = false;
    ev.stopPropagation();
  };
  if (porPieza.size) {
    o.contenedor.addEventListener("pointerdown", onDown, true);
    o.contenedor.addEventListener("click", onClick, true);
    window.addEventListener("pointerup", onUp, true);
  }

  // pilotos con pieza: una copia del material para encenderla en su color
  const pilotos: { p: PilotoVivo; mesh: THREE.Mesh; original: THREE.Material | THREE.Material[]; copias: THREE.MeshStandardMaterial[]; color: THREE.Color }[] = [];
  for (const p of o.pilotos) {
    const mesh = p.pieza ? o.meshes.get(p.pieza) : undefined;
    if (!mesh) continue;
    const original = mesh.material;
    const copias = materialesDe(original).map((mat) =>
      mat instanceof THREE.MeshStandardMaterial ? mat.clone() : new THREE.MeshStandardMaterial({ color: "#888" }));
    mesh.material = Array.isArray(original) ? copias : copias[0];
    pilotos.push({ p, mesh, original, copias, color: new THREE.Color(colorFisico(p.color) ?? "#f2f2ef") });
  }
  let pintadoEn = -Infinity;

  return {
    tick: (nowMs) => {
      if (!pilotos.length || nowMs - pintadoEn < CADA_MS) return;
      pintadoEn = nowMs;
      for (const { p, copias, color } of pilotos) {
        const on = encendido(o.valor(p.senal));
        for (const c of copias) {
          c.emissive.copy(on ? color : _negro);
          c.emissiveIntensity = on ? 1.6 : 0;
        }
      }
    },
    quitar: () => {
      o.contenedor.removeEventListener("pointerdown", onDown, true);
      o.contenedor.removeEventListener("click", onClick, true);
      window.removeEventListener("pointerup", onUp, true);
      onUp();
      for (const { mesh, original, copias } of pilotos) {
        mesh.material = original;
        for (const c of copias) c.dispose();
      }
    },
  };
}

const _negro = new THREE.Color(0, 0, 0);
