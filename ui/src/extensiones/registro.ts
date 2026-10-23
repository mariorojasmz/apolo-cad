/// <reference types="vite/client" />
import type { Extension } from "./tipos";

/* Registro de las extensiones de la UI (plan núcleo-abierto-extensiones-privadas, D5). El núcleo
   lo publica VACÍO: no trae ninguna carpeta dentro de `src/extensiones/` (el `.gitignore` de `ui/`
   las ignora). Un paquete privado compila la UI copiando su `ui/` en `src/extensiones/<nombre>/`
   de un checkout del núcleo; su `index.ts` (o `.tsx`) exporta por defecto un objeto `Extension`
   (`tipos.ts`). Nada del núcleo se edita: el glob la recoge al compilar, y los gates de texto y de
   tamaño la recorren porque vive dentro de `src/`.

   Una extensión mal formada rompe al cargar el módulo, con TODOS sus problemas en el mensaje: la
   ve su propia suite (vitest importa este registro), no una persona. */

type Modulos = Record<string, { default?: unknown }>;

const MODULOS: Modulos = import.meta.glob("./*/index.{ts,tsx}", { eager: true });

const NOMBRE = /^[a-z][a-z0-9_-]*$/;
const RESTO_DEL_ID = /^[a-z][a-z0-9_-]*$/;

const esTexto = (v: unknown): v is string => typeof v === "string" && v.trim() !== "";
const esComponente = (v: unknown) => typeof v === "function" || (typeof v === "object" && v !== null);

/** Problemas de UNA extensión recogida de `./<carpeta>/index.ts`; [] si está bien. */
function problemasDe(carpeta: string, ext: unknown): string[] {
  if (typeof ext !== "object" || ext === null) return [`${carpeta}: el index no exporta por defecto una extensión`];
  const { nombre, paneles } = ext as Partial<Extension>;
  if (nombre !== carpeta) return [`${carpeta}: el nombre (${String(nombre)}) tiene que ser el de su carpeta`];
  if (!NOMBRE.test(carpeta)) return [`${carpeta}: el nombre va en minúsculas, sin espacios ni puntos`];
  if (paneles === undefined) return [];
  if (!Array.isArray(paneles)) return [`${carpeta}: «paneles» tiene que ser una lista`];
  const out: string[] = [];
  for (const p of paneles as unknown[]) {
    const panel = (p ?? {}) as Record<string, unknown>;
    const id = String(panel.id);
    const prefijo = `${carpeta}.`;
    if (!id.startsWith(prefijo) || !RESTO_DEL_ID.test(id.slice(prefijo.length)))
      out.push(`${carpeta}: el panel «${id}» tiene que llamarse «${prefijo}<panel>»`);
    if (!esTexto(panel.titulo) || !esTexto(panel.rotulo)) out.push(`${carpeta}: al panel «${id}» le falta título o rótulo`);
    if (!esComponente(panel.Componente) || !esComponente(panel.icono))
      out.push(`${carpeta}: al panel «${id}» le falta el componente o el ícono`);
  }
  return out;
}

/** Valida lo que recogió el glob y devuelve las extensiones en orden de nombre (el orden de sus
   paneles en la barra no depende del sistema de archivos). Lanza con todos los problemas juntos. */
export function validarExtensiones(modulos: Modulos): Extension[] {
  const problemas: string[] = [];
  const extensiones: Extension[] = [];
  const ids = new Set<string>();
  for (const [ruta, modulo] of Object.entries(modulos)) {
    const carpeta = ruta.split("/")[1] ?? ruta;
    const errores = problemasDe(carpeta, modulo.default);
    problemas.push(...errores);
    if (errores.length) continue;
    const ext = modulo.default as Extension;
    for (const p of ext.paneles ?? []) {
      if (ids.has(p.id)) problemas.push(`${carpeta}: el panel «${p.id}» está repetido`);
      ids.add(p.id);
    }
    extensiones.push(ext);
  }
  if (problemas.length) throw new Error(`Extensiones de la UI mal formadas:\n${problemas.join("\n")}`);
  return extensiones.sort((a, b) => a.nombre.localeCompare(b.nombre));
}

/** Las extensiones compiladas en este bundle; en el núcleo, ninguna. */
export const EXTENSIONES: readonly Extension[] = validarExtensiones(MODULOS);
