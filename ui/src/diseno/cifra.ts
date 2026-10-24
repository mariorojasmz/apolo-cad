/* Cómo se escribe una cifra en la UI (plan V8.5 F3b-0): coma decimal, espacio de miles, signo
   menos tipográfico y la unidad separada por un espacio («1 799 rpm», «3,81 A», «64 %»). Sin
   valor, «—». Puro: la usan el deslizador, los ítems de atención y las lecturas de la máquina
   viva (`vivo/unidades.ts`). */

export function cifra(valor: number | undefined | null, decimales = 0, unidad = ""): string {
  if (valor === undefined || valor === null || !Number.isFinite(valor)) return "—";
  const [ent, dec] = Math.abs(valor).toFixed(decimales).split(".");
  const miles = ent.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const signo = valor < 0 && Number(Math.abs(valor).toFixed(decimales)) !== 0 ? "−" : "";
  const num = `${signo}${miles}${dec ? `,${dec}` : ""}`;
  if (!unidad) return num;
  return unidad === "°" ? `${num}°` : `${num} ${unidad}`; // los grados van pegados
}
