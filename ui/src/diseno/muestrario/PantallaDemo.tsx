import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { encuadrar } from "../../viewport/camara";
import { crearPipeline } from "../../viewport/pipeline";
import { instalarPantallas3D } from "../../vivo/pantallas3d";
import { temaDe } from "../../vivo/pantallas";
import { useVivo } from "../../vivo/estado";
import { pantallasDe } from "../../extensiones/puntosVivo";
import type { MensajeExtension, VivoPantalla } from "../../extensiones/tipos";
import type { DispositivoVivo } from "../../vivo/protocolo";
import { movimientoReducido } from "../movimiento";
import { EXTENSION_PRUEBA } from "./extensionPrueba";
import { INICIO_DEMO } from "./datosVivo";

/* La pantalla 3D de la extensión de prueba en el muestrario (plan plc-en-el-lazo, D13): la puerta
   de un tablero GIRADO (`?giro=25` grados sobre Z, por defecto) con el panel de operador de 7″
   (marco 200,3 × 146,3 mm delante, cuerpo detrás: la forma de `panel_puerta`, también girada en su
   propio marco) y el plano con el canvas que pinta la extensión, instalado con el MISMO
   `instalarPantallas3D` del visor. Tocar «−10» o «+10» manda un `escribir`: aquí lo aplica la
   sesión de ejemplo (`useVivo`) y el chip de la barra lo ve. */

const q = () => new URLSearchParams(window.location.search);

/** El panel como lo arma `panel_puerta` en su marco: marco en +Y, cuerpo hasta −Y (fondo 35). */
function geometriaPanel(): THREE.BufferGeometry {
  const marco = new THREE.BoxGeometry(200.3, 7.4, 146.3).translate(0, 35 / 2 - 7.4 / 2, 0);
  const cuerpo = new THREE.BoxGeometry(189.6, 27.8, 135.6).translate(0, -35 / 2 + 27.8 / 2, 0);
  return mergeGeometries([marco, cuerpo])!;
}

export default function PantallaDemo() {
  const mountRef = useRef<HTMLDivElement>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  useEffect(() => {
    const pipe = crearPipeline(mountRef.current!, () => []);
    const { group, meshes, camera, controls } = pipe;
    const giro = THREE.MathUtils.degToRad(Number(q().get("giro") ?? 25));
    const tablero = new THREE.Group();
    tablero.rotation.z = giro;
    group.add(tablero);
    const chapa = new THREE.MeshStandardMaterial({ color: 0xc9ced6, metalness: 0.1, roughness: 0.55 });
    const oscuro = new THREE.MeshStandardMaterial({ color: 0x2a2e35, metalness: 0.05, roughness: 0.6 });
    const puerta = new THREE.Mesh(new THREE.BoxGeometry(500, 4, 600), chapa);
    puerta.position.set(0, -100, 300); // la puerta en −Y del tablero
    const panel = new THREE.Mesh(geometriaPanel(), oscuro);
    panel.position.set(0, -102 - 7.4 + 35 / 2, 430); // el marco apoya en la cara exterior de la chapa
    panel.rotation.z = Math.PI; // su +Y (el marco) mira hacia −Y del tablero: afuera de la puerta
    for (const [id, m] of [["puerta", puerta], ["panel-operador", panel]] as const) {
      m.userData.featureId = id;
      tablero.add(m);
      meshes.set(id, m);
    }
    group.updateMatrixWorld(true);
    const raiz = getComputedStyle(document.documentElement);
    const tema = temaDe((t) => raiz.getPropertyValue(t), getComputedStyle(document.body).fontFamily);
    const enviar = (m: MensajeExtension): boolean => {
      if (!("accion" in m) || m.accion !== "escribir") return false;
      const st = useVivo.getState();
      st.set({ lecturas: { ...st.lecturas, [`${m.dispositivo}.${m.variable}`]: Number(m.valor) } });
      setMensaje(`escribir ${String(m.variable)} = ${String(m.valor)} en ${String(m.dispositivo)}`);
      return true;
    };
    const vivo = (dispositivo: DispositivoVivo, ancho: number, alto: number): VivoPantalla => ({
      dispositivo, inicio: INICIO_DEMO, ancho, alto, tema, movimientoReducido: movimientoReducido(),
      t: useVivo.getState().t,
      valor: (s) => useVivo.getState().lecturas[s],
      texto: (s) => useVivo.getState().textos[s],
      enviar,
    });
    const pantallas = instalarPantallas3D({
      contenedor: mountRef.current!, canvas: pipe.renderer.domElement, camara: () => camera, meshes, grupo: group,
      dispositivos: INICIO_DEMO.dispositivos, pantallas: pantallasDe([EXTENSION_PRUEBA]), vivo,
    });
    pipe.antesDeComponer((ahora) => pantallas.tick(ahora));
    const caja = new THREE.Box3().setFromObject(panel).expandByScalar(90);
    encuadrar(camera, controls, caja, [Math.sin(giro) + 0.3, -Math.cos(giro), 0.25]);
    pipe.arrancar();
    return () => {
      pantallas.quitar();
      pipe.detener();
      pipe.dispose();
    };
  }, []);
  return (
    <>
      <div ref={mountRef} className="mu-visor mu-pantalla" aria-label="Panel de operador de ejemplo" />
      <p className="mu-rotulo mu-detalle" aria-live="polite">
        {mensaje ? `Último mensaje a la sesión: ${mensaje}` : "Toca −10 o +10 en la pantalla del panel."}
      </p>
    </>
  );
}
