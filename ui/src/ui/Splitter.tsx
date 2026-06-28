import { useCallback, useRef, useState } from "react";

/* Divisor arrastrable sin librería (pointer events). El tamaño resultante se aplica
   como CSS var sobre el contenedor padre (p. ej. --props-h, --bottomdock-h) y el grid
   lo lee. Persiste opcionalmente en localStorage. Reutilizable en right-dock y bottom-dock. */

type Axis = "x" | "y";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

export function useSplitter(opts: {
  initial: number;
  min: number;
  max: number;
  axis: Axis;
  invert?: boolean; // true cuando arrastrar hacia el lado "negativo" agranda (p. ej. dock inferior)
  storageKey?: string;
}) {
  const { initial, min, max, axis, invert, storageKey } = opts;
  const [size, setSize] = useState(() => {
    if (storageKey) {
      const v = Number(localStorage.getItem(storageKey));
      if (v) return clamp(v, min, max);
    }
    return initial;
  });
  const start = useRef(0);
  const base = useRef(0);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
      start.current = axis === "y" ? e.clientY : e.clientX;
      base.current = size;
      const move = (ev: PointerEvent) => {
        const cur = axis === "y" ? ev.clientY : ev.clientX;
        let d = cur - start.current;
        if (invert) d = -d;
        const next = clamp(base.current + d, min, max);
        setSize(next);
        if (storageKey) localStorage.setItem(storageKey, String(next));
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    [size, axis, min, max, invert, storageKey],
  );

  return { size, onPointerDown, setSize };
}

export function SplitHandle({
  axis,
  onPointerDown,
}: {
  axis: Axis;
  onPointerDown: (e: React.PointerEvent) => void;
}) {
  return <div className={`split-handle split-${axis}`} onPointerDown={onPointerDown} role="separator" />;
}
