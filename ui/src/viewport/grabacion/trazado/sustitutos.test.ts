import * as THREE from "three";
import { DenoiseMaterial } from "three-gpu-pathtracer";
import { describe, expect, it } from "vitest";
import { alfaPiso } from "./escenaTrazable";
import { pedazoDeGeometria, Sustitutos } from "./sustitutos";
import { adaptarDenoise } from "./trazador";

/* Lo que el trazador de three-gpu-pathtracer 0.0.23 no sabe dibujar y su reemplazo (video-realista
   F4): instancias y arreglos de materiales como mallas sueltas de UN material, el piso del
   visor y el denoiser con color premultiplicado. */

const caja = () => {
  const g = new THREE.BoxGeometry(1, 1, 1).toNonIndexed();
  g.clearGroups(); // como las del visor (`meshes.ts::geometryFrom`): sin grupos salvo las zonas
  return g;
};

describe("mallas sustitutas", () => {
  it("una cadena instanciada sale como una malla por instancia, en su pose, y se reusa", () => {
    const raiz = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial();
    const im = new THREE.InstancedMesh(caja(), mat, 5);
    im.count = 3;
    for (let i = 0; i < 5; i++) im.setMatrixAt(i, new THREE.Matrix4().makeTranslation(i * 10, 0, 0));
    im.position.set(0, 0, 100);
    raiz.add(im);
    const s = new Sustitutos();
    expect(s.sincronizar(raiz)).toEqual([im]);
    expect(s.visibles).toBe(3);
    const copias = s.grupo.children as THREE.Mesh[];
    const p = new THREE.Vector3().setFromMatrixPosition(copias[2].matrix);
    expect(p.toArray()).toEqual([20, 0, 100]);
    expect(copias.every((c) => c.material === mat && c.geometry === im.geometry)).toBe(true);
    // la marcha la mueve: las mismas copias (refit, no rebuild), en la pose nueva
    const uuids = copias.map((c) => c.uuid);
    im.position.z = 200;
    s.sincronizar(raiz);
    expect((s.grupo.children as THREE.Mesh[]).map((c) => c.uuid)).toEqual(uuids);
    expect(new THREE.Vector3().setFromMatrixPosition(copias[0].matrix).z).toBe(200);
  });

  it("una pieza con zonas se parte en una malla por grupo con el material de su zona", () => {
    const geo = caja(); // 36 vértices
    geo.addGroup(0, 24, 1);
    geo.addGroup(24, 12, 0);
    const rojo = new THREE.MeshStandardMaterial({ color: 0xff0000 });
    const amarillo = new THREE.MeshStandardMaterial({ color: 0xffff00 });
    const seta = new THREE.Mesh(geo, [amarillo, rojo]);
    seta.position.set(5, 6, 7);
    const sola = new THREE.Mesh(caja(), amarillo); // un solo material: no se toca
    const raiz = new THREE.Group().add(seta, sola);
    const s = new Sustitutos();
    expect(s.sincronizar(raiz)).toEqual([seta]);
    const [a, b] = s.grupo.children as THREE.Mesh[];
    expect([a.material, b.material]).toEqual([rojo, amarillo]);
    expect([a.geometry.getAttribute("position").count, b.geometry.getAttribute("position").count]).toEqual([24, 12]);
    expect(Array.from(a.geometry.getAttribute("position").array.slice(0, 3)))
      .toEqual(Array.from(geo.getAttribute("position").array.slice(0, 3)));
    expect(new THREE.Vector3().setFromMatrixPosition(a.matrix).toArray()).toEqual([5, 6, 7]);
    const geos = [a.geometry, b.geometry];
    s.sincronizar(raiz); // los pedazos se copian una vez
    expect((s.grupo.children as THREE.Mesh[]).map((c) => c.geometry)).toEqual(geos);
  });

  it("lo que deja de verse se quita", () => {
    const raiz = new THREE.Group();
    const im = new THREE.InstancedMesh(caja(), new THREE.MeshStandardMaterial(), 2);
    raiz.add(im);
    const s = new Sustitutos();
    s.sincronizar(raiz);
    im.visible = false;
    expect(s.sincronizar(raiz)).toEqual([]);
    expect(s.grupo.children).toHaveLength(0);
  });

  it("el pedazo de una geometría con índice sale de su versión sin índice", () => {
    const g = new THREE.BoxGeometry(1, 1, 1); // con índice
    expect(pedazoDeGeometria(g, 6, 6).getAttribute("position").count).toBe(6);
  });
});

describe("piso y denoiser del trazado", () => {
  it("el piso cae como el disco del visor: 0,9 al centro, nada en el borde", () => {
    expect(alfaPiso(0)).toBeCloseTo(0.9);
    expect(alfaPiso(0.15)).toBeCloseTo(0.9);
    expect(alfaPiso(0.575)).toBeCloseTo(0.45);
    expect(alfaPiso(1)).toBe(0);
    expect(alfaPiso(1.4)).toBe(0);
  });

  it("el denoiser recibe color premultiplicado y lo devuelve premultiplicado", () => {
    const m = new DenoiseMaterial();
    adaptarDenoise(m);
    expect(m.fragmentShader).not.toContain("centrPx.rgb *= centrPx.a");
    expect(m.fragmentShader).not.toContain("#include <premultiplied_alpha_fragment>");
    expect(m.fragmentShader).toContain("gl_FragColor.rgb /= max( gl_FragColor.a, 1e-4 );");
    expect(m.fragmentShader).toContain("#include <tonemapping_fragment>"); // el ACES del visor
    expect(() => adaptarDenoise(m)).toThrow(/cambió/); // otra versión de la librería: avisa
  });
});
