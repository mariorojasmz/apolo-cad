import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { installErrorCapture } from "./errorlog";
import { escucharCambiosExternos } from "./visor/cambiosExternos";
import "./styles.css";
import "./visor/visor.css"; // después de styles.css: sus reglas pisan las del modo Completo

installErrorCapture();
escucharCambiosExternos(); // lo que cambió el agente se marca en el 3D, el aviso y el árbol

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
