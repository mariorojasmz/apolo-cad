import ReactDOM from "react-dom/client";
import "../../styles.css";
import Muestrario from "./Muestrario";

/* Entrada del muestrario de diseño (`ui/muestrario.html`, sólo con `npm run dev`). Sin
   StrictMode: el visor de ejemplo monta un canvas de three.js una sola vez, como el real. */

ReactDOM.createRoot(document.getElementById("root")!).render(<Muestrario />);
