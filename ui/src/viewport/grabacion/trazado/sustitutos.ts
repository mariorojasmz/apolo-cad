import * as THREE from "three";

/* Mallas SUSTITUTAS para el trazador (plan video-realista, F4). `three-gpu-pathtracer` 0.0.23
   arma la escena con UNA malla = UN material y sin instancias (lo medido en F4):

   - `InstancedMesh` (los eslabones de las cadenas, `marcha/cadena.ts`): contaría una sola pieza
     en el origen. Se expande en una malla suelta por instancia, que comparte geometría y material.
   - Una malla con un ARREGLO de materiales (las zonas de la seta, `viewport/zonas.ts`): la librería
     asigna el material por MALLA, no por grupo, y corre los índices de todas las que vienen
     después (la banda salía gris y el piso rojo). Se parte en una malla por grupo, con su pedazo
     de geometría (copiado una vez y reusado) y el material de su zona.

   Las sustitutas son PERSISTENTES: de un cuadro al siguiente sólo cambia su matriz, así que el
   trazador reajusta el BVH (refit) en vez de rearmarlo. Las originales se ocultan mientras dura
   el trazado (el llamador lo hace con lo que devuelve `sincronizar`). */

/** El pedazo `[inicio, inicio + cuenta)` de vértices de una geometría SIN índice. */
export function pedazoDeGeometria(geo: THREE.BufferGeometry, inicio: number, cuenta: number): THREE.BufferGeometry {
  const fuente = geo.index ? geo.toNonIndexed() : geo;
  const out = new THREE.BufferGeometry();
  for (const [nombre, attr] of Object.entries(fuente.attributes)) {
    const a = attr as THREE.BufferAttribute;
    const n = a.itemSize;
    const fin = Math.min(inicio + cuenta, a.count);
    const datos = (a.array as Float32Array).slice(inicio * n, fin * n);
    out.setAttribute(nombre, new THREE.BufferAttribute(datos, n, a.normalized));
  }
  if (fuente !== geo) fuente.dispose();
  return out;
}

const esInstancias = (o: THREE.Object3D): o is THREE.InstancedMesh => (o as THREE.InstancedMesh).isInstancedMesh === true;
const conZonas = (o: THREE.Object3D): o is THREE.Mesh =>
  (o as THREE.Mesh).isMesh === true && Array.isArray((o as THREE.Mesh).material)
  && (o as THREE.Mesh).geometry.groups.length > 0;

export class Sustitutos {
  readonly grupo = new THREE.Group();
  /** Por malla original (uuid): sus sustitutas. */
  private readonly copias = new Map<string, THREE.Mesh[]>();
  /** Pedazos de geometría por (uuid de la geometría, versión de la posición). */
  private readonly pedazos = new Map<string, THREE.BufferGeometry[]>();
  private readonly m = new THREE.Matrix4();

  constructor() {
    this.grupo.name = "sustitutos-trazado";
    this.grupo.matrixAutoUpdate = false;
  }

  private lista(original: THREE.Object3D): THREE.Mesh[] {
    let l = this.copias.get(original.uuid);
    if (!l) {
      l = [];
      this.copias.set(original.uuid, l);
    }
    return l;
  }

  private nueva(lista: THREE.Mesh[], geo: THREE.BufferGeometry, mat: THREE.Material): THREE.Mesh {
    const c = new THREE.Mesh(geo, mat);
    c.matrixAutoUpdate = false;
    lista.push(c);
    this.grupo.add(c);
    return c;
  }

  private piezasDe(geo: THREE.BufferGeometry): THREE.BufferGeometry[] {
    const clave = `${geo.uuid}|${(geo.getAttribute("position") as THREE.BufferAttribute).version}|${geo.groups.length}`;
    let p = this.pedazos.get(clave);
    if (!p) {
      p = geo.groups.map((g) => pedazoDeGeometria(geo, g.start, g.count));
      this.pedazos.set(clave, p);
    }
    return p;
  }

  /** Pone las sustitutas de lo visible de `raiz` en su pose de ahora y devuelve las ORIGINALES
     que reemplazan (el llamador las oculta mientras traza). Las de lo que ya no está se quitan. */
  sincronizar(raiz: THREE.Object3D): THREE.Mesh[] {
    const originales: THREE.Mesh[] = [];
    raiz.updateMatrixWorld(true);
    raiz.traverseVisible((o) => {
      if (esInstancias(o) || conZonas(o)) originales.push(o as THREE.Mesh);
    });
    const vivos = new Set(originales.map((o) => o.uuid));
    for (const [id, lista] of this.copias) {
      if (vivos.has(id)) continue;
      for (const c of lista) this.grupo.remove(c);
      this.copias.delete(id);
    }
    for (const o of originales) {
      const lista = this.lista(o);
      if (esInstancias(o)) {
        const mat = Array.isArray(o.material) ? o.material[0] : o.material;
        while (lista.length < o.count) this.nueva(lista, o.geometry, mat);
        lista.forEach((c, i) => {
          c.visible = i < o.count;
          if (!c.visible) return;
          o.getMatrixAt(i, this.m);
          c.matrix.multiplyMatrices(o.matrixWorld, this.m);
          c.material = mat; // la marcha puede cambiarlo
        });
      } else {
        const mats = o.material as THREE.Material[];
        const piezas = this.piezasDe(o.geometry);
        if (lista.length !== piezas.length || lista.some((c, i) => c.geometry !== piezas[i])) {
          for (const c of lista) this.grupo.remove(c);
          lista.length = 0;
          piezas.forEach((g) => this.nueva(lista, g, mats[0]));
        }
        lista.forEach((c, i) => {
          c.matrix.copy(o.matrixWorld);
          c.material = mats[o.geometry.groups[i].materialIndex ?? 0] ?? mats[0];
          c.visible = true;
        });
      }
    }
    return originales;
  }

  /** Cuántas sustitutas hay a la vista (para las pruebas). */
  get visibles(): number {
    return this.grupo.children.filter((c) => c.visible).length;
  }

  dispose(): void {
    for (const p of this.pedazos.values()) for (const g of p) g.dispose();
    this.pedazos.clear();
    this.copias.clear();
    this.grupo.clear();
  }
}
