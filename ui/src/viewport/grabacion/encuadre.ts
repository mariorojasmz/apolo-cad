import * as THREE from "three";

/* Encuadre del giro (plan video-realista, F2): la cámara del visor viene con el aspecto de la
   ventana y lejos (el «encuadrar» del visor deja aire de sobra). Para el video se acerca lo justo
   para que la caja de la máquina entre en el cuadro de 16:9 durante TODO el giro, desde la misma
   dirección de mirada (altura relativa incluida). Una búsqueda binaria sobre la distancia,
   probando la proyección de las 8 esquinas en varios ángulos del giro. */

/** Fracción del cuadro que puede ocupar la máquina (deja un margen alrededor). */
export const MARGEN = 0.86;
/** Ángulos del giro que se prueban (cada 10° en una vuelta). */
const ANGULOS = 36;

const _v = new THREE.Vector3();
const _p = new THREE.Vector3();

function esquinas(caja: THREE.Box3): THREE.Vector3[] {
  const { min, max } = caja;
  const out: THREE.Vector3[] = [];
  for (const x of [min.x, max.x]) for (const y of [min.y, max.y]) for (const z of [min.z, max.z]) {
    out.push(new THREE.Vector3(x, y, z));
  }
  return out;
}

/** Posición de cámara que encuadra `caja` mirando a su centro desde la dirección `desde`→centro
   actual, para un giro de `grados` alrededor de Z. Devuelve también el nuevo objetivo. */
export function encuadreGiro(
  camara: THREE.PerspectiveCamera, objetivoActual: THREE.Vector3, caja: THREE.Box3, grados: number,
  margen = MARGEN,
): { posicion: THREE.Vector3; objetivo: THREE.Vector3 } | null {
  if (caja.isEmpty()) return null;
  const centro = caja.getCenter(new THREE.Vector3());
  const dir = camara.position.clone().sub(objetivoActual).normalize();
  if (!Number.isFinite(dir.x)) return null;
  const prueba = camara.clone();
  const puntos = esquinas(caja);
  const diag = caja.getSize(new THREE.Vector3()).length() || 1000;
  const eje = new THREE.Vector3(0, 0, 1);
  const entra = (d: number) => {
    for (let k = 0; k <= ANGULOS; k++) {
      const a = THREE.MathUtils.degToRad((grados * k) / ANGULOS);
      prueba.position.copy(centro).add(_v.copy(dir).applyAxisAngle(eje, a).multiplyScalar(d));
      prueba.lookAt(centro);
      prueba.updateMatrixWorld(true);
      for (const p of puntos) {
        _p.copy(p).applyMatrix4(prueba.matrixWorldInverse);
        if (_p.z >= -prueba.near) return false; // detrás de la cámara
        _p.applyMatrix4(prueba.projectionMatrix);
        if (Math.abs(_p.x) > margen || Math.abs(_p.y) > margen) return false;
      }
    }
    return true;
  };
  let cerca = diag * 0.05;
  let lejos = diag * 20;
  if (!entra(lejos)) return null;
  for (let i = 0; i < 40; i++) {
    const medio = (cerca + lejos) / 2;
    if (entra(medio)) lejos = medio;
    else cerca = medio;
  }
  return { posicion: centro.clone().add(dir.multiplyScalar(lejos)), objetivo: centro };
}
