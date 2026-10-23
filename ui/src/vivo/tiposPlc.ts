import { useMemo } from "react";
import { useStore } from "../state/store";
import { useVivo } from "./estado";
import { indiceSenales, programasDelDocumento, tiposDeSenales } from "./programa";

/* El tipo ST (BOOL, INT, REAL…) de cada señal que es una variable de un programa del PLC: con
   él, el multímetro, el árbol y el osciloscopio leen `-K1.Main.en_marcha` como sí/no y
   `-K1.Main.cuenta` como entero. Sale del log de comandos y de los nombres de la sesión. */

export function useTiposPlc(): Map<string, string> {
  const commands = useStore((s) => s.scene?.document.commands);
  const inicio = useVivo((s) => s.inicio);
  const n = useVivo((s) => Object.keys(s.lecturas).length); // primitivo: llegan señales nuevas
  return useMemo(() => {
    if (!commands || !inicio) return new Map<string, string>();
    const nombres = new Set([...inicio.senales, ...Object.keys(useVivo.getState().lecturas)]);
    return tiposDeSenales(programasDelDocumento(commands), indiceSenales(nombres));
  }, [commands, inicio, n]); // `n`: recalcula cuando llegan señales nuevas
}
