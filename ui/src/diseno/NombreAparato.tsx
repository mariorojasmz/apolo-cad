import type { ReactNode } from "react";
import { designacionSecundaria, nombrePrincipal, type ConNombre } from "./nombres";
import "./diseno.css";

/* El nombre de un aparato en una fila (plan nombres-por-funcion D9): el rótulo en `--fw-medio` y
   detrás, en `--fs-nota` y tinta secundaria, la designación y un detalle opcional («-K2 · Relé de
   seguridad 2 canales»). La designación nunca se corta ni queda sola en su línea: va pegada a la
   última palabra del nombre (F5b); el detalle sí se parte, en angosto. `cola` (la ⓘ de «Mandos»)
   va pegada a la designación. Va dentro de un contenedor `.cabeza-aparato`. */

export default function NombreAparato({ a, detalle, cola }: { a: ConNombre; detalle?: string | null; cola?: ReactNode }) {
  const principal = nombrePrincipal(a);
  const designacion = designacionSecundaria(a);
  const extra = detalle && detalle !== principal ? detalle : null;
  return (
    <>
      <span className="rotulo-aparato">{principal}</span>
      {(designacion || extra) ? (
        <span className="designacion-aparato">
          {designacion && <span className="designacion-codigo">{designacion}{!extra && cola}</span>}
          {designacion && extra && " · "}
          {extra}
          {extra && cola}
        </span>
      ) : cola}
    </>
  );
}
