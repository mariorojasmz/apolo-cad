import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * Todo texto que lee un usuario va de TÚ, en español neutro latinoamericano:
 * nunca de vos, nunca de usted, sin españolismos. El voseo le suena a otro país
 * a un usuario peruano (en Caronte el reporte fue textual: los agentes «hablaban
 * como argentinos»).
 *
 * **Recorre `src/` entero y lo que se enumera son las EXCEPCIONES**, cada una con
 * su razón: una lista de inclusiones se queda vieja en silencio (los textos que
 * se colaban estaban en archivos que la lista no nombraba), una de exclusiones no.
 *
 * Los comentarios no cuentan. El voseo INTERNO que no es comentario (un prompt
 * AL agente, una vista que sólo ve el equipo) se declara de dos formas:
 *
 *   - **Por archivo**: entrada en `EXCEPCIONES`, con la razón al lado. Cuando el
 *     archivo entero es eso, o cuando lo exento vive dentro de un template
 *     literal, donde un comentario al final de la línea entraría al string.
 *   - **Por línea**: `// voseo-interno` al final. Para archivos mixtos.
 *
 * El marcador por línea cubre además los falsos positivos del detector
 * (`escribí`, `subí`, `pedí`, `abrí` y `decidí` también son pretérito de 1ª
 * persona): se acepta el riesgo porque el fallo muestra la línea y decide una
 * persona.
 */

// ── Configuración del proyecto ────────────────────────────────────────────────

/** Carpeta que se recorre, relativa a este archivo (pensado para vivir en `src/`). */
const RAIZ = join(dirname(fileURLToPath(import.meta.url)), '.');

/** Nunca se recorren, estén donde estén. */
const CARPETAS_IGNORADAS = new Set(['node_modules', '__tests__', 'dist', 'build', 'coverage', 'out']);

/** Archivo exento entero (ruta relativa a RAIZ), con la razón. Si deja de tener voseo, se borra la entrada. */
const EXCEPCIONES = new Map<string, string>([
    // ['lib/agente/prompt.ts', 'prompt AL agente'],
]);

// ── Detectores ────────────────────────────────────────────────────────────────

/**
 * Imperativos del voseo. Todos con acento y por eso inconfundibles: no hay
 * palabra del tuteo que matchee (`revisa`, `espera`, `elige` no llevan tilde).
 * La lista es cerrada: un verbo que no está pasa; se suma cuando se escapa uno.
 */
const IMPERATIVOS = [
    'elegí', 'esperá', 'revisá', 'creá', 'reinstalá', 'activá', 'mirá', 'volvé', 'andá', 'dejá',
    'reintentá', 'escribí', 'pegá', 'subí', 'abrí', 'cerrá', 'seleccioná', 'ingresá', 'completá',
    'confirmá', 'guardá', 'enviá', 'probá', 'intentá', 'usá', 'tocá', 'buscá', 'pedí', 'decí',
    'contá', 'agregá', 'quitá', 'sacá', 'cargá', 'descargá', 'copiá', 'marcá', 'avisá', 'apretá',
    'presioná', 'hacé', 'poné', 'vení', 'tené', 'mandá', 'editá', 'asigná', 'planificá', 'preguntá',
    'arrastrá', 'señalá', 'respondé', 'pasá', 'continuá', 'ajustá', 'lanzá', 'juzgá', 'calificá',
    'decidí', 'apagá', 'asegurá', 'reabrí',
];

/** Presentes del voseo y formas sueltas que no salen de la lista de imperativos. */
const OTRAS = [
    'tenés', 'podés', 'querés', 'resolvela', 'fijate', 'hacelo', 'escribinos', 'decímelo', 'decime',
    'acordate', 'decinos', 'contanos', 'mandanos', 'movete', 'preguntame', 'asignás', 'confirmás',
    'pedís', 'necesitás', 'sabés',
];

/**
 * **El imperativo con pronombre pierde la tilde** («revisá» + «la» = «revisala»;
 * el tú es «revísala»), así que la lista de arriba no lo caza. Las formas se
 * DERIVAN de `IMPERATIVOS` —una lista a mano se queda vieja—; con dos pronombres
 * la tilde vuelve («pedíselo»).
 */
const CLITICOS = ['lo', 'la', 'los', 'las', 'le', 'les', 'me', 'nos', 'te'];
const SIN_TILDE: Record<string, string> = { á: 'a', é: 'e', í: 'i' };
/** Formas derivadas que existen en otro idioma o en el tuteo. */
const NO_ES_VOSEO = new Set(['create', 'mandate']);
const CON_PRONOMBRE = IMPERATIVOS.flatMap((v) => {
    const raiz = v.slice(0, -1) + SIN_TILDE[v.slice(-1)];
    return [
        ...CLITICOS.map((c) => raiz + c),
        ...['se', 'me', 'te', 'nos'].flatMap((a) => ['lo', 'la', 'los', 'las'].map((b) => v + a + b)),
    ];
}).filter((f) => !NO_ES_VOSEO.has(f));

/**
 * El pronombre `vos` suelto va al final: «esto depende de vos» no conjuga ningún
 * verbo y pasaba. `voseo` y `vosotros` no matchean: el lookahead exige que la
 * palabra termine ahí. Y el modismo rioplatense «no te cierra».
 *
 * ⚠️ **`\b` NO sirve acá**: en JS es ASCII, así que `á` es un carácter «no
 * palabra» y `\besperá\b` no matchea *«Esperá a que…»*: el borde final cae
 * entre dos no-palabra. Por eso van lookaround explícitos con las vocales
 * acentuadas y la eñe adentro de la clase.
 */
const VOSEO = new RegExp(
    `(?<![a-záéíóúñ])(${[...IMPERATIVOS, ...OTRAS, ...CON_PRONOMBRE, 'vos', 'no te cierra'].join('|')})(?![a-záéíóúñ])`,
    'i',
);

/**
 * El otro registro que no es el nuestro: el «usted» y los españolismos. Sólo lo
 * inconfundible: «escriba», «complete» o «pulse» también son subjuntivo o inglés
 * («animate-pulse»), y «acá», «añadir» o «recién» se dicen en Perú. Eso lo cuida
 * el estándar de textos, no el gate.
 */
const OTRO_REGISTRO =
    /(?<![a-záéíóúñ])(compruebe|seleccione|verifique|ingrese|elija|introduzca|asegúrese|haga clic|no tiene permiso|inicie sesión|vídeos?|ficheros?|ordenador|pulsa|pulsar|púlsa|ratón)(?![a-záéíóúñ])/i;

/** Marcador de exención por línea. */
const EXENTA = /\/\/\s*voseo-interno\s*$/;

// ── Recorrido ─────────────────────────────────────────────────────────────────

/**
 * Borra los comentarios conservando los saltos de línea (para que los números de
 * línea sigan valiendo). Los `//` dentro de un string (`https://…`) se respetan.
 * Misma función que en `textoDeAyuda.test.ts`: cada gate se sostiene solo.
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

/** Las líneas de `fuente` donde el detector encuentra algo fuera de un comentario y sin marcador. */
export function lineasCon(fuente: string, detector: RegExp): { n: number; linea: string }[] {
    const limpias = sinComentarios(fuente).split('\n');
    return fuente
        .split('\n')
        .map((linea, i) => ({ linea, n: i + 1, limpia: limpias[i] ?? '' }))
        .filter(({ linea, limpia }) => !EXENTA.test(linea) && detector.test(limpia))
        .map(({ n, linea }) => ({ n, linea: linea.trim() }));
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
    return out;
}

const ofensasDe = (rel: string, detector: RegExp) =>
    lineasCon(readFileSync(join(RAIZ, rel), 'utf8'), detector).map(({ n, linea }) => `${rel}:${n}: ${linea}`);

describe('el texto que lee un usuario va en tuteo neutro', () => {
    it('ningún archivo tiene voseo sin declarar', () => {
        const ofensivas = fuentes()
            .filter((rel) => !EXCEPCIONES.has(rel))
            .flatMap((rel) => ofensasDe(rel, VOSEO));
        expect(ofensivas).toEqual([]);
        // El default de 5 s no alcanza: leer `src/` entero con la suite completa
        // corriendo en paralelo se pasa.
    }, 30_000);

    it('ni «usted» ni españolismos', () => {
        const ofensivas = fuentes()
            .filter((rel) => !EXCEPCIONES.has(rel))
            .flatMap((rel) => ofensasDe(rel, OTRO_REGISTRO));
        expect(ofensivas).toEqual([]);
    }, 30_000);

    it('las excepciones siguen existiendo y siguen haciendo falta', () => {
        // Una excepción que ya no aplica es peor que no tenerla: tapa el archivo
        // entero para el próximo texto que entre.
        for (const [rel, razon] of EXCEPCIONES) {
            expect(existsSync(join(RAIZ, rel)), `${rel} ya no existe (${razon})`).toBe(true);
            expect(ofensasDe(rel, VOSEO).length, `${rel} ya no tiene voseo: borra la excepción`).toBeGreaterThan(0);
        }
    }, 30_000);

    it('caza el voseo y deja pasar el tuteo', () => {
        expect(VOSEO.test('`Revisá ${cual}: la revisión automática lo viene rechazando`')).toBe(true);
        expect(VOSEO.test("'Reintentá el alta en un momento: '")).toBe(true);
        expect(VOSEO.test("'Escribí el motivo (mínimo 10 caracteres)'")).toBe(true);
        expect(VOSEO.test("'No tenés permiso para ver esta página.'")).toBe(true);
        expect(VOSEO.test("'Mientras tanto, esto depende de vos.'")).toBe(true);
        expect(VOSEO.test("'Vos lo decides.'")).toBe(true);

        expect(VOSEO.test('`Revisa ${cual}: la revisión automática lo viene rechazando`')).toBe(false);
        expect(VOSEO.test("'Reintenta el alta en un momento: '")).toBe(false);
        expect(VOSEO.test("'Escribe el motivo (mínimo 10 caracteres)'")).toBe(false);
        expect(VOSEO.test("'No tienes permiso para ver esta página.'")).toBe(false);
        // Palabras que empiezan igual y no son voseo.
        expect(VOSEO.test("'Elige una opción…'")).toBe(false);
        expect(VOSEO.test("'contáctanos por la web'")).toBe(false);
        expect(VOSEO.test("'Mientras tanto, esto depende de ti.'")).toBe(false);
        expect(VOSEO.test("'el voseo y vosotros no son el pronombre'")).toBe(false);
    });

    it('caza el pronombre pegado, los verbos sueltos y el modismo', () => {
        expect(VOSEO.test('«¿No te cierra? … o cerralo sin guardar.»')).toBe(true);
        expect(VOSEO.test("'Receta sugerida. Revisala y ajustá antes de guardar.'")).toBe(true);
        expect(VOSEO.test("'Copialo ahora: no se vuelve a mostrar.'")).toBe(true);
        expect(VOSEO.test("'Todavía no hay plan. Pedíselo al agente en el chat.'")).toBe(true);
        expect(VOSEO.test("title='Arrastrá para cambiar el tamaño'")).toBe(true);
        expect(VOSEO.test("'Si asignás un cliente, las notas…'")).toBe(true);

        expect(VOSEO.test("'Receta sugerida. Revísala y ajústala antes de guardar.'")).toBe(false);
        expect(VOSEO.test("'Cópialo ahora: no se vuelve a mostrar.'")).toBe(false);
        expect(VOSEO.test("'Todavía no hay plan. Pídeselo al agente en el chat.'")).toBe(false);
        expect(VOSEO.test("action: 'create'")).toBe(false);
        expect(VOSEO.test("'El modelo y el vuelo del cielo'")).toBe(false);
    });

    it('caza el «usted» y los españolismos inconfundibles, y nada más', () => {
        expect(OTRO_REGISTRO.test("'Compruebe su conexión.'")).toBe(true);
        expect(OTRO_REGISTRO.test("z.string().min(1, 'Seleccione un cliente')")).toBe(true);
        expect(OTRO_REGISTRO.test("'No tiene permiso para acceder a esta página.'")).toBe(true);
        expect(OTRO_REGISTRO.test("'Grabación de pantalla con vídeo'")).toBe(true);
        expect(OTRO_REGISTRO.test("'Pulsa un bloque para editarlo.'")).toBe(true);

        expect(OTRO_REGISTRO.test("'Grabación de pantalla con video'")).toBe(false);
        expect(OTRO_REGISTRO.test('className="animate-pulse"')).toBe(false);
        expect(OTRO_REGISTRO.test("'No tienes permiso para acceder a esta página.'")).toBe(false);
        expect(OTRO_REGISTRO.test("'Elige un cliente'")).toBe(false);
    });

    it('los comentarios no cuentan y el marcador exime su línea y nada más', () => {
        const fuente = [
            "const a = 'Revisa el pedido';",
            '// revisá esto antes del merge',
            "const b = 1; // probá con otro valor",
            '/*',
            '  bloque: mirá el plan',
            '*/',
            "const c = 'Usá la ruta tal cual figura.'; // voseo-interno",
            "const d = 'Usá la ruta tal cual figura.';",
            "const e = 'https://x.com/elegí';",
        ].join('\n');
        expect(lineasCon(fuente, VOSEO).map((x) => x.n)).toEqual([8, 9]);
    });
});
