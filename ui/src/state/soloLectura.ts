import type { SceneOut, SoloLecturaOut } from "../types";

/* Proyecto en SÓLO LECTURA (plan núcleo-abierto-extensiones-privadas, D4): usa una extensión que
   esta instalación no tiene. El servidor lo marca en `document.solo_lectura` y responde 409 a
   toda edición; la UI avisa y no ofrece editar (ribbon, Propiedades, deshacer/rehacer, gizmo y
   arrastre en el 3D). Lógica pura, sin la store: se prueba sola. */

/** El marcador del documento si es válido; null = editable. Devuelve el MISMO objeto que trae la
   escena: sirve de selector de zustand sin re-render en cada llamada. */
export function soloLecturaDe(scene: Pick<SceneOut, "document"> | null | undefined): SoloLecturaOut | null {
  const s: unknown = scene?.document?.solo_lectura;
  if (typeof s !== "object" || s === null) return null;
  const { extensiones } = s as Partial<SoloLecturaOut>;
  return Array.isArray(extensiones) ? (s as SoloLecturaOut) : null;
}

/** «a», «a» y «b», «a», «b» y «c». */
function enumerar(nombres: string[]): string {
  const n = nombres.map((x) => `«${x}»`);
  return n.length > 1 ? `${n.slice(0, -1).join(", ")} y ${n[n.length - 1]}` : n[0];
}

/** El aviso para la persona: qué extensión falta y qué puedes hacer. Nombra las extensiones que
   manda el servidor; sin nombres, usa su aviso. */
export function textoSoloLectura(s: SoloLecturaOut): string {
  const nombres = s.extensiones.filter((x) => typeof x === "string" && x.trim() !== "");
  if (nombres.length === 0) {
    return typeof s.aviso === "string" && s.aviso.trim()
      ? s.aviso
      : "Este proyecto usa extensiones que no están instaladas: puedes verlo, no editarlo.";
  }
  return nombres.length === 1
    ? `Este proyecto usa la extensión ${enumerar(nombres)}, que no está instalada: puedes verlo, no editarlo.`
    : `Este proyecto usa las extensiones ${enumerar(nombres)}, que no están instaladas: puedes verlo, no editarlo.`;
}
