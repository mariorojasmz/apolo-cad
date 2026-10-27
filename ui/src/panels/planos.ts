import { useEffect, useState } from "react";
import { detalleDeError } from "../api";
import { encolar, esperarJob, type ProgresoJob } from "../state/jobs";

/* El diálogo «Planos» sin congelar Apolo (plan visor-para-evaluar D10–D12): la lámina de conjunto
   llega de `GET /api/drawing/lamina` (lista al instante si ya se calculó, o como job con su
   progreso, mostrando mientras tanto la última lámina o una vista sombreada) y el juego de planos
   de taller sale como job con su descarga al terminar. Lo puro (`fraseProgreso`) lo prueba vitest. */

/** Cómo se dice qué está calculando el HLR (la `fase` del progreso del job). */
const FASES: Record<string, string> = {
  alzado: "el alzado", planta: "la planta", lateral: "el perfil", iso: "la isométrica", corte: "el corte",
};

/** «Calculando las vistas · 1 de 4 listas» (corren a la vez, una por núcleo), «Calculando el
   corte», «Armando la lámina», «Lámina 12 de 40». */
export function fraseProgreso(p: ProgresoJob | undefined, encolado: boolean): string {
  if (encolado) return "En espera: otro plano se está armando";
  if (!p) return "Empezando…";
  if (p.fase === "laminas") return `Lámina ${p.hechas + 1} de ${p.total}`;
  if (p.fase === "listo" || p.hechas >= p.total) return "Armando la lámina";
  if (p.total === 1) return `Calculando ${FASES[p.fase] ?? "la vista"}`;
  return `Calculando las vistas · ${p.hechas} de ${p.total} listas`;
}

/** La fracción hecha (0…1) de un progreso, o null sin él. */
export function fraccion(p: ProgresoJob | undefined): number | null {
  return p && p.total > 0 ? Math.min(1, p.hechas / p.total) : null;
}

/** «unos 4 min», «unos 40 s». */
export function textoEstimado(s: number | undefined): string {
  if (!s) return "";
  return s >= 90 ? `unos ${Math.round(s / 60)} min` : `unos ${Math.max(5, Math.round(s / 5) * 5)} s`;
}

export interface EstadoPlano {
  /** La lámina exacta del modelo de hoy (url del SVG), cuando está. */
  svg: string | null;
  /** Mientras se calcula: la lámina de antes de los últimos cambios, o null. */
  previa: string | null;
  calculando: boolean;
  encolado: boolean;
  progreso?: ProgresoJob;
  estimadoS?: number;
  error: string | null;
}

const INICIAL: EstadoPlano = { svg: null, previa: null, calculando: false, encolado: false, error: null };

interface RespuestaLamina {
  lista: boolean;
  svg?: string;
  job_id?: string;
  previa?: string;
  estimado_s?: number;
}

/** La lámina de conjunto con esas opciones (`query`); se vuelve a pedir cuando cambian. */
export function usePlano(query: string | null): EstadoPlano {
  const [e, setE] = useState<EstadoPlano>(INICIAL);
  useEffect(() => {
    if (query === null) return;
    let vivo = true;
    setE((prev) => ({ ...INICIAL, previa: prev.svg ?? prev.previa }));
    void (async () => {
      try {
        const r = await fetch(`/api/drawing/lamina?${query}`);
        if (!r.ok) throw new Error((await detalleDeError(r)) ?? r.statusText);
        const d = (await r.json()) as RespuestaLamina;
        if (!vivo) return;
        if (d.lista && d.svg) {
          setE({ ...INICIAL, svg: d.svg });
          return;
        }
        setE((prev) => ({ ...prev, calculando: true, encolado: true, previa: d.previa ?? null, estimadoS: d.estimado_s }));
        const res = await esperarJob(d.job_id!, (j) => {
          if (vivo) setE((prev) => ({ ...prev, encolado: j.estado === "encolado", progreso: j.progreso }));
        }, () => !vivo);
        if (vivo) setE({ ...INICIAL, svg: String(res.svg) });
      } catch (err) {
        if (!vivo || (err instanceof DOMException && err.name === "AbortError")) return;
        setE((prev) => ({ ...prev, calculando: false, error: err instanceof Error ? err.message : String(err) }));
      }
    })();
    return () => {
      vivo = false;
    };
  }, [query]);
  return e;
}

export interface EstadoJuego {
  formato: "pdf" | "dwg" | null;
  encolado: boolean;
  progreso?: ProgresoJob;
  error: string | null;
}

/** Pide el juego de planos de taller como job (PDF o DWG) y lo baja al terminar. */
export async function pedirJuego(
  formato: "pdf" | "dwg", sheet: string, alCambiar: (e: EstadoJuego) => void,
): Promise<void> {
  const ruta = formato === "pdf" ? "/api/drawingset.pdf" : "/api/drawingset.dwg";
  alCambiar({ formato, encolado: true, error: null });
  try {
    const id = await encolar(`${ruta}?sheet=${sheet}&async=true&origen=visor`);
    const res = await esperarJob(id, (j) => alCambiar({ formato, encolado: j.estado === "encolado", progreso: j.progreso, error: null }));
    const a = document.createElement("a");
    a.href = String(res.archivo);
    a.download = String(res.nombre ?? "");
    document.body.appendChild(a);
    a.click();
    a.remove();
    alCambiar({ formato: null, encolado: false, error: null });
  } catch (err) {
    alCambiar({ formato: null, encolado: false, error: err instanceof Error ? err.message : String(err) });
  }
}

/** ¿Este servidor puede escribir DWG? (`GET /api/health` → `dwg.disponible`). */
export async function dwgDisponible(): Promise<boolean> {
  try {
    const h = (await fetch("/api/health").then((r) => r.json())) as { dwg?: { disponible?: boolean } };
    return h.dwg?.disponible === true;
  } catch {
    return false;
  }
}
