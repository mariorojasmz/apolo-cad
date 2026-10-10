---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens y un escaneo real de Mario (un motor) para F0
descripcion: Subes el escaneo 3D de una pieza en cualquier formato y el agente la mide y la reconstruye como pieza limpia de Apolo, con sus medidas de montaje y lista para reusar en cualquier proyecto
---

# Del escaneo 3D a una pieza que Apolo maneja

## Estado y origen

Mario (2026-10-10), pensando en comprar un escáner 3D: «puedo escanear, te importo el archivo
(asegura todos los posibles formatos), y con Claude se conecta por MCP y ve la pieza y lo crea
en un objeto manejable?, eso sería bueno, porque pensaba usarlo para escanear unos motores con
forma rara y tenerlo para Apolo sería muy útil». Es el punto 11 de la visión (repo privado de
negocio).

## El problema / lo que hay hoy

- Apolo sólo importa STEP: `POST /api/import` (`api/routers/projects.py:147`) → comando
  `import_step` (`commands/registry.py:887`, `step_bytes_to_shape`).
- Un escáner entrega casi siempre una MALLA de triángulos (STL, OBJ, PLY, 3MF) o una NUBE de
  puntos (PLY, XYZ, PTS, E57, LAS); el STEP sólo sale con software de ingeniería inversa aparte.
- Una malla no tiene caras planas reales, agujeros con diámetro ni cotas editables: sirve de
  referencia, no de pieza.
- Ya existen las piezas GUÍA (`is_guide`): no cuentan en BOM, masa, interferencias, DOF ni FEA
  (`library/bom.py`, `library/checks.py`, `engineering/mass.py`, `assembly/dof.py`).
- `pyproject` no trae librerías de mallas (sólo numpy y scipy).

## Decisiones (para vetar)

- **D1. Todos los formatos razonables, por familia**:
  - CAD sólido: STEP (hoy), IGES y BREP (OCCT ya los lee).
  - Malla: STL (ASCII y binario), OBJ, PLY, OFF, 3MF, glTF/GLB, con `trimesh` (MIT).
  - Nube de puntos: PLY, XYZ/PTS/TXT, E57 (`pye57`) y LAS/LAZ (`laspy`); se convierte a malla
    (reconstrucción de superficie) antes de seguir.
  - Lo que no se pueda leer → error que nombra los formatos aceptados.
  Las librerías nuevas van como extra opcional (`apolo-cad[escaneo]`), como el marcador de
  `planegcs`: no engordan la instalación de quien no escanea. Licencias verificadas en F0.
- **D2. `import_scan` = pieza GUÍA**: la malla entra decimada (meta ≤ 200 mil triángulos,
  ≤ 20 MB en el `.apolo`) como adjunto, con `is_guide` (no cuenta en BOM ni cálculos). El
  original lo guarda el usuario; Apolo no lo engorda.
- **D3. Unidades y orientación al importar**: se detectan (mm por defecto; el usuario o el
  agente confirma con una cota conocida) y la pieza se alinea a sus ejes principales o al eje
  del cilindro dominante (el eje del motor queda en X, Y o Z).
- **D4. Tools de LECTURA para que el agente «vea» y mida el escaneo** (por el MCP fino, sin
  tool por comando):
  - `scan_fit`: ajusta primitivas por región (planos, cilindros, conos, esferas) con su error;
    devuelve ejes, diámetros, distancias y el agujero de cada perno de una brida.
  - `scan_section`: corte plano de la malla → contorno 2D (para croquis y revolución).
  - `render_view` y `measure` ya sirven sobre la guía.
- **D5. Reconstruir lo que importa, no cada aleta**: una pieza comprada (motor, reductor) se
  rehace con su INTERFAZ exacta (brida, círculo de pernos, Ø y chaveta del eje, centrador) +
  una ENVOLVENTE simplificada (para holguras y guardas) + masa y centro de gravedad. Una pieza a
  fabricar se rehace completa con croquis, extrusión y revolución. El agente compara la pieza
  nueva contra el escaneo (desviación máxima) antes de darla por buena.
- **D6. Queda como componente REUSABLE**: el resultado se guarda en un catálogo del usuario
  (`APOLO_HOME/catalogo_usuario/`, YAML + geometría) con anclas (`eje`, `brida`) como las del
  catálogo oficial, para insertarlo en cualquier proyecto con `insert_component`.

## Alternativas descartadas

- Convertir la malla entera a sólido OCCT y usarla como pieza: pesada, sin cotas, sin anclas;
  rompe interferencias y FEA.
- Comprar o integrar un software de ingeniería inversa: caro y cerrado; la IA + D4 cubre lo que
  una máquina necesita (interfaces y envolvente).

## Fases

- **F0 (S, sólo lectura + scratchpad)**: con un escaneo real de Mario (un motor) y archivos de
  muestra de cada formato: tiempos de lectura, decimado y conversión; error del ajuste de
  cilindros; licencias de cada librería.
- **F1 (M, `commands` + `api` + `library`)**: D1, D2 y D3: `import_scan` y el import ampliado.
- **F2 (M, `kernel`/`library` + `api` + MCP + golden)**: D4.
- **F3 (M, `library` + `commands`)**: D6, catálogo del usuario con anclas.
- **F4 (S, verificación)**: por MCP, del escaneo del motor de Mario a un componente reutilizable
  con su brida y eje exactos; se inserta en la piloto y pasa la puerta de entrega.

## Lo que este plan NO hace

- Escanear el LUGAR (la planta del cliente con LiDAR del celular): va en la visión, punto 9.
- Ingeniería inversa de superficies libres de alta precisión (álabes, moldes).

## Riesgos

- Escaneos con huecos o ruido (metal brillante) → el ajuste reporta su error y la región mala;
  recomendar spray mate en la guía de uso.
- Archivos enormes (cientos de MB) → límite de subida explícito y decimado previo; error que
  lo dice, nunca un cuelgue.
- Unidades mal detectadas (pulgadas vs mm) → D3 exige confirmar con una cota conocida.

## Bitácora
