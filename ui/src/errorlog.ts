/* Reporta errores del cliente al backend para revisarlos tras una sesión de
   pruebas (quedan en logs/errors.log). Con tope por sesión para evitar
   inundaciones si algo entra en bucle. */

let sent = 0;
const MAX_REPORTS = 50;

export function reportError(source: string, message: string, context: Record<string, unknown> = {}): void {
  if (sent >= MAX_REPORTS) return;
  sent += 1;
  try {
    void fetch("/api/client-errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source, message: String(message).slice(0, 2000), context }),
      keepalive: true,
    }).catch(() => {
      /* el propio reporte nunca debe generar más errores */
    });
  } catch {
    /* ídem */
  }
}

export function installErrorCapture(): void {
  window.addEventListener("error", (e) => {
    reportError("window", e.message, {
      file: e.filename,
      line: e.lineno,
      col: e.colno,
      stack: (e.error as Error | undefined)?.stack?.slice(0, 2000),
    });
  });
  window.addEventListener("unhandledrejection", (e) => {
    const reason = e.reason as Error | undefined;
    reportError("promise", reason?.message ?? String(e.reason), {
      stack: reason?.stack?.slice(0, 2000),
    });
  });
}
