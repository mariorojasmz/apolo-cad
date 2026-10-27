import { designacionSecundaria, nombrePrincipal, type ConNombre } from "./nombres";
import "./diseno.css";

/* El nombre de un aparato en una fila (plan nombres-por-funcion D9): el rótulo en `--fw-medio` y
   detrás, en `--fs-nota` y tinta secundaria, la designación y un detalle opcional («-K2 · Relé de
   seguridad 2 canales»). La designación nunca se corta; el detalle sí, en angosto. Va dentro de un
   contenedor `.cabeza-aparato` (la fila de «Mandos», la de «Tablero»), que lo deja bajar entero. */

export default function NombreAparato({ a, detalle }: { a: ConNombre; detalle?: string | null }) {
  const principal = nombrePrincipal(a);
  const designacion = designacionSecundaria(a);
  const extra = detalle && detalle !== principal ? detalle : null;
  return (
    <>
      <span className="rotulo-aparato">{principal}</span>
      {(designacion || extra) && (
        <span className="designacion-aparato">
          {designacion && <span className="designacion-codigo">{designacion}</span>}
          {designacion && extra && " · "}
          {extra}
        </span>
      )}
    </>
  );
}
