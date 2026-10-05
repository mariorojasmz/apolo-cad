import { describe, expect, it } from 'vitest';
import { crearLectorSse, eventosSse, validar, type EventoChat } from './sse';

/** Un evento como lo escribe el backend (`_sse` del chat viejo y el chat nuevo). */
const frame = (dato: unknown) => `data: ${JSON.stringify(dato)}\n\n`;

/** Un turno con todos los tipos del protocolo, incluido uno desconocido. */
const TURNO = [
    { type: 'progreso', text: 'Leo el modelo.' },
    { type: 'tool', name: 'get_scene', etiqueta: 'Leyendo el modelo' },
    { type: 'tool', name: 'undo_last' },
    { type: 'turno_futuro', algo: 1 },
    { type: 'text', text: 'Listo: añadí la ménsula «A».' },
    { type: 'actions', actions: [{ type: 'create_box', params: { width: 10 }, reason: 'r' }], executed: true },
    { type: 'aviso', motivo: 'max_tokens', mensaje: 'La respuesta se cortó: pídeme que continúe.', max_tokens: 16000 },
    { type: 'error', message: 'Error del API de Claude: x' },
    { type: 'done', uso: { input: 30, output: 9, cache_read: 1200, cache_creation: 0 } },
];
const STREAM = TURNO.map(frame).join('');
const ESPERADOS: EventoChat[] = [
    { type: 'progreso', text: 'Leo el modelo.' },
    { type: 'tool', name: 'get_scene', etiqueta: 'Leyendo el modelo' },
    { type: 'tool', name: 'undo_last' },
    { type: 'text', text: 'Listo: añadí la ménsula «A».' },
    { type: 'actions', actions: [{ type: 'create_box', params: { width: 10 }, reason: 'r' }], executed: true },
    { type: 'aviso', motivo: 'max_tokens', mensaje: 'La respuesta se cortó: pídeme que continúe.' },
    { type: 'error', message: 'Error del API de Claude: x' },
    { type: 'done', uso: { input: 30, output: 9, cache_read: 1200, cache_creation: 0 } },
];

/** Pasa los trozos por un lector y junta eventos y descartes. */
function leer(trozos: string[]) {
    const descartes: string[] = [];
    const lector = crearLectorSse((d) => descartes.push(d));
    const eventos = trozos.flatMap((t) => lector.push(t));
    eventos.push(...lector.fin());
    return { eventos, descartes };
}

/** Un cuerpo de `fetch` que entrega los bytes en los trozos dados. */
function cuerpo(trozos: Uint8Array[]) {
    let cancelado = false;
    let i = 0;
    const stream = new ReadableStream<Uint8Array>({
        pull(c) {
            if (i < trozos.length) c.enqueue(trozos[i++]);
            else c.close();
        },
        cancel() {
            cancelado = true;
        },
    });
    return { stream, cancelado: () => cancelado };
}

async function todos(stream: ReadableStream<Uint8Array>, alDescartar?: (d: string) => void) {
    const out: EventoChat[] = [];
    for await (const ev of eventosSse(stream, alDescartar)) out.push(ev);
    return out;
}

describe('el parser del SSE del chat', () => {
    it('entrega cada tipo tipado y en orden, e ignora el desconocido', () => {
        const { eventos, descartes } = leer([STREAM]);
        expect(eventos).toEqual(ESPERADOS);
        expect(descartes).toEqual([]);
    });

    it('da lo mismo con un corte en CUALQUIER posición', () => {
        for (let i = 0; i <= STREAM.length; i++) {
            expect(leer([STREAM.slice(0, i), STREAM.slice(i)]).eventos, `corte en ${i}`).toEqual(ESPERADOS);
        }
    });

    it('da lo mismo carácter a carácter y en trozos de tamaños variados', () => {
        expect(leer([...STREAM]).eventos).toEqual(ESPERADOS);
        for (const n of [2, 3, 7, 13, 64]) {
            const trozos: string[] = [];
            for (let i = 0; i < STREAM.length; i += n) trozos.push(STREAM.slice(i, i + n));
            expect(leer(trozos).eventos, `trozos de ${n}`).toEqual(ESPERADOS);
        }
    });

    it('un trozo con varios eventos y la mitad del siguiente los entrega a medida que se completan', () => {
        const lector = crearLectorSse();
        const a = frame({ type: 'text', text: 'uno' });
        const b = frame({ type: 'text', text: 'dos' });
        const c = frame({ type: 'done' });
        expect(lector.push(a + b + c.slice(0, 5))).toEqual([
            { type: 'text', text: 'uno' },
            { type: 'text', text: 'dos' },
        ]);
        expect(lector.push(c.slice(5))).toEqual([{ type: 'done' }]);
    });

    it('acepta \\r\\n (también partido entre trozos) y \\r solo', () => {
        const crlf = STREAM.replace(/\n/g, '\r\n');
        expect(leer([crlf]).eventos).toEqual(ESPERADOS);
        for (let i = 0; i <= crlf.length; i++) {
            expect(leer([crlf.slice(0, i), crlf.slice(i)]).eventos, `corte en ${i}`).toEqual(ESPERADOS);
        }
        expect(leer([STREAM.replace(/\n/g, '\r')]).eventos).toEqual(ESPERADOS);
        // `\r` final = fin de línea: el último evento se despacha al cerrar
        expect(leer([`data: {"type":"done"}\r\r`]).eventos).toEqual([{ type: 'done' }]);
    });

    it('ignora comentarios y otros campos, junta los `data:` y acepta `data:` sin espacio', () => {
        const crudo = [
            ': latido',
            'event: mensaje',
            'id: 7',
            'data:{"type":"text",',
            'data: "text":"hola"}',
            '',
            'retry: 1000',
            '',
            '',
        ].join('\n');
        const { eventos, descartes } = leer([crudo]);
        expect(eventos).toEqual([{ type: 'text', text: 'hola' }]);
        expect(descartes).toEqual([]);
    });

    it('JSON roto: se descarta, se avisa y el stream SIGUE', () => {
        const crudo = 'data: {"type":"text","text":"a\n\n' + frame({ type: 'text', text: 'b' }) + frame({ type: 'done' });
        const { eventos, descartes } = leer([crudo]);
        expect(eventos).toEqual([{ type: 'text', text: 'b' }, { type: 'done' }]);
        expect(descartes).toHaveLength(1);
        expect(descartes[0]).toMatch(/^JSON inválido: \{"type":"text"/);
    });

    it('lo que no es un evento o le faltan campos se descarta con su motivo', () => {
        const malos = [[1, 2], 'hola', null, { text: 'sin tipo' }, { type: 'text' }, { type: 'tool' },
            { type: 'actions', actions: 'x' }, { type: 'aviso', motivo: 'refusal' }, { type: 'error' }];
        const { eventos, descartes } = leer([...malos.map(frame), frame({ type: 'done' })]);
        expect(eventos).toEqual([{ type: 'done' }]);
        expect(descartes.map((d) => d.split(':')[0])).toEqual([
            'no es un objeto', 'no es un objeto', 'no es un objeto', 'sin `type`', '`text` sin `text`',
            '`tool` sin `name`', '`actions` sin `actions`', '`aviso` sin `mensaje`', '`error` sin `message`',
        ]);
    });

    it('el descarte recorta el crudo largo', () => {
        const { descartes } = leer([`data: {${'x'.repeat(1000)}\n\n`]);
        expect(descartes[0].length).toBeLessThan(260);
        expect(descartes[0].endsWith('…')).toBe(true);
    });

    it('un evento a medias al cerrar no se despacha y se avisa', () => {
        const { eventos, descartes } = leer([frame({ type: 'text', text: 'a' }), 'data: {"type":"done"}']);
        expect(eventos).toEqual([{ type: 'text', text: 'a' }]);
        expect(descartes).toEqual(['evento incompleto al cerrar: {"type":"done"}']);
        expect(leer(['data: {"type":"done"}\n']).descartes).toHaveLength(1);
    });

    it('sin descartador, un descarte no tira', () => {
        const lector = crearLectorSse();
        expect(lector.push('data: {roto\n\n' + frame({ type: 'done' }))).toEqual([{ type: 'done' }]);
    });
});

describe('validar: la forma de cada evento', () => {
    it('tool: la etiqueta sólo si es texto no vacío', () => {
        expect(validar({ type: 'tool', name: 'n', etiqueta: 'Leyendo' })).toEqual({ type: 'tool', name: 'n', etiqueta: 'Leyendo' });
        expect(validar({ type: 'tool', name: 'n', etiqueta: '  ' })).toEqual({ type: 'tool', name: 'n' });
        expect(validar({ type: 'tool', name: 'n', etiqueta: 3 })).toEqual({ type: 'tool', name: 'n' });
    });

    it('actions: `executed` sólo con true; aviso sin motivo = otro', () => {
        expect(validar({ type: 'actions', actions: [] })).toEqual({ type: 'actions', actions: [], executed: false });
        expect(validar({ type: 'aviso', mensaje: 'm' })).toEqual({ type: 'aviso', motivo: 'otro', mensaje: 'm' });
    });

    it('done: `uso` opcional; lo que falte o no sea número cuenta 0', () => {
        expect(validar({ type: 'done' })).toEqual({ type: 'done' });
        expect(validar({ type: 'done', uso: 'x' })).toEqual({ type: 'done' });
        expect(validar({ type: 'done', uso: { input: 5, output: 'x' } })).toEqual({
            type: 'done', uso: { input: 5, output: 0, cache_read: 0, cache_creation: 0 },
        });
    });

    it('un tipo desconocido devuelve null (se ignora sin avisar)', () => {
        expect(validar({ type: 'turno', mensajes: [] })).toBeNull();
    });
});

describe('eventosSse: el cuerpo de fetch', () => {
    const bytes = new TextEncoder().encode(STREAM);

    it('reparte bien un carácter UTF-8 partido entre trozos', async () => {
        // corte en CADA byte: cae dentro de «ñ», «í», «»», etc.
        for (let i = 0; i <= bytes.length; i += 1) {
            const { stream } = cuerpo([bytes.slice(0, i), bytes.slice(i)]);
            expect(await todos(stream), `corte en el byte ${i}`).toEqual(ESPERADOS);
        }
    });

    it('byte a byte', async () => {
        const { stream } = cuerpo([...bytes].map((b) => Uint8Array.of(b)));
        expect(await todos(stream)).toEqual(ESPERADOS);
    });

    it('avisa los descartes y sigue', async () => {
        const descartes: string[] = [];
        const { stream } = cuerpo([new TextEncoder().encode('data: roto\n\n' + frame({ type: 'done' }))]);
        expect(await todos(stream, (d) => descartes.push(d))).toEqual([{ type: 'done' }]);
        expect(descartes).toHaveLength(1);
    });

    it('si quien consume corta antes, cancela el stream', async () => {
        // el primer trozo trae el primer evento entero; quedan trozos sin leer
        const { stream, cancelado } = cuerpo([bytes.slice(0, 60), bytes.slice(60, 120), bytes.slice(120)]);
        for await (const ev of eventosSse(stream)) {
            expect(ev.type).toBe('progreso');
            break;
        }
        expect(cancelado()).toBe(true);
    });
});
