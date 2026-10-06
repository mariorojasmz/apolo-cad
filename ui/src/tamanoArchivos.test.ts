import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Un archivo de código de la UI tiene como máximo 500 líneas (CLAUDE.md raíz § Escala).
 * Un componente de miles de líneas mezcla responsabilidades: nadie lo lee entero y cada
 * cambio choca con el de otra sesión. Gemelo de `tests/test_tamano_archivos.py` (backend).
 *
 * **Trinquete** (el patrón de `textoDeAyuda.test.ts`). `EXCEPCIONES` declara CUÁNTAS
 * líneas tiene hoy cada archivo que ya pasa el tope. Falla si un archivo nuevo (o no
 * declarado) pasa de 500, si uno declarado CRECE por encima de su número (no se sube el
 * número: se saca código a otro módulo), si BAJA sin actualizar el número (la lista sólo
 * se achica, en el mismo commit; en ≤ 500 se borra la entrada) o si ya no existe.
 * Partir un archivo grande se hace con un plan (`docs/plans/`), no de pasada.
 *
 * **Línea** = una línea del archivo como texto: CRLF y LF cuentan igual y el salto final
 * no suma una línea vacía (el mismo conteo que `len(texto.splitlines())` del gate de Python).
 *
 * **Adoptarlo en un proyecto con archivos existentes**: correrlo una vez; imprime las
 * entradas `['archivo', N],` de cada archivo no declarado que pasa el tope. Pegarlas en
 * `EXCEPCIONES` y desde ahí el número sólo baja.
 */

// ── Configuración del proyecto ────────────────────────────────────────────────

/** Carpeta que se recorre, relativa a este archivo (pensado para vivir en `src/`). */
const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '.');

/** Nunca se recorren, estén donde estén. */
const CARPETAS_IGNORADAS = new Set(['node_modules', '__tests__', 'dist', 'build', 'coverage', 'out']);

const TOPE = 500;

/**
 * Cuántas líneas tiene hoy cada archivo que ya pasa el tope (ruta relativa a RAIZ). Al
 * achicar un archivo se baja su número; en ≤ 500, se borra la entrada.
 */
const EXCEPCIONES = new Map<string, number>([
    ['forms/SchemaForm.tsx', 591],
    ['panels/SketcherDialog.tsx', 707],
    ['state/store.ts', 923],
    ['viewport/Viewport.tsx', 1679],
]);

// ── Medición ──────────────────────────────────────────────────────────────────

/** Líneas de un texto: CRLF = LF y un único salto final no abre una línea vacía. */
export function contarLineas(texto: string): number {
    const partes = texto.split(/\r?\n/);
    if (partes[partes.length - 1] === '') partes.pop();
    return partes.length;
}

function fuentes(dir: string = RAIZ, base = ''): string[] {
    const out: string[] = [];
    for (const e of readdirSync(dir, { withFileTypes: true })) {
        const rel = base ? `${base}/${e.name}` : e.name;
        if (e.isDirectory()) {
            if (!CARPETAS_IGNORADAS.has(e.name) && !e.name.startsWith('.')) out.push(...fuentes(join(dir, e.name), rel));
        } else if (/\.tsx?$/.test(e.name) && !/\.(test|spec|stories)\./.test(e.name) && !/\.d\.ts$/.test(e.name)) {
            out.push(rel);
        }
    }
    return out.sort();
}

const lineasDe = (rel: string) => contarLineas(readFileSync(join(RAIZ, rel), 'utf8'));

describe('ningún archivo de la UI pasa de 500 líneas', () => {
    it('ningún archivo pasa el tope más de lo declarado', () => {
        const nuevos: string[] = [];
        const crecieron: string[] = [];
        for (const rel of fuentes()) {
            const n = lineasDe(rel);
            const declarado = EXCEPCIONES.get(rel);
            if (declarado === undefined && n > TOPE) nuevos.push(`    ['${rel}', ${n}],`);
            else if (declarado !== undefined && n > declarado)
                crecieron.push(`${rel}: ${declarado} → ${n} líneas (no subas el número: saca código a otro módulo)`);
        }
        if (nuevos.length) console.log(nuevos.join('\n'));
        expect(nuevos, `más de ${TOPE} líneas sin declarar: parte el archivo`).toEqual([]);
        expect(crecieron, 'archivos congelados que crecieron').toEqual([]);
        // Leer `src/` entero con la suite en paralelo puede pasar los 5 s por defecto.
    }, 30_000);

    it('trinquete: cada excepción declara exactamente lo que queda', () => {
        for (const [rel, declarado] of EXCEPCIONES) {
            expect(existsSync(join(RAIZ, rel)), `${rel} ya no existe: borra la entrada`).toBe(true);
            const n = lineasDe(rel);
            expect(n > TOPE, `${rel}: ya cumple (${n} ≤ ${TOPE}): borra la entrada`).toBe(true);
            // si CRECIÓ, lo reporta el caso de arriba
            expect(n >= declarado, `${rel}: bajó de ${declarado} a ${n}: actualiza el número`).toBe(true);
        }
    });

    it('cuenta líneas como un editor', () => {
        expect(contarLineas('')).toBe(0);
        expect(contarLineas('a')).toBe(1);
        expect(contarLineas('a\nb')).toBe(2);
        expect(contarLineas('a\nb\n')).toBe(2); // el salto final no suma
        expect(contarLineas('a\n\n')).toBe(2); // una línea vacía real sí
        expect(contarLineas('\n')).toBe(1);
    });

    it('CRLF y LF cuentan igual', () => {
        expect(contarLineas('a\r\nb\r\n')).toBe(2);
        expect(contarLineas('a\r\nb')).toBe(2);
        expect(contarLineas('a\r\n\r\n')).toBe(contarLineas('a\n\n'));
    });
});
