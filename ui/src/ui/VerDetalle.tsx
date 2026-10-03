import type { ReactNode } from "react";

/* Ver detalle (N3 de ui/CLAUDE.md § Texto y ayuda): contesta «¿cómo es por dentro?», a
   pedido y plegado en el lugar. `<details>` nativo: se abre con teclado y lector de
   pantalla sin estado propio, y nace cerrado. Lo técnico (nombres de parámetros, ids)
   vive aquí, no a la vista. */

interface Props {
  /** Lo que se lee plegado: «Detalle técnico». */
  resumen: string;
  children: ReactNode;
}

export default function VerDetalle({ resumen, children }: Props) {
  return (
    <details className="ver-detalle">
      <summary>{resumen}</summary>
      <div className="ver-detalle-cuerpo">{children}</div>
    </details>
  );
}
