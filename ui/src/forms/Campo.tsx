import type { ReactNode } from "react";
import type { JsonSchema } from "../types";
import Ayuda from "../ui/Ayuda";
import Pista from "../ui/Pista";
import { textoTecnico } from "../ui/textoTecnico";

/* El envoltorio de UN campo del formulario de un comando (SchemaForm): rótulo, unidad y ⓘ
   en una fila, el control debajo y la pista al pie. Lee los metadatos que arma la vista
   persona del servidor (`GET /api/schemas?vista=persona`):
   - `x-unidad`: la unidad con la que empieza la descripción («mm», «grados»), junto al rótulo.
   - `description`: va COMPLETA a la ⓘ (es la documentación del parámetro), y sólo si dice
     algo más que la unidad.
   - `x-pista`: la pista bajo el control; la llevan sólo los campos que anulan a otro o
     dependen de otro. */

interface Props {
  rotulo: string;
  /** Metadatos del campo (description, x-unidad, x-pista), ya desenvuelto de `anyOf`. */
  campo: JsonSchema;
  /** Pisa la unidad del schema: «JSON» para un valor sin control propio. */
  unidad?: string;
  /** Control que va en la fila del rótulo: la casilla de un sí/no o la que activa un opcional. */
  enCabeza?: ReactNode;
  className?: string;
  children?: ReactNode;
}

export default function Campo({ rotulo, campo, unidad, enCabeza, className, children }: Props) {
  const u = unidad ?? campo["x-unidad"];
  const descripcion = campo.description?.trim() ?? "";
  const ayuda = descripcion !== campo["x-unidad"] ? descripcion : "";
  const pista = campo["x-pista"];
  return (
    <div className={className ? `field ${className}` : "field"}>
      <div className="campo-cabeza">
        <label>{rotulo}</label>
        {u && <span className="unit">{u}</span>}
        {enCabeza}
        {ayuda && <Ayuda tema={rotulo}>{textoTecnico(ayuda)}</Ayuda>}
      </div>
      {children}
      {pista && <Pista>{pista}</Pista>}
    </div>
  );
}
