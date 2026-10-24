import { useEffect, useRef } from "react";
import * as THREE from "three";
import { cajaConContexto, cajaDe, destinoEncuadre, encuadrar } from "../../viewport/camara";
import { crearPipeline } from "../../viewport/pipeline";
import { crearVueloCamara, poseEn } from "../../viewport/vuelo";
import { colorDelTema, liberarRecorrido, tuboDeRecorrido } from "../../tablero/recorrido3d";
import { suave } from "../movimiento";

/* El visor de ejemplo del muestrario: un tablero de cajas con el pipeline REAL del visor
   (contorno de selección incluido) y el vuelo de `viewport/vuelo.ts`. Clic en un ítem → la
   cámara vuela a sus piezas y las contornea; el deslizador «Puerta» la abre y un conductor
   elegido se dibuja con el mismo tubo del visor real (`tablero/recorrido3d.ts`). Para las
   capturas, `?vuelo=0.4&a=canaleta-h` congela el vuelo en esa fracción del tiempo. */

export interface Demo {
  ir: (piezas: readonly string[], puntos?: readonly (readonly number[])[]) => void;
  puerta: (grados: number) => void;
  recorrido: (tramos: number[][][] | null) => void;
}

const MATERIAL = {
  chapa: new THREE.MeshStandardMaterial({ color: 0xc9ced6, metalness: 0.1, roughness: 0.55 }),
  placa: new THREE.MeshStandardMaterial({ color: 0xa8aeb8, metalness: 0.3, roughness: 0.45 }),
  aparato: new THREE.MeshStandardMaterial({ color: 0x3a3f47, metalness: 0.05, roughness: 0.6 }),
  canaleta: new THREE.MeshStandardMaterial({ color: 0x6d737c, metalness: 0.05, roughness: 0.7 }),
  seta: new THREE.MeshStandardMaterial({ color: 0xc8302c, metalness: 0.05, roughness: 0.5 }),
};

function caja(id: string, mat: THREE.Material, dims: [number, number, number], pos: [number, number, number]): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.BoxGeometry(...dims), mat);
  m.position.set(...pos);
  m.userData.featureId = id;
  m.castShadow = true;
  return m;
}

export default function VueloDemo({ alListo, puntosIniciales }: {
  alListo: (d: Demo) => void;
  /** Lo que el fotograma congelado (`?vuelo=`) también encuadra: el recorrido de `?conductor=`. */
  puntosIniciales?: readonly (readonly number[])[];
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const seleccion: string[] = [];
    const pipe = crearPipeline(mountRef.current!, () => seleccion);
    const { group, meshes, camera, controls } = pipe;
    const agregar = (m: THREE.Mesh, padre: THREE.Object3D = group) => { padre.add(m); meshes.set(m.userData.featureId, m); };
    // gabinete 500 × 200 × 600 (x, y, z): fondo, laterales, techo y piso; la puerta en −Y
    agregar(caja("fondo", MATERIAL.chapa, [500, 4, 600], [0, 100, 300]));
    agregar(caja("lateral-izq", MATERIAL.chapa, [4, 200, 600], [-250, 0, 300]));
    agregar(caja("lateral-der", MATERIAL.chapa, [4, 200, 600], [250, 0, 300]));
    agregar(caja("techo", MATERIAL.chapa, [500, 200, 4], [0, 0, 600]));
    agregar(caja("piso", MATERIAL.chapa, [500, 200, 4], [0, 0, 0]));
    agregar(caja("placa", MATERIAL.placa, [440, 3, 540], [0, 90, 300]));
    agregar(caja("canaleta-h", MATERIAL.canaleta, [400, 60, 40], [0, 58, 520]));
    agregar(caja("canaleta-b", MATERIAL.canaleta, [400, 60, 40], [0, 58, 120]));
    for (let i = 0; i < 6; i++) agregar(caja(`aparato-${i}`, MATERIAL.aparato, [45, 70, 85], [-150 + i * 60, 52, 410]));
    agregar(caja("variador", MATERIAL.aparato, [120, 90, 200], [-120, 42, 250]));
    const prensa = new THREE.Mesh(new THREE.CylinderGeometry(14, 14, 24, 32), MATERIAL.aparato);
    prensa.position.set(262, -30, 70); // en el lateral derecho, abajo
    prensa.rotation.z = Math.PI / 2;
    prensa.userData.featureId = "prensaestopas";
    agregar(prensa);
    const bisagra = new THREE.Group(); // la puerta gira sobre el canto izquierdo del frente
    bisagra.position.set(-250, -102, 0);
    group.add(bisagra);
    agregar(caja("puerta", MATERIAL.chapa, [500, 4, 600], [250, 0, 300]), bisagra);
    const seta = new THREE.Mesh(new THREE.CylinderGeometry(20, 20, 18, 32), MATERIAL.seta);
    seta.position.set(380, -10, 470);
    seta.userData.featureId = "seta";
    agregar(seta, bisagra);
    group.updateMatrixWorld(true);
    // el tablero solo: el encuadre inicial y el contexto del vuelo (las capturas de antes no cambian)
    const cajaTablero = new THREE.Box3().setFromObject(group);
    // la estructura por la que van los cables de campo (F4b): pata, larguero, tambor que gira,
    // el motor y el sensor del tambor (mm, a la derecha del tablero)
    agregar(caja("pata", MATERIAL.canaleta, [60, 60, 900], [700, 0, 450]));
    agregar(caja("larguero", MATERIAL.canaleta, [2000, 50, 100], [1700, 0, 950]));
    const tambor = new THREE.Mesh(new THREE.CylinderGeometry(60, 60, 400, 48), MATERIAL.placa);
    tambor.position.set(2750, 0, 950); // eje en Y
    tambor.userData.featureId = "tambor";
    agregar(tambor);
    agregar(caja("motor", MATERIAL.aparato, [150, 200, 150], [2750, -300, 950]));
    agregar(caja("sensor", MATERIAL.aparato, [50, 50, 50], [2875, 25, 1015]));
    group.updateMatrixWorld(true);

    const vuelo = crearVueloCamara(camera, controls);
    pipe.antesDeComponer(vuelo.tick);
    encuadrar(camera, controls, cajaTablero, [0.9, -1, 0.55]);
    pipe.arrancar();

    const destinoDe = (piezas: readonly string[], puntos: readonly (readonly number[])[] = []) => {
      let box = cajaDe(meshes, [...piezas]); // el mismo encuadre que `apolo:fit` con `animar`
      for (const [x, y, z] of puntos) box = (box ?? new THREE.Box3()).expandByPoint(new THREE.Vector3(x, y, z));
      return box ? destinoEncuadre(camera.position, controls.target, cajaConContexto(box, cajaTablero)) : null;
    };
    const ir = (piezas: readonly string[], puntos?: readonly (readonly number[])[]) => {
      seleccion.splice(0, seleccion.length, ...piezas);
      const d = destinoDe(piezas, puntos);
      if (d) vuelo.volar(d);
    };
    let tubo: THREE.Group | null = null;
    const recorrido = (tramos: number[][][] | null) => {
      if (tubo) liberarRecorrido(tubo);
      tubo = tramos ? tuboDeRecorrido(tramos, colorDelTema("--accent", "#5b8cff")) : null;
      if (tubo) pipe.scene.add(tubo);
    };
    const puerta = (grados: number) => {
      bisagra.rotation.z = -THREE.MathUtils.degToRad(grados);
      group.updateMatrixWorld(true);
    };
    const q = new URLSearchParams(window.location.search);
    if (q.has("puerta")) puerta(Number(q.get("puerta")));
    const k = q.get("vuelo"), a = q.get("a");
    if (k !== null && a) { // fotograma congelado del vuelo, para las capturas
      seleccion.splice(0, seleccion.length, ...a.split(","));
      const d = destinoDe(a.split(","), puntosIniciales);
      if (d) {
        const p = poseEn({ posicion: camera.position.clone(), objetivo: controls.target.clone() }, d, suave(Number(k)));
        camera.position.copy(p.posicion);
        controls.target.copy(p.objetivo);
        controls.update();
      }
    }
    alListo({ ir, puerta, recorrido });
    return () => {
      vuelo.dispose();
      pipe.detener();
      pipe.dispose();
    };
  }, []);
  return <div ref={mountRef} className="mu-visor" aria-label="Visor de ejemplo" />;
}
