import type { ReactNode } from "react";

/* Pista (N1 de ui/CLAUDE.md § Texto y ayuda): contesta «¿qué tengo que hacer aquí?»,
   siempre visible, bajo el campo o la acción. Una frase, ≤ 120 caracteres: el gate
   `textoDeAyuda.test.ts` mide los literales; las pistas que llegan del servidor las mide
   `tests/test_pistas.py`. */

export default function Pista({ children }: { children: ReactNode }) {
  return <p className="pista">{children}</p>;
}
