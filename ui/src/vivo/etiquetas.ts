import * as THREE from "three";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { textoLectura, type Lectura } from "./lecturas";
import "./vivo.css";

/* Datos vivos sobre el 3D (plan V8.4 D5): una etiqueta HTML (`CSS2DRenderer`) sobre la pieza de
   cada dispositivo que la tenga —motor: rpm e I; variador: Hz; el contador del PLC— con su
   designación y su valor, actualizada a ~10 Hz. Las etiquetas viven en una escena PROPIA (no
   en la del modelo: el GTAO y la grabación no las ven) y su capa no recibe clics. Un
   dispositivo sin pieza no tiene etiqueta: su lectura está en el panel «Mandos». Una lectura
   `soloElegida` (el cilindro, V8.9 D12) se ve sólo mientras `elegida` lo diga (su pieza
   seleccionada). */

const CADA_MS = 100;
/** Cuánto por encima de la pieza va la etiqueta (mm). */
const ALTO_MM = 60;

export interface EtiquetasVivas {
  tick: (nowMs: number, camara: THREE.Camera) => void;
  quitar: () => void;
}

interface Etiqueta {
  lectura: Lectura;
  valor: HTMLSpanElement;
  obj: CSS2DObject;
}

const _caja = new THREE.Box3();

export function crearEtiquetas(
  contenedor: HTMLElement,
  meshes: Map<string, THREE.Mesh>,
  lecturas: Lectura[],
  valor: (senal: string) => number | undefined,
  elegida: (l: Lectura) => boolean = () => true,
): EtiquetasVivas {
  const escena = new THREE.Scene();
  const render = new CSS2DRenderer();
  const dom = render.domElement;
  dom.className = "etiquetas-vivas";
  contenedor.appendChild(dom);
  const etiquetas: Etiqueta[] = [];
  for (const l of lecturas) {
    const mesh = l.pieza ? meshes.get(l.pieza) : undefined;
    if (!mesh || !mesh.visible) continue;
    mesh.updateMatrixWorld();
    _caja.setFromObject(mesh);
    if (_caja.isEmpty()) continue;
    const div = document.createElement("div");
    div.className = "etiqueta-viva";
    const des = document.createElement("strong");
    des.textContent = l.designacion;
    const val = document.createElement("span");
    div.append(des, val);
    const obj = new CSS2DObject(div);
    const c = _caja.getCenter(new THREE.Vector3());
    obj.position.set(c.x, c.y, _caja.max.z + ALTO_MM);
    obj.center.set(0.5, 1);
    escena.add(obj);
    etiquetas.push({ lectura: l, valor: val, obj });
  }
  let escritoEn = -Infinity;
  let ancho = 0;
  let alto = 0;
  const escribir = () => {
    for (const { lectura, valor: span, obj } of etiquetas) {
      if (lectura.soloElegida) obj.visible = elegida(lectura);
      if (obj.visible) span.textContent = textoLectura(lectura, valor);
    }
  };
  escribir();
  return {
    tick: (nowMs, camara) => {
      if (!etiquetas.length) return;
      const w = contenedor.clientWidth;
      const h = contenedor.clientHeight;
      if (w !== ancho || h !== alto) {
        ancho = w;
        alto = h;
        render.setSize(w, h);
      }
      if (nowMs - escritoEn >= CADA_MS) {
        escritoEn = nowMs;
        escribir();
      }
      render.render(escena, camara);
    },
    quitar: () => {
      escena.clear();
      dom.remove();
    },
  };
}
