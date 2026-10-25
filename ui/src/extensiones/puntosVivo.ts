import type { ChipVivo, Extension, Pantalla3D } from "./tipos";

/* Los puntos de la sesión viva que trae una extensión (plan plc-en-el-lazo, D13): chips de la barra
   y pantallas 3D. Aquí se validan (los llama `registro.ts`, que junta todos los problemas en un
   mensaje) y se juntan en orden para quien los pinta (`vivo/ChipsVivo.tsx`, `vivo/pantallas3d.ts`).
   Puro: sin React ni three.js. */

const RESTO_DEL_ID = /^[a-z][a-z0-9_-]*$/;
/** El `tipo` de un dispositivo de la tabla del `inicio` (`hmi`, `plc`, `rele_seguridad`…). */
const TIPO = /^[a-z][a-z0-9_]*$/;

const esComponente = (v: unknown) => typeof v === "function" || (typeof v === "object" && v !== null);

function idMalo(carpeta: string, id: string): boolean {
  const prefijo = `${carpeta}.`;
  return !id.startsWith(prefijo) || !RESTO_DEL_ID.test(id.slice(prefijo.length));
}

/** Problemas de los chips y las pantallas de UNA extensión (ya con nombre válido); [] si están bien. */
export function problemasPuntosVivo(carpeta: string, ext: Record<string, unknown>): string[] {
  const out: string[] = [];
  const { chipsVivo, pantallas3d } = ext;
  if (chipsVivo !== undefined) {
    if (!Array.isArray(chipsVivo)) out.push(`${carpeta}: «chipsVivo» tiene que ser una lista`);
    else for (const c of chipsVivo as unknown[]) {
      const chip = (c ?? {}) as Record<string, unknown>;
      const id = String(chip.id);
      if (idMalo(carpeta, id)) out.push(`${carpeta}: el chip «${id}» tiene que llamarse «${carpeta}.<chip>»`);
      if (!esComponente(chip.Componente)) out.push(`${carpeta}: al chip «${id}» le falta el componente`);
    }
  }
  if (pantallas3d !== undefined) {
    if (!Array.isArray(pantallas3d)) out.push(`${carpeta}: «pantallas3d» tiene que ser una lista`);
    else for (const p of pantallas3d as unknown[]) {
      const pantalla = (p ?? {}) as Record<string, unknown>;
      const id = String(pantalla.id);
      if (idMalo(carpeta, id)) out.push(`${carpeta}: la pantalla «${id}» tiene que llamarse «${carpeta}.<pantalla>»`);
      if (typeof pantalla.tipo !== "string" || !TIPO.test(pantalla.tipo))
        out.push(`${carpeta}: la pantalla «${id}» necesita el tipo de dispositivo que pinta, en minúsculas (p. ej. «hmi»)`);
      if (typeof pantalla.dibujar !== "function") out.push(`${carpeta}: a la pantalla «${id}» le falta «dibujar» (una función)`);
      if (pantalla.tocar !== undefined && typeof pantalla.tocar !== "function")
        out.push(`${carpeta}: «tocar» de la pantalla «${id}» tiene que ser una función`);
    }
  }
  return out;
}

/** Problemas ENTRE extensiones ya válidas: un id de chip o de pantalla repetido, o dos pantallas
   para el mismo tipo de dispositivo (pintarían el mismo plano). */
export function choquesPuntosVivo(extensiones: readonly Extension[]): string[] {
  const out: string[] = [];
  const chips = new Set<string>();
  const pantallas = new Set<string>();
  const porTipo = new Map<string, string>();
  for (const ext of extensiones) {
    for (const c of ext.chipsVivo ?? []) {
      if (chips.has(c.id)) out.push(`${ext.nombre}: el chip «${c.id}» está repetido`);
      chips.add(c.id);
    }
    for (const p of ext.pantallas3d ?? []) {
      if (pantallas.has(p.id)) out.push(`${ext.nombre}: la pantalla «${p.id}» está repetida`);
      pantallas.add(p.id);
      const otra = porTipo.get(p.tipo);
      if (otra && otra !== p.id) out.push(`${ext.nombre}: el tipo «${p.tipo}» ya lo pinta la pantalla «${otra}»`);
      else porTipo.set(p.tipo, p.id);
    }
  }
  return out;
}

/** Los chips de todas las extensiones, en orden. */
export function chipsDe(extensiones: readonly Extension[]): ChipVivo[] {
  return extensiones.flatMap((e) => e.chipsVivo ?? []);
}

/** Las pantallas de todas las extensiones, en orden. */
export function pantallasDe(extensiones: readonly Extension[]): Pantalla3D[] {
  return extensiones.flatMap((e) => e.pantallas3d ?? []);
}
