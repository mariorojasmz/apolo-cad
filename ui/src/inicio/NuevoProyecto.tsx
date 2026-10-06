import { useState } from "react";

/* Formulario para crear un proyecto, desplegado sobre la lista al tocar «Nuevo proyecto».
   Crear es menos frecuente que encontrar uno, por eso no ocupa la cabecera todo el tiempo. */

const PLANTILLAS = [
  { id: "", label: "Vacío" },
  { id: "transportador", label: "Transportador 2 m (paramétrico)" },
  { id: "brazo", label: "Brazo robótico 4 ejes" },
] as const;

interface Props {
  ocupado: boolean;
  onCrear: (nombre: string, plantilla: string | null) => void;
  onCancelar: () => void;
}

export default function NuevoProyecto({ ocupado, onCrear, onCancelar }: Props) {
  const [nombre, setNombre] = useState("");
  const [plantilla, setPlantilla] = useState("");
  const crear = () => onCrear(nombre.trim() || "Sin título", plantilla || null);

  return (
    <form
      className="nuevo-proy"
      onSubmit={(e) => {
        e.preventDefault();
        crear();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onCancelar();
        }
      }}
    >
      <label className="nuevo-campo">
        <span>Nombre</span>
        <input autoFocus placeholder="p. ej. mesa-de-corte-2m" value={nombre} onChange={(e) => setNombre(e.target.value)} />
      </label>
      <label className="nuevo-campo">
        <span>Empezar desde</span>
        <select value={plantilla} onChange={(e) => setPlantilla(e.target.value)}>
          {PLANTILLAS.map((t) => (
            <option key={t.id} value={t.id}>{t.label}</option>
          ))}
        </select>
      </label>
      <span className="nuevo-acc">
        <button type="submit" className="primary" disabled={ocupado}>Crear proyecto</button>
        <button type="button" className="ghost" onClick={onCancelar}>Cancelar</button>
      </span>
    </form>
  );
}
