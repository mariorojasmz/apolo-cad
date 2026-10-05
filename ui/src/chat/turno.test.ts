import { describe, expect, it } from 'vitest';
import type { ChatMsg } from '../types';
import type { EventoChat } from './sse';
import { CORTADO, aplicarEvento, cerrarTurno } from './turno';

const VACIO: ChatMsg = { role: 'assistant', content: '' };

/** Aplica una secuencia como el store: `seguido` = el anterior también fue `progreso`. */
function turno(eventos: EventoChat[], msg: ChatMsg = VACIO): ChatMsg {
    let anterior: string | undefined;
    for (const ev of eventos) {
        msg = aplicarEvento(msg, ev, anterior === 'progreso');
        anterior = ev.type;
    }
    return msg;
}

const progreso = (text: string): EventoChat => ({ type: 'progreso', text });

describe('el mensaje del asistente evento a evento', () => {
    it('el texto se acumula y borra la nota de avance', () => {
        const m = turno([progreso('Leo el modelo.'), { type: 'text', text: 'Hola' }, { type: 'text', text: ' mundo' }]);
        expect(m.content).toBe('Hola mundo');
        expect(m.progreso).toBeUndefined();
    });

    it('una nota nueva (tras una tool) reemplaza a la anterior', () => {
        const m = turno([progreso('Leo el modelo.'), { type: 'tool', name: 'get_scene' }, progreso('Reviso las uniones.')]);
        expect(m.progreso).toBe('Reviso las uniones.');
    });

    it('los `progreso` seguidos son trozos de la MISMA nota', () => {
        expect(turno([progreso('Reviso '), progreso('las uniones.')]).progreso).toBe('Reviso las uniones.');
    });

    it('la tool no borra la nota: sigue a la vista mientras corre', () => {
        expect(turno([progreso('Mido la holgura.'), { type: 'tool', name: 'measure' }]).progreso).toBe('Mido la holgura.');
    });

    it('error y done borran la nota; done guarda el uso', () => {
        expect(turno([progreso('a'), { type: 'error', message: 'falló' }])).toMatchObject({ error: 'falló', progreso: undefined });
        const uso = { input: 1, output: 2, cache_read: 3, cache_creation: 4 };
        const m = turno([progreso('a'), { type: 'done', uso }]);
        expect(m.progreso).toBeUndefined();
        expect(m.uso).toEqual(uso);
        expect(turno([{ type: 'done' }])).not.toHaveProperty('uso');
    });

    it('el chip guarda la etiqueta si vino y el nombre siempre', () => {
        const m = turno([
            { type: 'tool', name: 'check_interference', etiqueta: 'Revisando interferencias' },
            { type: 'tool', name: 'undo_last' },
        ]);
        expect(m.tools).toEqual([{ name: 'check_interference', etiqueta: 'Revisando interferencias' }, { name: 'undo_last' }]);
    });

    it('lotes: el autónomo acumula y queda aceptado; la propuesta queda pendiente', () => {
        const a = { type: 'create_box', params: {}, reason: 'r' };
        const auto = turno([
            { type: 'actions', actions: [a], executed: true },
            { type: 'actions', actions: [a, a], executed: true },
        ]);
        expect(auto.actions).toHaveLength(3);
        expect(auto.actionsStatus).toBe('accepted');
        const propuesta = turno([{ type: 'actions', actions: [a], executed: false }]);
        expect(propuesta).toMatchObject({ actions: [a], actionsStatus: 'pending' });
    });

    it('el aviso va aparte del error y no se pierde si llegan dos', () => {
        const m = turno([
            { type: 'text', text: 'Hice la mitad' },
            { type: 'aviso', motivo: 'vueltas', mensaje: 'Llegué al tope de pasos.' },
            { type: 'aviso', motivo: 'otro', mensaje: 'Otra cosa.' },
            { type: 'done' },
        ]);
        expect(m.aviso).toBe('Llegué al tope de pasos.\nOtra cosa.');
        expect(m.error).toBeUndefined();
        expect(m.content).toBe('Hice la mitad');
    });

    it('no toca el mensaje que recibe', () => {
        const antes: ChatMsg = { role: 'assistant', content: 'x', tools: [{ name: 'a' }] };
        const copia = structuredClone(antes);
        turno([{ type: 'text', text: 'y' }, { type: 'tool', name: 'b' }, progreso('p')], antes);
        expect(antes).toEqual(copia);
    });
});

describe('el cierre del stream', () => {
    it('con done: sin nota y sin error', () => {
        expect(cerrarTurno({ ...VACIO, progreso: 'p' }, true)).toEqual({ ...VACIO, progreso: undefined });
    });

    it('sin done ni error: la conexión se cortó y se dice', () => {
        expect(cerrarTurno({ ...VACIO, progreso: 'p' }, false)).toMatchObject({ error: CORTADO, progreso: undefined });
    });

    it('sin done pero con un error: el error se conserva', () => {
        expect(cerrarTurno({ ...VACIO, error: 'falló' }, false).error).toBe('falló');
    });
});
