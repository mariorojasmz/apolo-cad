import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * El texto de ayuda tiene tope (DESIGN.md §Texto y ayuda). «¿Se entiende sin
 * explicación?» lo decide cada uno distinto; el largo no. Este gate mide lo que
 * se puede medir sobre los literales:
 *
 *   - subtítulo de página: una frase, ≤ 100 caracteres (el alcance, o nada).
 *   - pista (`hint=` o `<Pista>`): una frase, ≤ 120 caracteres.
 *   - ⓘ (`<Ayuda>`): ≤ 60 palabras (más que eso es «Ver detalle» o «Cómo funciona»).
 *   - la historia en pantalla («plan 123») fuera de un comentario: vive en `docs/plans/`.
 *   - props retiradas: las que hacen lo mismo que otra y se dejan de usar.
 *
 * No ve lo que viaja en constantes o expresiones (`hint={texto}`): se acepta.
 *
 * **Trinquete.** `EXCEPCIONES` declara, archivo por archivo, CUÁNTAS violaciones
 * tiene hoy. Si sube, falla (texto nuevo que no cumple); si baja, también falla
 * hasta que se actualice el número. La lista sólo se achica, y se achica en el
 * mismo commit que limpia.
 *
 * **Adoptarlo en un proyecto con texto existente**: correrlo una vez; imprime las
 * entradas `['archivo', N],` de cada archivo que no cumple. Pegarlas en
 * `EXCEPCIONES` y desde ahí el número sólo baja.
 */

// ── Configuración del proyecto ────────────────────────────────────────────────

/** Carpeta que se recorre, relativa a este archivo (pensado para vivir en `src/`). */
const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '.');

/** Carpetas (relativas a RAIZ) que otra sesión está rehaciendo o que no son pantalla. */
const CARPETAS_AFUERA: string[] = [];

/** Nunca se recorren, estén donde estén. */
const CARPETAS_IGNORADAS = new Set(['node_modules', '__tests__', 'dist', 'build', 'coverage', 'out']);

const TOPES = {
    subtitulo: { frases: 1, caracteres: 100 },
    pista: { frases: 1, caracteres: 120 },
    ayuda: { palabras: 60 },
};

/**
 * Nombres de las props y piezas del proyecto (`<Pista>` y `<Ayuda>` viven en `src/ui/`). Las
 * pistas de los comandos llegan del backend (dinámicas): este gate no las ve; las mide su
 * gemelo de backend, `tests/test_pistas.py`, con los mismos criterios.
 */
const PROP_SUBTITULO = 'subtitle';
const PROP_PISTA = 'hint';
const PIEZA_PISTA = 'Pista';
const PIEZA_AYUDA = 'Ayuda';

/**
 * La historia que no va en pantalla. En Apolo el «número de plan» es la versión del
 * roadmap: V6.8-E, V7.2b, V6.4c (`docs/plans/V*.md`).
 */
const HISTORIA: { regla: string; re: RegExp }[] = [
    { regla: 'número de plan en pantalla', re: /\bplan \d{2,4}\b/gi },
    { regla: 'versión del roadmap en pantalla', re: /\bV\d+(?:\.\d+)?[a-z]?(?:-[A-Z])?(?![\w.])/g },
];

/** Props que se retiran: `{ componente: 'PageLayout', prop: 'description', usa: 'subtitle' }`. */
export interface PropRetirada {
    componente: string;
    prop: string;
    usa: string;
}
const PROPS_RETIRADAS: PropRetirada[] = [];

/**
 * Cuántas violaciones tiene hoy cada archivo (ruta relativa a RAIZ). Al limpiar, se
 * baja el número; en 0, se borra la entrada.
 */
const EXCEPCIONES = new Map<string, number>([
    // ['components/Ejemplo.tsx', 3],
]);

// ── Medición ──────────────────────────────────────────────────────────────────

/** Oración nueva: signo de cierre, espacio y algo que arranca oración. */
const FIN_DE_ORACION = /[.!?…]\s+(?=[A-ZÁÉÍÓÚÜÑ0-9¿¡«("])/g;

export function frases(texto: string): number {
    const limpio = texto.replace(/\s+/g, ' ').trim();
    if (!limpio) return 0;
    return 1 + (limpio.match(FIN_DE_ORACION)?.length ?? 0);
}

const palabras = (texto: string) => texto.split(/\s+/).filter(Boolean).length;

/** El texto de un hijo JSX sin etiquetas ni expresiones: lo que se lee. */
function textoDeJsx(fuente: string): string {
    return fuente
        .replace(/\{[^{}]*\}/g, ' ')
        .replace(/<[^>]+>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

/**
 * Borra los comentarios conservando los saltos de línea (para que los números de
 * línea sigan valiendo). Los `//` dentro de un string (`https://…`) se respetan.
 */
export function sinComentarios(texto: string): string {
    const sinBloques = texto.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
    return sinBloques
        .split('\n')
        .map((linea) => {
            let comilla: string | null = null;
            for (let i = 0; i < linea.length - 1; i++) {
                const c = linea[i];
                if (comilla) {
                    if (c === '\\') i++;
                    else if (c === comilla) comilla = null;
                } else if (c === "'" || c === '"' || c === '`') {
                    comilla = c;
                } else if (c === '/' && linea[i + 1] === '/') {
                    return linea.slice(0, i);
                }
            }
            return linea;
        })
        .join('\n');
}

/**
 * La etiqueta de apertura de cada `<Nombre …>`: hasta el `>` fuera de llaves y
 * strings, para que una flecha (`() => a > b`) dentro de una prop no la corte.
 */
function aperturasDe(texto: string, nombre: string): { props: string; indice: number; fin: number }[] {
    const out: { props: string; indice: number; fin: number }[] = [];
    const re = new RegExp(`<${nombre}(?![A-Za-z0-9_.])`, 'g');
    let m: RegExpExecArray | null;
    while ((m = re.exec(texto))) {
        let profundidad = 0;
        let comilla: string | null = null;
        let i = m.index + m[0].length;
        for (; i < texto.length; i++) {
            const c = texto[i];
            if (comilla) {
                if (c === '\\') i++;
                else if (c === comilla) comilla = null;
            } else if (c === '"' || c === "'" || c === '`') comilla = c;
            else if (c === '{') profundidad++;
            else if (c === '}') profundidad--;
            else if (c === '>' && profundidad === 0) break;
        }
        out.push({ props: texto.slice(m.index, i), indice: m.index, fin: i + 1 });
    }
    return out;
}

/** Lo que va entre `<Nombre …>` y `</Nombre>`. Las autocerradas no tienen hijos. */
function hijosDe(texto: string, nombre: string): { hijos: string; indice: number }[] {
    const out: { hijos: string; indice: number }[] = [];
    for (const { props, indice, fin } of aperturasDe(texto, nombre)) {
        if (props.trimEnd().endsWith('/')) continue;
        const cierre = texto.indexOf(`</${nombre}>`, fin);
        if (cierre !== -1) out.push({ hijos: texto.slice(fin, cierre), indice });
    }
    return out;
}

/** `prop="…"`, `prop='…'`, `prop={"…"}` y `` prop={`…`} `` sin interpolar. */
function literalesDeProp(texto: string, prop: string): { valor: string; indice: number }[] {
    const re = new RegExp(`\\b${prop}=(?:\\{\\s*)?(?:"([^"]*)"|'([^']*)'|\`([^\`$]*)\`)`, 'g');
    return [...texto.matchAll(re)].map((m) => ({ valor: m[1] ?? m[2] ?? m[3], indice: m.index! }));
}

export interface Violacion {
    linea: number;
    regla: string;
    texto: string;
}

export function violaciones(fuente: string, retiradas: PropRetirada[] = PROPS_RETIRADAS): Violacion[] {
    const t = sinComentarios(fuente);
    const lineaDe = (indice: number) => t.slice(0, indice).split('\n').length;
    const recorte = (s: string) => (s.length > 90 ? `${s.slice(0, 90)}…` : s);
    const out: Violacion[] = [];
    const { subtitulo, pista, ayuda } = TOPES;
    const reglaSubtitulo = `subtítulo: ${subtitulo.frases} frase, ≤ ${subtitulo.caracteres}`;
    const reglaPista = `pista: ${pista.frases} frase, ≤ ${pista.caracteres}`;

    for (const { valor, indice } of literalesDeProp(t, PROP_SUBTITULO)) {
        if (frases(valor) > subtitulo.frases || valor.length > subtitulo.caracteres)
            out.push({ linea: lineaDe(indice), regla: reglaSubtitulo, texto: recorte(valor) });
    }
    for (const { valor, indice } of literalesDeProp(t, PROP_PISTA)) {
        if (frases(valor) > pista.frases || valor.length > pista.caracteres)
            out.push({ linea: lineaDe(indice), regla: reglaPista, texto: recorte(valor) });
    }
    for (const { hijos, indice } of hijosDe(t, PIEZA_PISTA)) {
        const s = textoDeJsx(hijos);
        if (frases(s) > pista.frases || s.length > pista.caracteres)
            out.push({ linea: lineaDe(indice), regla: reglaPista, texto: recorte(s) });
    }
    for (const { hijos, indice } of hijosDe(t, PIEZA_AYUDA)) {
        const s = textoDeJsx(hijos);
        if (palabras(s) > ayuda.palabras)
            out.push({ linea: lineaDe(indice), regla: `ⓘ: ≤ ${ayuda.palabras} palabras`, texto: recorte(s) });
    }
    for (const { regla, re } of HISTORIA) {
        for (const m of t.matchAll(re)) out.push({ linea: lineaDe(m.index!), regla, texto: m[0] });
    }
    for (const { componente, prop, usa } of retiradas) {
        for (const { props, indice } of aperturasDe(t, componente)) {
            if (new RegExp(`\\s${prop}=`).test(props))
                out.push({ linea: lineaDe(indice), regla: `\`${prop}\` de ${componente} (usa \`${usa}\`)`, texto: '' });
        }
    }
    return out;
}

function fuentes(dir: string = RAIZ, base = ''): string[] {
    const out: string[] = [];
    for (const e of readdirSync(dir, { withFileTypes: true })) {
        const rel = base ? `${base}/${e.name}` : e.name;
        if (e.isDirectory()) {
            if (!CARPETAS_IGNORADAS.has(e.name) && !e.name.startsWith('.')) out.push(...fuentes(join(dir, e.name), rel));
        } else if (/\.[jt]sx?$/.test(e.name) && !/\.(test|spec|stories)\./.test(e.name) && !/\.d\.ts$/.test(e.name)) {
            out.push(rel);
        }
    }
    return out.filter((rel) => !CARPETAS_AFUERA.some((c) => rel.startsWith(c)));
}

const violacionesDe = (rel: string) => violaciones(readFileSync(join(RAIZ, rel), 'utf8'));

describe('el texto de ayuda respeta sus topes', () => {
    it('ningún archivo pasa sus topes más de lo declarado', () => {
        const ofensas: string[] = [];
        const propuesta: string[] = [];
        for (const rel of fuentes()) {
            const v = violacionesDe(rel);
            const permitidas = EXCEPCIONES.get(rel) ?? 0;
            if (v.length > permitidas) {
                ofensas.push(...v.map((x) => `${rel}:${x.linea}: ${x.regla} — ${x.texto}`));
                propuesta.push(`    ['${rel}', ${v.length}],`);
            }
        }
        if (propuesta.length) console.log(propuesta.join('\n'));
        expect(ofensas).toEqual([]);
        // Leer `src/` entero con la suite en paralelo pasa los 5 s por defecto.
    }, 30_000);

    it('trinquete: cada excepción declara exactamente lo que queda', () => {
        for (const [rel, n] of EXCEPCIONES) {
            expect(existsSync(join(RAIZ, rel)), `${rel} ya no existe: borra la entrada`).toBe(true);
            expect(violacionesDe(rel).length, `${rel}: bajó; actualiza el número (en 0, borra la entrada)`).toBe(n);
        }
    }, 30_000);

    it('cuenta frases como las cuenta una persona', () => {
        expect(frases('Uno por línea, sin https://.')).toBe(1);
        expect(frases('Cuántos turnos máx. por corrida tolera el agente.')).toBe(1);
        expect(frases('Default 48. Se borra si nadie lo usa.')).toBe(2);
        expect(frases('Porcentaje de la base. 100 = la de siempre.')).toBe(2);
        expect(frases('¿Seguro? Sí.')).toBe(2);
    });

    it('rebota lo largo y deja pasar lo corto', () => {
        const largo = 'x'.repeat(130);
        expect(violaciones(`<Campo label="A" hint="Uno por línea.">`)).toEqual([]);
        expect(violaciones(`<Campo label="A" hint="Default 48. Se borra solo.">`)).toHaveLength(1);
        expect(violaciones(`<Campo label="A" hint='Default 48. Se borra solo.'>`)).toHaveLength(1);
        expect(violaciones(`<Campo label="A" hint={"Default 48. Se borra solo."}>`)).toHaveLength(1);
        expect(violaciones(`<Campo label="A" hint="${largo}">`)).toHaveLength(1);
        expect(violaciones(`<Campo label="A" hint={texto}>`)).toEqual([]);
        expect(violaciones(`<Pagina title="Usuarios" subtitle="De tu empresa">`)).toEqual([]);
        expect(violaciones(`<Pagina title="X" subtitle="Una. Dos.">`)).toHaveLength(1);
        expect(violaciones(`<Pista>Uno por línea. Y otra cosa.</Pista>`)).toHaveLength(1);
        expect(violaciones(`<Pista className="x">Uno por línea.</Pista>`)).toEqual([]);
        expect(violaciones(`<Ayuda titulo="X">${'palabra '.repeat(61)}</Ayuda>`)).toHaveLength(1);
        expect(violaciones(`<Ayuda>${'palabra '.repeat(61)}</Ayuda>`)).toHaveLength(1);
        expect(violaciones(`<Ayuda titulo="X">${'palabra '.repeat(20)}</Ayuda>`)).toEqual([]);
        expect(violaciones(`<AyudaGrande>${'palabra '.repeat(61)}</AyudaGrande>`)).toEqual([]);
    });

    it('la versión del roadmap cuenta como historia', () => {
        expect(violaciones(`const a = 'Entrada declarativa (V6.8-E)';`)).toHaveLength(1);
        expect(violaciones(`const a = 'Tablas de diseño (V6.4c)';`)).toHaveLength(1);
        expect(violaciones(`const a = 'desde V7.2';`)).toHaveLength(1);
        expect(violaciones(`// V6.6: arrastre con dead-zone\nconst a = 1;`)).toEqual([]);
        expect(violaciones(`const a = '220V';`)).toEqual([]);
        expect(violaciones(`const a = 'Vista 3D';`)).toEqual([]);
    });

    it('la historia cuenta en un string y no en un comentario', () => {
        expect(violaciones(`const a = 'Escribir el mapa (plan 026)';`)).toHaveLength(1);
        expect(violaciones(`// el corte del plan 124\nconst a = 1;`)).toEqual([]);
        expect(violaciones(`{/* dvh y no vh (plan 089 F3) */}`)).toEqual([]);
        expect(violaciones(`const u = 'https://x.com'; // plan 172`)).toEqual([]);
        expect(violaciones(`const plan1 = planes[0];`)).toEqual([]);
    });

    it('una prop retirada cuenta aunque las props traigan JSX y flechas', () => {
        const retirada = [{ componente: 'Pagina', prop: 'description', usa: 'subtitle' }];
        const con = `<Pagina\n  title="X"\n  accion={<Btn onClick={() => a > b} />}\n  description={<p>hola</p>}>\n</Pagina>`;
        const sin = `<Pagina\n  title="X"\n  accion={<Btn onClick={() => a > b} />}>\n  <Card description="no es de la página" />\n</Pagina>`;
        expect(violaciones(con, retirada)).toHaveLength(1);
        expect(violaciones(sin, retirada)).toEqual([]);
    });
});
