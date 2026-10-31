"""Mixin de METADATOS de manifest del documento: variantes, color, material, vertical,
movimiento, cadenas de cotas, FEA, requisitos, visibilidad y boceto-guía.

Sale de `document.py` (plan partir-nucleo-congelado, F5): `Document` hereda los métodos tal cual.
Viven fuera del log y de los checkpoints (por qué: CLAUDE.md raíz, «Metadato ≠ comando»); sólo
`apply_configuration` muta el log, por `Document._mutate`.
"""

from __future__ import annotations

from apolo.doc import variantes
from apolo.doc.errors import DocumentError
from apolo.doc.por_comando import de_la_pieza, piezas_del_comando


def _destino(scene: dict, feature_id: str) -> tuple[bool, list[str]]:
    """(¿por pieza?, piezas que toca) de un set de apariencia: un id de pieza es POR PIEZA; la
    raíz de un patrón (el comando de unas piezas que no es pieza), POR COMANDO (D9 de
    puerta-fuera-de-catalogo, `doc/por_comando.py`)."""
    if feature_id in scene:
        return True, [feature_id]
    piezas = piezas_del_comando(scene, feature_id)
    if not piezas:
        raise DocumentError(f"No existe el sólido '{feature_id}'")
    return False, piezas


class MetadatosDocumento:
    # ------------------------------------------------------- configuraciones
    # Variantes = tabla de diseño: cada una guarda sólo sus COLUMNAS. Lógica en `variantes.py`;
    # aquí se delega y se traduce `VarianteError` → `DocumentError`. No tocan el log ni la
    # geometría, salvo `apply_configuration`.
    def _tabla(self, fn, *args) -> dict:
        try:
            return fn(*args)
        except variantes.VarianteError as exc:
            raise DocumentError(str(exc)) from None

    def save_configuration(self, name: str, variables: list[str] | None = None) -> None:
        """Variante con el valor ACTUAL de las columnas ∪ `variables` (columnas nuevas)."""
        self.configurations = self._tabla(
            variantes.guardar, self.configurations, name, self.variables_raw, variables)

    def set_configuration(self, name: str, values: dict[str, str]) -> None:
        """Edita {variable: expresión} SIN aplicar; un nombre nuevo parte de las columnas."""
        self.configurations = self._tabla(
            variantes.editar, self.configurations, name, values, self.variables_raw)

    def delete_configuration_column(self, variable: str) -> None:
        """Quita la columna de TODAS las variantes; la variable sigue en el proyecto."""
        self.configurations = self._tabla(variantes.quitar_columna, self.configurations, variable)

    def apply_configuration(self, name: str) -> dict:
        """Reescribe los set_variable de SUS columnas y regenera (un solo undo). Devuelve
        {"cambios": [{variable, antes, despues}], "aviso": str | None}, medido ANTES."""
        config = self.configurations.get(name)
        if config is None:
            raise DocumentError(f"No existe la variante '{name}'")
        resultado = variantes.al_aplicar(config, self.variables_raw)

        def apply():
            for cmd in self.commands:
                var = cmd["params"].get("name") if cmd["type"] == "set_variable" else None
                if var in config:
                    cmd["params"] = {"name": var, "expression": str(config[var])}

        self._mutate(apply, intencion=f"Aplicar variante «{name}»")  # D1: se entiende mejor
        return resultado

    def delete_configuration(self, name: str) -> None:
        if name not in self.configurations:
            raise DocumentError(f"No existe la variante '{name}'")
        del self.configurations[name]

    def set_color(self, feature_id: str, color: str | None) -> None:
        """Por pieza; con la raíz de un patrón, por comando (lo heredan sus copias: D9)."""
        por_pieza, _ = _destino(self.scene, feature_id)
        destino = self.colors if por_pieza else self.colores_por_comando
        if color:
            destino[feature_id] = color
        else:
            destino.pop(feature_id, None)

    def set_material(self, feature_id: str, material: str | None) -> None:
        """Por pieza; con la raíz de un patrón, por comando (lo heredan sus copias, también las
        que nacen al subir la variable; una copia con material propio lo conserva: D9)."""
        por_pieza, piezas = _destino(self.scene, feature_id)
        destino = self.materials if por_pieza else self.materiales_por_comando
        if material:
            destino[feature_id] = material
        else:
            destino.pop(feature_id, None)
        for fid in piezas:  # la copia con material propio lo conserva
            feat = self.scene[fid]
            feat.material = de_la_pieza(fid, feat.command_id, self.materials,
                                        self.materiales_por_comando)

    def set_vertical(self, vertical: str) -> None:
        if vertical not in ("metalmecanica", "carpinteria"):
            raise DocumentError("vertical debe ser 'metalmecanica' o 'carpinteria'")
        self.vertical = vertical

    def default_material(self) -> str:
        """Material por defecto de piezas a-medida no reconocidas (según vertical)."""
        return "madera" if self.vertical == "carpinteria" else "acero"

    def set_motion(self, name: str, keyframes: list[dict]) -> None:
        """Define los fotogramas clave de un estudio de movimiento CON NOMBRE (metadato, no
        geometría). Lista vacía → borra el estudio. Pueden coexistir varios estudios.
        Formato de fotograma: {"t": segundos, "values": {junta: valor}} — los valores de
        junta van ANIDADOS en "values"; claves sueltas al nivel superior se RECHAZAN
        (aceptarlas en silencio producía estudios que "reproducían" sin mover nada).
        Opcional `"posicion": "uso" | "guardado"` etiqueta la pose de uso y la de guardado de un
        producto plegable, una vez cada una por estudio (plan plegables-en-la-puerta, D2): un
        manifest viejo no la trae y abre igual. Sólo el fotograma de `uso` acepta `"trabas"`
        (D5: lo que lo traba en cada sentido de cada grado que pliega; formato y validación en
        `library/calidad/trabas.py`)."""
        from apolo.library.calidad.trabas import validar_trabas
        from apolo.library.requisitos import POSICIONES_PLEGADO as POSICIONES

        name = str(name).strip()
        if not name:
            raise DocumentError("El estudio de movimiento necesita un nombre")
        clean: list[dict] = []
        etiquetadas: set[str] = set()
        for kf in keyframes:
            if not isinstance(kf, dict):
                raise DocumentError(
                    'Cada fotograma debe ser un dict {"t": segundos, "values": {junta: valor}}'
                )
            extras = sorted(set(map(str, kf)) - {"t", "values", "posicion", "trabas"})
            if extras:
                raise DocumentError(
                    f"Claves desconocidas en el fotograma: {', '.join(extras)} — los valores "
                    'de junta van ANIDADOS: {"t": segundos, "values": {junta: valor}} (y, '
                    'opcional, "posicion": "uso" | "guardado"; el de uso, sus "trabas")'
                )
            posicion = kf.get("posicion")
            if posicion is not None:
                posicion = str(posicion).strip().lower()
                if posicion not in POSICIONES:
                    raise DocumentError(
                        f"'posicion' del fotograma es {' | '.join(POSICIONES)} (la pose de uso y "
                        f"la de guardado de un producto plegable), no «{kf.get('posicion')}»")
                if posicion in etiquetadas:
                    raise DocumentError(
                        f"La posición «{posicion}» va en UN solo fotograma del estudio")
                etiquetadas.add(posicion)
            trabas = None
            if "trabas" in kf:
                if posicion != "uso":
                    raise DocumentError(
                        '"trabas" va sólo en el fotograma "posicion": "uso" (lo que traba la '
                        "posición de uso de un producto plegable)")
                try:
                    trabas = validar_trabas(kf["trabas"], self.joints, self.scene)
                except ValueError as exc:
                    raise DocumentError(str(exc)) from exc
            try:
                t = float(kf["t"])
            except (KeyError, TypeError, ValueError) as exc:
                raise DocumentError("Cada fotograma necesita un tiempo 't' numérico") from exc
            if t < 0:
                raise DocumentError("El tiempo del fotograma no puede ser negativo")
            values = kf.get("values") or {}
            if not isinstance(values, dict):
                raise DocumentError("Los valores del fotograma deben ser {junta: valor}")
            desconocidas = sorted(set(map(str, values)) - set(self.joints))
            if desconocidas:
                validas = ", ".join(sorted(self.joints)) or "ninguna declarada"
                raise DocumentError(
                    f"Juntas desconocidas en el fotograma: {', '.join(desconocidas)} "
                    f"(válidas: {validas})"
                )
            try:
                vals = {str(n): float(v) for n, v in values.items()}
            except (TypeError, ValueError) as exc:
                raise DocumentError("Cada valor de junta debe ser numérico") from exc
            clean.append({"t": t, "values": vals, **({"posicion": posicion} if posicion else {}),
                          **({"trabas": trabas} if trabas is not None else {})})
        if clean and not any(k["values"] for k in clean):
            raise DocumentError(
                "El estudio no mueve ninguna junta: todos los fotogramas tienen 'values' vacío"
            )
        if clean:
            self.motion[name] = sorted(clean, key=lambda k: k["t"])
        else:
            self.motion.pop(name, None)

    def delete_motion(self, name: str) -> None:
        """Elimina un estudio de movimiento por nombre (no falla si no existe)."""
        self.motion.pop(str(name).strip(), None)

    def set_stackup(self, name: str, eslabones: list[dict], requisito: dict | None = None) -> None:
        """Declara una CADENA DE COTAS con nombre (metadato de manifest, como motion: NO
        entra al log ni a los checkpoints). Cada eslabón: {nombre, nominal_mm (número o
        '=expr'), sentido:±1, tol}; o {id, eje} para medir el bbox vivo de una pieza. La
        evaluación (resolver nominales/ids + peor caso/RSS) la hace la capa API. Lista de
        eslabones vacía → borra la cadena."""
        name = str(name).strip()
        if not name:
            raise DocumentError("La cadena de cotas necesita un nombre")
        if not eslabones:
            self.stackups.pop(name, None)
            return
        clean: list[dict] = []
        for e in eslabones:
            if not isinstance(e, dict):
                raise DocumentError("Cada eslabón debe ser un objeto")
            if e.get("id"):  # eslabón medido del bbox vivo de una pieza
                clean.append({
                    "id": str(e["id"]), "eje": str(e.get("eje", "x")),
                    "sentido": 1 if int(e.get("sentido", 1)) >= 0 else -1,
                    "tol": e.get("tol"), "nombre": e.get("nombre"),
                })
            elif "nominal_mm" in e:
                clean.append({
                    "nombre": str(e.get("nombre", "eslabón")),
                    "nominal_mm": e["nominal_mm"],  # número o "=expr" (lo resuelve la API)
                    "sentido": 1 if int(e.get("sentido", 1)) >= 0 else -1,
                    "tol": e.get("tol") or {"pm": 0.0},
                })
            else:
                raise DocumentError("Cada eslabón necesita 'nominal_mm' o 'id' (pieza)")
        self.stackups[name] = {"eslabones": clean, "requisito": requisito or {}}

    def delete_stackup(self, name: str) -> None:
        """Elimina una cadena de cotas por nombre (no falla si no existe)."""
        self.stackups.pop(str(name).strip(), None)

    def set_fea_result(self, feature_id: str, summary: dict | None) -> None:
        """Guarda (o borra con None) el resumen del último FEA de una pieza.
        Metadato de manifest (como motion/requirements): NO entra al log ni a los
        checkpoints; la memoria de cálculo lo consume con chequeo de vigencia."""
        fid = str(feature_id).strip()
        if not fid:
            raise DocumentError("El resultado FEA necesita el id de la pieza")
        if summary is None:
            self.fea.pop(fid, None)
        else:
            self.fea[fid] = dict(summary)

    def set_requirements(self, fields: dict) -> None:
        """Define las BASES DE DISEÑO del proyecto (metadato, como motion): contra qué se
        valida la máquina. Reemplaza el dict completo; `{}` las borra. Validación y ficha del
        encargo (con su marca `asumido`): `library/requisitos.py`."""
        from apolo.library.requisitos import normalizar_requisitos

        try:
            self.requirements = normalizar_requisitos(fields)
        except ValueError as exc:
            raise DocumentError(str(exc)) from exc

    def set_visibility(self, feature_id: str, visible: bool) -> None:
        if feature_id not in self.scene:
            raise DocumentError(f"No existe el sólido '{feature_id}'")
        if visible:
            self.hidden.discard(feature_id)
        else:
            self.hidden.add(feature_id)
        self.scene[feature_id].visible = visible

    def set_sketch_guide(self, feature_id: str, guide: bool) -> None:
        """Marca/desmarca el sólido (y TODAS las piezas de su comando) como boceto-guía
        (blockout): geometría de INTENCIÓN excluida de BOM/masa/interferencia/FEA. Metadato
        de manifest (como colors/materials): no entra al log ni a los checkpoints."""
        feat = self.scene.get(feature_id)
        if feat is None:
            raise DocumentError(f"No existe el sólido '{feature_id}'")
        cmd_id = feat.command_id
        if guide:
            self.sketch_guides.add(cmd_id)
        else:
            self.sketch_guides.discard(cmd_id)
        for f in self.scene.values():  # un comando puede emitir varias piezas (create_frame)
            if f.command_id == cmd_id:
                f.is_guide = guide
