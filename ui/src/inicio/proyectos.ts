import type { ProjectInfo } from "../types";
import { grupoFecha, ORDEN_GRUPOS, type GrupoFecha } from "./fechas";

/* Buscar, ordenar y agrupar la lista de proyectos. Funciones puras (sin React) con tests.
   La búsqueda ignora mayúsculas y tildes, y cada palabra debe aparecer en el nombre en
   cualquier orden: «faja 4m» encuentra «faja-paqueteria-4m». */

export type Orden = "recientes" | "nombre";

/** Minúsculas y sin tildes, para comparar como lo escribe una persona. */
export function normalizar(texto: string): string {
  return texto.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/** Palabras de la búsqueda, ya normalizadas; vacío = sin filtro. */
export function palabras(consulta: string): string[] {
  return normalizar(consulta).split(/\s+/).filter(Boolean);
}

export function coincide(nombre: string, buscadas: string[]): boolean {
  const n = normalizar(nombre);
  return buscadas.every((p) => n.includes(p));
}

/** Filtra por la búsqueda y ordena. Recientes = el último guardado primero. */
export function filtrarYOrdenar(lista: ProjectInfo[], consulta: string, orden: Orden): ProjectInfo[] {
  const buscadas = palabras(consulta);
  const filtrada = buscadas.length ? lista.filter((p) => coincide(p.name, buscadas)) : [...lista];
  if (orden === "nombre") {
    return filtrada.sort((a, b) => normalizar(a.name).localeCompare(normalizar(b.name), "es", { numeric: true }));
  }
  return filtrada.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export interface Grupo {
  titulo: GrupoFecha | "Abierto ahora" | null;
  proyectos: ProjectInfo[];
}

/** Grupos para mostrar. Sólo se agrupa por fecha con «Recientes» y sin búsqueda: así la
   lista se lee como una línea de tiempo y el proyecto abierto queda arriba. Con búsqueda u
   orden por nombre va un solo grupo sin título, en el orden recibido. */
export function agrupar(
  lista: ProjectInfo[],
  actual: number | null,
  porFecha: boolean,
  ahora: Date = new Date(),
): Grupo[] {
  if (!porFecha) return lista.length ? [{ titulo: null, proyectos: lista }] : [];
  const grupos: Grupo[] = [];
  const abierto = lista.find((p) => p.id === actual);
  if (abierto) grupos.push({ titulo: "Abierto ahora", proyectos: [abierto] });
  for (const tramo of ORDEN_GRUPOS) {
    const del = lista.filter((p) => p.id !== actual && grupoFecha(p.updated_at, ahora) === tramo);
    if (del.length) grupos.push({ titulo: tramo, proyectos: del });
  }
  return grupos;
}

export interface Tramo {
  texto: string;
  marca: boolean;
}

/** Parte el nombre en tramos para resaltar lo que coincide con la búsqueda. Compara sin
   tildes ni mayúsculas, pero devuelve el texto original. La normalización NFD puede cambiar
   el largo de las letras con tilde, así que se mapea letra por letra. */
export function resaltar(nombre: string, buscadas: string[]): Tramo[] {
  if (!buscadas.length) return [{ texto: nombre, marca: false }];
  const letras = Array.from(nombre);
  const plano = letras.map((c) => normalizar(c));
  const marcadas = new Array<boolean>(letras.length).fill(false);
  const unido = plano.join("");
  // posición en `unido` → índice de letra original
  const indice: number[] = [];
  plano.forEach((p, i) => { for (let k = 0; k < p.length; k++) indice.push(i); });
  for (const p of buscadas) {
    let desde = 0;
    for (;;) {
      const en = unido.indexOf(p, desde);
      if (en < 0) break;
      for (let k = en; k < en + p.length; k++) marcadas[indice[k]] = true;
      desde = en + p.length;
    }
  }
  const tramos: Tramo[] = [];
  letras.forEach((c, i) => {
    const ultimo = tramos[tramos.length - 1];
    if (ultimo && ultimo.marca === marcadas[i]) ultimo.texto += c;
    else tramos.push({ texto: c, marca: marcadas[i] });
  });
  return tramos;
}

/** Color estable por nombre para la inicial de cada proyecto (ayuda a reconocerlo). */
export function tonoDe(nombre: string): number {
  let h = 0;
  for (const c of nombre) h = (h * 31 + c.codePointAt(0)!) % 360;
  return h;
}
