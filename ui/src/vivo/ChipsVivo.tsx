import { Component, type ComponentType, type ReactNode } from "react";
import type { Extension } from "../extensiones/tipos";
import { chipsDe } from "../extensiones/puntosVivo";

/* Los chips de las extensiones en la barra de la sesión viva (plan plc-en-el-lazo, D13 a), tras la
   fase y el factor. Sin chips no pinta NADA: la barra queda idéntica a la de un núcleo sin
   extensiones. Cada chip va en su contenedor con la letra de la barra y su propio límite de
   errores: uno que revienta desaparece y la barra sigue. */

class Limite extends Component<{ id: string; children: ReactNode }, { roto: boolean }> {
  state = { roto: false };
  static getDerivedStateFromError() {
    return { roto: true };
  }
  componentDidCatch(e: unknown) {
    console.error(`El chip «${this.props.id}» de la barra viva falló y se quitó:`, e);
  }
  render() {
    return this.state.roto ? null : this.props.children;
  }
}

export default function ChipsVivo({ extensiones }: { extensiones: readonly Extension[] }) {
  const chips = chipsDe(extensiones);
  if (!chips.length) return null;
  return (
    <>
      {chips.map(({ id, Componente }: { id: string; Componente: ComponentType }) => (
        <span key={id} className="bv-chip" data-chip={id}>
          <Limite id={id}><Componente /></Limite>
        </span>
      ))}
    </>
  );
}
