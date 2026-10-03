import { Fragment, type ReactNode } from "react";

/* Texto técnico del servidor en pantalla: la descripción de un comando (en «Detalle
   técnico») o de un campo (en su ⓘ). Llega limpio de historia desde la vista persona
   (`GET /api/schemas?vista=persona`); acá sólo se le da forma:
   - lo que va entre backticks es un nombre de parámetro o un valor literal → `<code>`;
   - los párrafos (línea en blanco) y las viñetas («- …») se respetan.
   Un texto de una sola línea vuelve sin envoltorio, para ir dentro de cualquier bloque. */

const VINETA = /^[-•]\s+/;

/** Una línea con sus `backticks` como `<code>`; un backtick sin pareja queda literal. */
function enLinea(texto: string): ReactNode[] {
  const partes = texto.split("`");
  if (partes.length % 2 === 0) {
    const huerfana = partes.pop() ?? "";
    partes[partes.length - 1] += "`" + huerfana;
  }
  return partes.map((trozo, i) =>
    i % 2 === 1 ? <code key={i}>{trozo}</code> : <Fragment key={i}>{trozo}</Fragment>,
  );
}

/** Las líneas de un párrafo, con las viñetas seguidas agrupadas en una lista. */
function parrafo(texto: string, clave: number): ReactNode[] {
  const out: ReactNode[] = [];
  let lista: string[] = [];
  const cerrarLista = () => {
    if (!lista.length) return;
    out.push(
      <ul key={`${clave}-${out.length}`}>
        {lista.map((l, i) => (
          <li key={i}>{enLinea(l)}</li>
        ))}
      </ul>,
    );
    lista = [];
  };
  for (const linea of texto.split("\n")) {
    if (VINETA.test(linea)) {
      lista.push(linea.replace(VINETA, ""));
    } else {
      cerrarLista();
      out.push(<p key={`${clave}-${out.length}`}>{enLinea(linea)}</p>);
    }
  }
  cerrarLista();
  return out;
}

/** El texto técnico listo para pintar: `<code>`, párrafos y viñetas. */
export function textoTecnico(texto: string): ReactNode {
  const limpio = texto.trim();
  if (!limpio.includes("\n")) return enLinea(limpio);
  return limpio.split(/\n[ \t]*\n/).flatMap((p, i) => parrafo(p.trim(), i));
}
