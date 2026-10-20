import * as THREE from "three";
import { FullScreenQuad, Pass } from "three/examples/jsm/postprocessing/Pass.js";
import { CopyShader } from "three/examples/jsm/shaders/CopyShader.js";

/* Antialias ACUMULADO de la grabación (plan video-realista, D3): el mismo instante se dibuja N
   veces con la cámara corrida una fracción de píxel (secuencia de Halton 2,3) y se promedia en un
   render target HalfFloat. Es lo que el TAA alcanza con la cámara quieta, pero sin depender de que
   lo esté: con el reloj virtual cada cuadro espera sus N muestras.

   Reemplaza al `RenderPass` mientras se graba: `acumular` dibuja por tandas (el modo grabación
   suelta el hilo entre tandas para no colgar la GPU) y `render`, ya en el composer, copia el
   promedio al buffer de lectura como haría el RenderPass (sin swap), así GTAO, OutputPass y el
   resto siguen igual. El mapa de sombras se rehace sólo en la primera muestra del cuadro. */

/** Corrimiento de la muestra `i` en píxeles, en (−0,5, 0,5): Halton base 2 y 3, sin la 0. */
export function corrimiento(i: number): [number, number] {
  const halton = (k: number, base: number) => {
    let f = 1;
    let r = 0;
    for (let n = k; n > 0; n = Math.floor(n / base)) {
      f /= base;
      r += f * (n % base);
    }
    return r;
  };
  return [halton(i + 1, 2) - 0.5, halton(i + 1, 3) - 0.5];
}

export class PaseAcumulado extends Pass {
  muestras = 16;
  private hechas = 0;
  private readonly acumulado: THREE.WebGLRenderTarget;
  private readonly muestra: THREE.WebGLRenderTarget;
  private readonly sumar: THREE.ShaderMaterial;
  private readonly copiar: THREE.ShaderMaterial;
  private readonly quad: FullScreenQuad;
  private readonly color = new THREE.Color();

  constructor(private readonly scene: THREE.Scene, private readonly camera: THREE.PerspectiveCamera) {
    super();
    this.needsSwap = false; // como el RenderPass: deja la escena en el buffer de lectura
    const rt = () => new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType });
    this.acumulado = rt();
    this.muestra = rt();
    const material = (aditivo: boolean) => new THREE.ShaderMaterial({
      uniforms: THREE.UniformsUtils.clone(CopyShader.uniforms),
      vertexShader: CopyShader.vertexShader,
      fragmentShader: CopyShader.fragmentShader,
      depthTest: false,
      depthWrite: false,
      transparent: aditivo,
      premultipliedAlpha: aditivo,
      blending: aditivo ? THREE.AdditiveBlending : THREE.NoBlending, // aditivo = ONE, ONE
    });
    this.sumar = material(true);
    this.copiar = material(false);
    this.quad = new FullScreenQuad(this.sumar);
  }

  get listo(): boolean {
    return this.hechas >= this.muestras;
  }

  /** Empieza un cuadro nuevo. */
  reiniciar(): void {
    this.hechas = 0;
  }

  override setSize(ancho: number, alto: number): void {
    this.acumulado.setSize(ancho, alto);
    this.muestra.setSize(ancho, alto);
  }

  /** Dibuja hasta `tanda` muestras más del instante actual; devuelve cuántas van. */
  acumular(renderer: THREE.WebGLRenderer, tanda: number): number {
    const { width: w, height: h } = this.acumulado;
    const previo = renderer.getRenderTarget();
    const autoClear = renderer.autoClear;
    const alfa = renderer.getClearAlpha();
    renderer.getClearColor(this.color);
    const sombras = renderer.shadowMap.autoUpdate;
    renderer.autoClear = false;
    this.sumar.uniforms.opacity.value = 1 / this.muestras;
    this.sumar.uniforms.tDiffuse.value = this.muestra.texture;
    this.quad.material = this.sumar;
    try {
      for (let k = 0; k < tanda && !this.listo; k++) {
        renderer.shadowMap.autoUpdate = this.hechas === 0; // una vez por cuadro
        const [dx, dy] = corrimiento(this.hechas);
        this.camera.setViewOffset(w, h, dx, dy, w, h);
        renderer.setRenderTarget(this.muestra);
        renderer.setClearColor(this.color, alfa);
        renderer.clear();
        renderer.render(this.scene, this.camera);
        renderer.setRenderTarget(this.acumulado);
        if (this.hechas === 0) {
          renderer.setClearColor(0x000000, 0);
          renderer.clear();
        }
        this.quad.render(renderer);
        this.hechas++;
      }
    } finally {
      this.camera.clearViewOffset();
      renderer.shadowMap.autoUpdate = sombras;
      renderer.autoClear = autoClear;
      renderer.setClearColor(this.color, alfa);
      renderer.setRenderTarget(previo);
    }
    return this.hechas;
  }

  override render(renderer: THREE.WebGLRenderer, _escritura: THREE.WebGLRenderTarget,
    lectura: THREE.WebGLRenderTarget): void {
    this.copiar.uniforms.opacity.value = 1;
    this.copiar.uniforms.tDiffuse.value = this.acumulado.texture;
    this.quad.material = this.copiar;
    renderer.setRenderTarget(this.renderToScreen ? null : lectura);
    this.quad.render(renderer);
  }

  override dispose(): void {
    this.acumulado.dispose();
    this.muestra.dispose();
    this.sumar.dispose();
    this.copiar.dispose();
    // `quad` no se libera: su geometría es la compartida de three (la usan los otros pases)
  }
}
