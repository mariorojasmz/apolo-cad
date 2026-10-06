import { describe, expect, it } from 'vitest';
import type { DocumentOut, FeatureOut, Mesh, SceneOut } from '../types';
import { cambiosDelDelta, mergeSceneDelta } from './sceneDelta';

const DOC: DocumentOut = {
    name: 'prueba', commands: [], can_undo: false, can_redo: false, variables: [],
    configurations: [], groups: [], project_id: 1,
};
const MALLA: Mesh = { positions: [0, 0, 0, 1, 0, 0, 0, 1, 0], indices: [0, 1, 2] };

/** Pieza completa (como llega en una escena entera o en un delta con geometría nueva). */
function pieza(id: string, extra: Partial<FeatureOut> = {}): FeatureOut {
    return {
        id, name: `Pieza ${id}`, visible: true, color: '#888888', volume_mm3: 1000,
        bbox: { min: [0, 0, 0], max: [10, 10, 10] }, mesh: MALLA, mesh_key: null, matrix: null,
        command_id: `cmd_${id}`, command_type: 'create_box', component: null, cut_length: null,
        group: null, is_guide: false, rev: 1, ...extra,
    };
}

/** Entrada `same` del delta: sin geometría, sólo id + rev + metadatos volátiles. */
function igual(id: string, extra: Partial<FeatureOut> = {}): FeatureOut {
    return {
        id, name: `Pieza ${id}`, visible: true, color: '#888888', volume_mm3: 0,
        bbox: { min: [], max: [] }, mesh: null, mesh_key: null, matrix: null,
        command_id: '', command_type: null, component: null, cut_length: null,
        group: null, is_guide: false, rev: 1, same: true, ...extra,
    };
}

const escena = (features: FeatureOut[], definitions: Record<string, Mesh> = {}, epoch = 'e1'): SceneOut =>
    ({ features, definitions, document: DOC, epoch });

describe('mergeSceneDelta', () => {
    it('una pieza `same` hereda la geometría anterior y recibe los metadatos volátiles', () => {
        const prev = escena([pieza('a', { volume_mm3: 1234, rev: 3 })]);
        const delta = escena([igual('a', {
            rev: 3, name: 'Larguero', color: '#ff0000', visible: false, group: 'Bastidor', is_guide: true,
        })]);
        const [a] = mergeSceneDelta(prev, delta).features;
        expect(a.mesh).toBe(MALLA);
        expect(a.volume_mm3).toBe(1234);
        expect(a.bbox).toEqual({ min: [0, 0, 0], max: [10, 10, 10] });
        expect(a.command_id).toBe('cmd_a');
        expect(a).toMatchObject({ name: 'Larguero', color: '#ff0000', visible: false, group: 'Bastidor', is_guide: true });
    });

    it('una pieza sin `same` llega completa, tal cual la manda el servidor', () => {
        const nueva = pieza('a', { rev: 2, volume_mm3: 5000 });
        const out = mergeSceneDelta(escena([pieza('a')]), escena([nueva]));
        expect(out.features).toEqual([nueva]);
    });

    it('una `same` sin pieza previa se descarta (no hay malla que heredar)', () => {
        const out = mergeSceneDelta(escena([]), escena([igual('fantasma')]));
        expect(out.features).toEqual([]);
    });

    it('las definiciones se podan a las que alguna pieza referencia', () => {
        const otra: Mesh = { positions: [], indices: [] };
        const prev = escena([pieza('a', { mesh: null, mesh_key: 'perno', matrix: [] })], { perno: MALLA, viejo: MALLA });
        const delta = escena([igual('a'), pieza('b', { mesh: null, mesh_key: 'tuerca', matrix: [] })], { tuerca: otra, suelto: otra });
        const out = mergeSceneDelta(prev, delta);
        expect(Object.keys(out.definitions).sort()).toEqual(['perno', 'tuerca']);
        expect(out.definitions.perno).toBe(MALLA);
        expect(out.definitions.tuerca).toBe(otra);
    });

    it('el documento y el epoch salen del delta', () => {
        const doc2: DocumentOut = { ...DOC, name: 'otro' };
        const out = mergeSceneDelta(escena([], {}, 'e1'), { features: [], definitions: {}, document: doc2, epoch: 'e2' });
        expect(out.document).toBe(doc2);
        expect(out.epoch).toBe('e2');
    });
});

describe('cambiosDelDelta', () => {
    it('separa nuevas, cambiadas y eliminadas', () => {
        const prev = escena([pieza('a'), pieza('b'), pieza('c'), pieza('d')]);
        const delta = escena([igual('a'), pieza('b', { rev: 2 }), pieza('n1'), pieza('d', { rev: 5 }), pieza('n2')]);
        expect(cambiosDelDelta(prev, delta)).toEqual({ nuevos: ['n1', 'n2'], cambiados: ['b', 'd'], eliminados: ['c'] });
    });

    it('respeta el orden del delta (nuevas y cambiadas) y el de la escena previa (eliminadas)', () => {
        const prev = escena([pieza('z'), pieza('y'), pieza('x'), pieza('w')]);
        const delta = escena([pieza('n2'), pieza('x', { rev: 2 }), pieza('n1'), pieza('z', { rev: 2 })]);
        expect(cambiosDelDelta(prev, delta)).toEqual({ nuevos: ['n2', 'n1'], cambiados: ['x', 'z'], eliminados: ['y', 'w'] });
    });

    it('una `same` con otro color, nombre o visibilidad NO cuenta: se marca geometría, no apariencia', () => {
        const prev = escena([pieza('a'), pieza('b')]);
        const delta = escena([igual('a', { color: '#00ff00' }), igual('b', { name: 'Otro nombre', visible: false })]);
        expect(cambiosDelDelta(prev, delta)).toEqual({ nuevos: [], cambiados: [], eliminados: [] });
    });

    it('una `same` sin pieza previa no es nueva: mergeSceneDelta la descarta', () => {
        expect(cambiosDelDelta(escena([]), escena([igual('fantasma')]))).toEqual({ nuevos: [], cambiados: [], eliminados: [] });
    });

    it('un delta vacío elimina todo lo previo; sobre una escena vacía, no cambia nada', () => {
        expect(cambiosDelDelta(escena([pieza('a'), pieza('b')]), escena([])))
            .toEqual({ nuevos: [], cambiados: [], eliminados: ['a', 'b'] });
        expect(cambiosDelDelta(escena([]), escena([]))).toEqual({ nuevos: [], cambiados: [], eliminados: [] });
    });
});
