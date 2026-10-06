import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { installErrorCapture } from "./errorlog";
import "./styles.css";
import "./visor/visor.css"; // después de styles.css: sus reglas pisan las del modo Completo

installErrorCapture();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
