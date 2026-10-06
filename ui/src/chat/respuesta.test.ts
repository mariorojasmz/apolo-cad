import { describe, expect, it } from 'vitest';
import { cuerpoDelChat } from './respuesta';

const LLENO = 'El asistente ya atiende varias conversaciones a la vez: espera a que termine una y vuelve a intentarlo.';

const conJson = (status: number, cuerpo: unknown) =>
    new Response(JSON.stringify(cuerpo), { status, headers: { 'Content-Type': 'application/json' } });

describe('la respuesta HTTP del chat', () => {
    it('cupo lleno (429): el motivo de la API, no el código', async () => {
        await expect(cuerpoDelChat(conJson(429, { detail: LLENO }))).rejects.toThrow(LLENO);
    });

    it('configuración inválida (500): el texto de la API', async () => {
        const texto = 'APOLO_EFFORT debe ser uno de low, medium, high, xhigh, max (vale «mucho»).';
        await expect(cuerpoDelChat(conJson(500, { detail: texto }))).rejects.toThrow(texto);
    });

    it('sin un texto legible, el código de siempre', async () => {
        const casos: [Response, number][] = [
            [conJson(422, { detail: [{ loc: ['body', 'messages'], msg: 'field required' }] }), 422],
            [conJson(503, { detail: '   ' }), 503],
            [conJson(500, { error: 'otro formato' }), 500],
            [new Response('<html>Bad Gateway</html>', { status: 502 }), 502],
            [new Response(null, { status: 504 }), 504],
        ];
        for (const [res, status] of casos) {
            await expect(cuerpoDelChat(res), `status ${status}`).rejects.toThrow(`Error ${status} del servidor`);
        }
    });

    it('respuesta buena: devuelve el cuerpo del stream; sin cuerpo, falla con el código', async () => {
        const res = new Response('data: {"type":"done"}\n\n', { status: 200 });
        const cuerpo = await cuerpoDelChat(res);
        expect(await new Response(cuerpo).text()).toBe('data: {"type":"done"}\n\n');
        await expect(cuerpoDelChat(new Response(null, { status: 200 }))).rejects.toThrow('Error 200 del servidor');
    });
});
