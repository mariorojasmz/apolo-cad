/* Fechas de la pantalla de proyectos, legibles de un vistazo: «hoy 09:18», «ayer 22:39»,
   «2 ago», «15 jun 2025». El servidor manda la hora LOCAL sin zona («2026-10-06T09:18:15»),
   que `new Date()` lee como local. Funciones puras: `ahora` entra por parámetro para los tests.
   Los meses van a mano y no con `Intl`: según la versión de ICU, «ago» sale con o sin punto. */

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

const DIA_MS = 24 * 60 * 60 * 1000;

function inicioDelDia(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Días de calendario entre `fecha` y `ahora` (0 = hoy, 1 = ayer). Negativo si es futura. */
export function diasAtras(fecha: Date, ahora: Date): number {
  return Math.round((inicioDelDia(ahora) - inicioDelDia(fecha)) / DIA_MS);
}

function hora(d: Date): string {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** «hoy 09:18», «ayer 22:39», «2 ago» (este año) o «15 jun 2025». Texto crudo si no se lee. */
export function fechaCorta(iso: string, ahora: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const dias = diasAtras(d, ahora);
  if (dias === 0) return `hoy ${hora(d)}`;
  if (dias === 1) return `ayer ${hora(d)}`;
  const diaMes = `${d.getDate()} ${MESES[d.getMonth()]}`;
  return d.getFullYear() === ahora.getFullYear() ? diaMes : `${diaMes} ${d.getFullYear()}`;
}

/** Fecha completa para leer con calma: «6 oct 2026, 09:18». */
export function fechaLarga(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.getDate()} ${MESES[d.getMonth()]} ${d.getFullYear()}, ${hora(d)}`;
}

export type GrupoFecha = "Hoy" | "Últimos 7 días" | "Últimos 30 días" | "Anteriores";

export const ORDEN_GRUPOS: GrupoFecha[] = ["Hoy", "Últimos 7 días", "Últimos 30 días", "Anteriores"];

/** En qué tramo cae una fecha (para agrupar la lista por recientes). */
export function grupoFecha(iso: string, ahora: Date = new Date()): GrupoFecha {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Anteriores";
  const dias = diasAtras(d, ahora);
  if (dias <= 0) return "Hoy";
  if (dias < 7) return "Últimos 7 días";
  if (dias < 30) return "Últimos 30 días";
  return "Anteriores";
}
