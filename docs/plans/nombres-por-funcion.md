---
estado: en curso
nota: contrato aprobado (D1–D18 vetables); fix «pandea» y F0 hechos (ajustes A1–A18 en la Bitácora); F1 (dato y respaldo) hecha en la rama worktree-agent-ad1e9b7996718701f, sin mergear; siguen F2–F6
descripcion: cada mando, piloto y sensor se ve por lo que HACE («Marcha», «Tapa del tanque»), con la designación chica al lado, y la puerta de publicación no aprueba una máquina cuyos mandos no tienen nombre
---

# Nombres por función — «Veo qué hace cada botón sin abrir el plano»

Fuera del roadmap: es un subplan de la máquina viva (V8.4) y del tablero (V8.5).

**Aprobación**: D1–D18 las aprueba Claude con el criterio que le delegó el dueño, y quedan
vetables. Un veto se anota en la Bitácora y ajusta la fase que todavía no se lanzó.

## 1. Estado y origen

Lo pidió Mario el 2026-10-27. Abrió «Mandos» en la sesión viva de la mezcladora de paletas de
200 L y tuvo que preguntar qué hacía cada botón:

> «tienes que darle un nombre y descripción para saber lo que hace … no te digo que lo rellenes de
> texto, sé más como Apple, pero no entiendo cuando dice solamente -Q1, tendría que ver los planos
> para eso»

Lo quiere como REGLA al construir mandos, pilotos y otras herramientas, y quiere saber qué otras
superficies del visor tienen el mismo defecto.

Ampliación del mismo día: la regla es también un ÍTEM de la puerta de publicación, para que la
cumpla cualquiera que construya máquinas, en cualquier PC.

## 2. El problema (medido)

**Inventario completo**, superficie por superficie y por gravedad: en el [informe](nombres-por-funcion-informe.md) § 1, anexo de
este borrador. Lo esencial:

- **El dato no existe.**
  - `AddDeviceParams` (`commands/models_electrico.py:70-136`) y `Dispositivo`
    (`library/electrico/modelo.py:75-111`) no tienen campo de nombre.
  - El `inicio` de la sesión viva lleva `designacion, tipo, ref, color, pieza` por mando
    (`cosim/vivo_fotograma.py:62-76`) y por piloto (`:112`).
- **La UI pone la designación como lo principal y el TIPO genérico al lado:**
  - `vivo/PanelMandos.tsx:168-169`, con «también con clic en el 3D» repetido en las 8 filas;
  - pilotos: `:276-280`, «Piloto» en las cuatro filas;
  - lecturas: `vivo/lecturas.ts:76`, -K2 y -K3 iguales.

  En la mezcladora, -S1/-S2/-S3 se leen igual («Pulsador [Presionar]»), y lo mismo -P3/-P4.
- **El selector no muestra su posición.** `PanelMandos.tsx:245` la guarda en un `useState(null)`
  local, aunque el modelo la publica (`cosim/modelos/mandos.py:198-199`, `<des>.posicion`). Y
  «[0][I]» no dice manual o ciclo.
- **Una cosa, dos nombres.** El resguardo es «Resguardo» en Mandos (`vivo/mandos.ts:69`) e
  «Interruptor de resguardo» en «Simular falla» (`vivo/fallas.ts:50`). Hay tres tablas de nombres
  de tipo en la UI (`mandos.ts:64`, `fallas.ts:45`, `arbolSenales.ts:18`).
- **Códigos opacos en el resto:**
  - «Simular falla» ofrece «c160 · Cable» (`FallasVivas.tsx:100`; `services/cosim_red.py:231`);
  - el accionamiento manual dice «posición 14» (`neumatica/AccionamientoManual.tsx:42-54`);
  - el esquema dice «Regulador de caudal» ×2 y «Silenciador» ×3;
  - Tablero → Aparatos usa el nombre de CATÁLOGO como secundario (`services/tablero_panel.py:301`);
  - en «Pruebas», el título es el id del escenario y la descripción trae «c68_vastago»
    (`pruebas/VistaPruebas.tsx:65,102`);
  - las juntas se muestran por `name`: «c388_puerta» (`KinematicsPanel.tsx:194`, `EventosVivos.tsx:23`).
- **El nombre con sentido sólo existe a medias:**
  - el de la pieza de campo («Interruptor de tapa -B1», `c66`);
  - los comentarios del ST.

  Los aparatos de la PUERTA del tablero tienen pieza generada por `layout_tablero` con el nombre
  del catálogo («… · -S1 Pulsador Ø22 verde 1NA», `commands/tablero.py:156-157,194`). -S0, -S3 y
  -Q1 ni pasan por el PLC: el rearme va cableado `-S3:14 → -K2:S34` y `-K3:S34`.
- **Miente** (va primero, fix aparte): «El vástago de -MM1 pandea» con FS = 109. La frase de
  `services/neumatica_panel.py:137` no distingue el aviso «λ < 100 sin fy» del pandeo real
  (`library/neumatica/calculo.py:244-246`).

## 3. Lo que se revisó antes de escribir esto

- **`doc/carril.py:101-104`**: `layout_tablero` sólo lee `ref, designacion, ubicacion, cantidad,
  pieza` del `add_device`. Un campo nuevo fuera de `CAMPOS_LECTURA` no re-ejecuta el layout. Por
  eso NO se renombran sus piezas (D6).
- **`commands/electrico.py:40-49`**: `add_device` es del carril (`_exec_carril`). Sin huella nueva
  ni `version`, y sin `GEOM_CACHE_EPOCH`.
- **`tests/test_firma_dispositivo.py:122-136` y `services/escenarios.py:49`**: todo campo nuevo de
  `Dispositivo` decide entre firma y `FUERA_DE_FIRMA`.
- **`services/tablero.py:95-121`** (`piezas_en_tabla`, llamada en `api/routers/cosim_vivo.py:286`):
  el patrón para decorar el `inicio` en la API sin tocar el worker ni `COSIM_EPOCH`.
- **`library/calidad/registro.py`**:
  - `Entrada`: id, título, modo de falla, norma, familia, `aplica_si`, evaluar, elementos;
  - `hay(tipo)` sobre `hechos["elementos"]` (`services/puerta_hechos.py:140-158`);
  - `VERSION_REGISTRO = "11"` (`:82`);
  - FALLA bloquea y SIN_EVALUAR también.
- **`library/calidad/puerta.py:187` (`erc`)**: `riesgos.electrico` falla con cualquier aviso del
  ERC. Si la regla viviera en el ERC, una falta de nombre saldría como riesgo eléctrico (D8).
- **`library/calidad/justificadas.py`**: sólo avisos. El ítem nuevo es FALLA sin justificación.
- **`cosim/modelos/seguridad.py:83`**: `BORNES_ENTRADA` = S12, S22 (canales) y S34 (rearme). De ahí
  se derivan el grupo «Seguridad» y lo que rearma cada pulsador (D10, D11).
- **`commands/electrico.py:131-160`** (`prefijar`): `insert_project` copia los params del carril
  con su aspecto de función. El rótulo viaja solo, y la unicidad se mide por aspecto (D5).

## 4. Decisiones (para vetar)

- **D1. El nombre es un DATO declarado en `add_device`**: `rotulo` (≤ 30 caracteres, el texto de
  la placa de leyenda), `estados` (el nombre de cada posición o estado de SU ficha, validado
  contra el modelo en el evaluador, como `ajustes`) y `descripcion` (opcional, una frase,
  ≤ 100 caracteres).
  - Default `""`/`{}`: un log viejo regenera igual, sin upcaster. Se anota en `CAMPOS` de
    `tests/test_contrato_comandos.py`.
  - Porqué: lo que más importa (puerta del tablero, seguridad cableada) no tiene otra fuente, y es
    un ENTREGABLE (placa de leyenda; IEC 60204-1 § identificación funcional, numeral a confirmar
    en F0).
  - En el comando y no en el manifest: el `name` de las piezas y la designación ya viven en el
    log, `insert_project` lo copia solo y el undo sale gratis.
- **D2. Alcance**, sin pedir rótulo a lo que su tipo ya nombra:
  - **lo que se opera**: `MANDOS` + electroválvula con `manual`;
  - **lo que se lee**: piloto, hmi; y sensores (sensor, presostato);
  - **lo repetido** (dos del mismo tipo: relés, reguladores, cilindros): sólo aviso de
    `delivery_check`.

  El PLC, la fuente, el variador único, la bornera y la red se nombran por su tipo.
- **D3. Respaldo para MOSTRAR, nunca para APROBAR** (`services/rotulos.py`, una sola fuente):
  1. rótulo declarado;
  2. nombre de la pieza ligada que no generó un layout, sin designación ni prefijo;
  3. relé de seguridad → «Seguridad de» + los rótulos de lo que vigila (S12/S22);
  4. tipo de la ficha + su distintivo de catálogo («Pulsador verde»).

  Nunca la designación sola ni un id de comando. Cada fila lleva `origen`. El ST y las variables
  del PLC NO se muestran: sólo van como `sugerencia` en el caso de la puerta.
- **D4. Ítem `interfaz.nombres_por_funcion`** en `REGISTRO`:
  - `Entrada`, familia «seguridad»;
  - norma: «IEC 60204-1 §16.3 (a confirmar en F0) · criterio de diseño»;
  - `aplica_si = hay("operables", …)`, `elementos = "operables"`;
  - **FALLA sin justificación posible**: falta un dato que el modelador puede escribir;
  - SIN_EVALUAR si el carril no evalúa;
  - `VERSION_REGISTRO` "11" → "12", con su línea en el docstring.
- **D5. Criterio determinista** (`library/calidad/nombres.py`, puro). Detalle y tabla de ejemplos
  en el [informe](nombres-por-funcion-informe.md) § 2.5. Un rótulo vale si:
  - está declarado;
  - le queda una palabra de ≥ 3 letras al quitar designaciones, tokens de la ref y del `name` de
    la ficha, colores, números, medidas, códigos de contacto, conectores y una tabla CERRADA de
    nombres de tipo;
  - no trae `_`, `%`, `:` ni `c\d+`;
  - es único en su aspecto de función;
  - y, en un selector o una electroválvula manual, todas sus posiciones tienen nombre.

  La tabla de tipos no se abre para aprobar un rótulo.
- **D6. Las piezas del tablero NO se renombran**: `CAMPOS_LECTURA` no cambia. El rótulo se une al
  LEER (ficha de pieza, árbol, paneles). Renombrar re-ejecutaría el layout y lo que tiene detrás
  (40 comandos en la mezcladora) por un texto.
- **D7. Fuera de la firma y del worker**: `Dispositivo.rotulo/estados/descripcion` en
  `FUERA_DE_FIRMA`. El `inicio` se decora en la API (`rotulos_en_tabla`, junto a
  `piezas_en_tabla`): sin `COSIM_EPOCH`. Claves AGREGADAS al `inicio`: sin `version`.
- **D8. NO va en el ERC.** `delivery_check` suma la regla «nombres por función» (AVISO, con el
  mismo criterio de D5 más lo repetido de D2), en el bucle del modelador. `VERSION_BATERIA` sube.
  `riesgos.electrico` no la ve.
- **D9. Fila de mando**:
  - el rótulo manda (`--fw-medio`) y la designación va detrás, chica (`--fs-chico`, tinta
    secundaria);
  - un mando que SE QUEDA (seccionador, resguardo, selector) es un control SEGMENTADO con los
    nombres de sus estados, y el segmento marcado es el LEÍDO de la señal;
  - el pulsador con resorte y la seta siguen siendo botón con verbo;
  - la concordancia («Cerrada») la declara el modelador en `estados`; sin ellos, el default por
    tipo lo da el servidor (seccionador «Apagado/Encendido»).
- **D10. Un mando NUNCA se deshabilita por no tener efecto ahora.** El panel es un banco de
  prueba: «rearme con la tapa abierta no debe rearmar» es lo que se prueba. El rearme muestra al
  lado el estado de lo que rearma (los relés a los que va cableado), en palabras de su acción:
  «Falta rearmar» / «Rearmada». No usa «Corta la marcha»: junto a un botón, eso se lee como lo
  que el botón hace.
- **D11. Agrupar por propósito sólo con más de 5 mandos**, con regla derivada:
  - seccionador → Energía;
  - seta, resguardo y todo mando cableado a una entrada de relé de seguridad → Seguridad;
  - el resto → Operación.

  Después van Pilotos y Lecturas.
- **D12. Veredicto de «Mandos»** (pieza `Veredicto`): sólo hechos leídos de señales, en orden de
  bloqueo. Sin energía → parada de emergencia presionada → «<resguardo> abierto» → «La seguridad
  corta la marcha» → «Energía y seguridad habilitadas». Nunca «Lista para arrancar»: el permiso del
  PLC no se conoce.
- **D13. Una sola fuente de nombres** (servidor). Se borran las tablas de tipo de la UI
  (`mandos.ts:64`, `fallas.ts:45`, `arbolSenales.ts:18`) y «también con clic en el 3D» pasa a UNA
  `<Pista>` arriba.
- **D14. Pruebas**: título = `nombre` humanizado, derivado y sin campo nuevo. `set_scenario` avisa
  (no rechaza) una `descripcion` con ids de comando o pieza.
- **D15. Juntas** (Eventos, Cinemática): se nombran por su pieza HIJA; el `name`, secundario.
- **D16. `descripcion` sólo en la ⓘ (N2)**, nunca a la vista. Presupuesto de `ui/CLAUDE.md`.
- **D17. La BOM queda fuera**: es para comprar, la ref es su dato. Al backlog: Descripción
  primero y una columna de designaciones.
- **D18. Máquinas viejas**: FALLA en el ítem hasta declarar. La sugerencia (pieza, variable del
  PLC) va como texto en el caso y nunca se aplica sola. F6 completa la mezcladora y los testigos.

## 5. Alternativas descartadas

- **Derivar del ST**: comentarios libres que nombran dos aparatos o bornes («canal 1 tras -S0 y
  -B1», «-K2 33-34: rele…»); variables en jerga (`rs_ok`); y -S0/-S3/-Q1 no están.
- **Derivar del nombre de la pieza**: el layout las nombra por catálogo. Queda como respaldo para
  mostrar (D3).
- **Metadato en el manifest**: necesitaría copia propia en `insert_project` y undo aparte.
- **Dentro de `ajustes`**: se valida contra el `modelo` y entra a la firma.
- **Regla del ERC**: haría fallar `riesgos.electrico` por algo que no es eléctrico, y doble (D8).
- **Renombrar las piezas del layout**: re-ejecución por un texto (D6).
- **Un campo `genero`** para concordar estados: `estados` resuelve eso, los selectores y las
  válvulas.
- **Deshabilitar un botón sin efecto**: escondería la prueba (D10).
- **Marcar «sin nombre» en el visor**: castiga a quien mira por la omisión del modelador. La
  marca va a la puerta y a `delivery_check`.

## 6. Fases

### Antes de F1, fuera del plan: la frase que miente (HECHO, entró con el contrato)

**Fix directo, S, ~20 min.** `neumatica_panel._frase_memoria` dice «pandea» sólo con estado
«error». Con «aviso» por λ, dice lo que pasa: «Falta el límite elástico del vástago…». Lleva un
test con el aviso de la mezcladora.

### F0 — Medir (sólo lectura) · S · ~15 min

- Leer IEC 60204-1 § identificación funcional de mandos e indicadores y fijar edición y numeral
  (regla de citas: sin el texto leído, «criterio de diseño»).
- Contar, en la mezcladora y en cada documento de prueba con carril (`tests/data/tablero_piloto.json`,
  fixtures de `test_puerta_*`, testigos de `test_puerta_publicacion.py`), cuántos operables por
  tipo hay y cuáles caerían a FALLA.
- Correr el criterio de D5 sobre 30 rótulos reales y de ejemplo, en un script suelto. Ningún falso
  ✓ con nombres de catálogo; los falsos ✗ se anotan.
- Verificar que `<des>.posicion` llega en `textos` y que los lados de una electroválvula son las
  claves de `estados`.
- Medir el tamaño de `PanelMandos.tsx` (317 líneas) para planear el corte bajo 500.

Sale con ajustes A1…An a este contrato.

### F1 — El dato y el respaldo (backend) · M · ~55 min · depende de F0

**`commands/models_electrico.py`**:
- `rotulo`, `estados`, `descripcion`, con su description para el agente;
- su `pista` si cambia (`commands/pistas.py`).

**`library/electrico/modelo.py`**:
- campos de `Dispositivo` y `dispositivo_desde_ficha`;
- el evaluador del carril valida `estados` contra la ficha, con el error accionable que lista las
  claves válidas.

**`services/escenarios.FUERA_DE_FIRMA`** y `tests/test_firma_dispositivo.py`.

**`services/rotulos.py`** (dominio, lee un `Document`):
- `rotulo_de`, con la cadena D3 y su `origen`;
- `estados_de`, con los defaults por tipo;
- `grupo_de` (D11);
- `rearma_a` (S34);
- el nombre de un cable por sus extremos;
- el de una junta por su hija;
- el de un escenario humanizado.

Consumidores del servicio:
- `api/routers/cosim_vivo.py`: `rotulos_en_tabla` en el `inicio`, con `rotulo`, `origen`,
  `estados`, `descripcion`, `grupo` y `rearma` por fila de mandos, pilotos, dispositivos,
  válvulas, fallas y ramas;
- `services/tablero_panel.py` (aparatos, textos de calentamiento);
- `services/neumatica_panel.py` (símbolos, ítems, cilindros);
- `services/pruebas_panel.py` (título);
- `get_circuit`, que expone el rótulo.

**`design/guidelines.py`**: `corto`, `detalle` y `verificar` ([informe](nombres-por-funcion-informe.md) § 4). Golden del MCP: revisar
y `--congelar`.

**Gates** (pytest):
- `test_rotulos.py` nuevo, con la cadena y los defaults;
- `test_contrato_comandos.py` (CAMPOS);
- `test_firma_dispositivo.py`;
- `test_fotograma_contrato.py` (claves agregadas);
- `test_mcp_golden.py`;
- `test_pistas.py`;
- un log viejo de la piloto regenera byte a byte igual (`test_golden_regen.py`).

### F2 — La regla que obliga (puerta y entrega) · M · ~50 min · depende de F1

**`library/calidad/nombres.py`** (puro): el criterio D5 con su tabla cerrada; casos con
designación, motivo, piezas y `sugerencia`.

**`services/puerta_hechos.py`**: `elementos["operables"]` por tipo.

**`services/puerta_publicacion.py`**: el insumo `nombres`, filas de `services/rotulos.py`.

**`library/calidad/registro.py`**:
- la `Entrada` de D4;
- el id en la lista del docstring;
- `VERSION_REGISTRO = "12"` y su línea en «Qué cambió».

**`library/delivery.py`**: la regla «nombres por función» (AVISO, más lo repetido);
`VERSION_BATERIA` 3 → 4.

**`set_scenario`**: el aviso de ids en la descripción (D14).

**Gates**:
- `tests/test_puerta_nombres.py` nuevo:
  - cada fila ✓/✗ de la tabla de D5;
  - unicidad por aspecto (dos `insert_project` con «Marcha» pasan);
  - un selector sin `estados` falla;
  - NO_APLICA sin carril;
  - SIN_EVALUAR si el control revienta;
  - lo derivado no aprueba;
- `test_puerta_publicacion.py`, `test_puerta_f3.py` y `test_extensiones_f1d.py` con
  `version_registro` "12";
- los testigos públicos con su veredicto por ítem al día. El que tenga tablero declara sus rótulos
  en el fixture: no se relaja el ítem;
- `test_delivery.py`.

### F3 — «Mandos» (UI) · M · ~50 min · depende de F1 · en paralelo con F4

**`ui/src/vivo/`**:
- la fila (D9) en un componente propio, para que `PanelMandos.tsx` quede bajo 500 líneas;
- `Segmentado` para seccionador, resguardo y selector, leyendo `<des>.cerrado` / `<des>.posicion`;
- grupos (D11), veredicto (D12) y una `<Pista>`;
- ⓘ con `descripcion`;
- pilotos y lecturas con rótulo;
- «Simular falla» con rótulos (aparato, contacto, cable por extremos);
- la apertura con el escenario humanizado;
- se borran `NOMBRES` de `mandos.ts`, `TIPOS` de `fallas.ts` y lo que repite `lecturas.ts`;
- el muestrario con datos de la mezcladora: 8 mandos, 4 pilotos y 2 relés.

**Gates**: `npm test` (con `mandos.test.ts` y `fallas.test.ts` al día, `textoDeAyuda`,
`tuteoNeutro`, `tamanoArchivos`) y `npm run build`.

### F4 — El resto de las superficies (UI) · M · ~45 min · depende de F1 · en paralelo con F3

- `tablero/DetalleTablero.tsx`: aparatos rótulo + «-K2 · catálogo».
- `neumatica/`: ficha del cilindro, símbolos, accionamiento manual con `estados`.
- `pruebas/VistaPruebas.tsx`: título humanizado.
- `vivo/EventosVivos.tsx` y `panels/KinematicsPanel.tsx`: junta por su hija.
- `vivo/PanelSenales.tsx`: cabecera «rótulo · -K2».
- `visor/FichaPieza.tsx`: una línea «Marcha · -S1» si la pieza es un dispositivo.

**Gates**: los mismos de F3.

### F5 — Revisión de diseño a ciegas · S · ~40 min · depende de F3 y F4

- **Capturas** del muestrario, en el tema vigente (`ui/CLAUDE.md`: hoy sólo oscuro), a ancho
  completo y a `?ancho=420`: Mandos (sesión corriendo, con el seccionador abierto y con la seta
  presionada), Simular falla, Tablero → Aparatos, Neumática y Pruebas.
- **Juez**: un subagente SIN contexto.
- **Rúbrica** (1–5 cada una):
  1. ¿Se entiende qué hace cada control sin conocer la designación?
  2. ¿La designación se encuentra cuando se la busca y no estorba cuando no?
  3. ¿El estado de cada mando que se queda se lee de un vistazo?
  4. ¿Hay texto que sobra o se repite?
  5. ¿La jerarquía es por peso y tamaño, sin cajas ni colores nuevos?
  6. ¿El veredicto dice la verdad y sólo eso?
  7. ¿Algo se ve como deshabilitado sin motivo?
- Lo confirmado se corrige y lo rechazado lleva su porqué en la Bitácora.

### F6 — Verificar con una máquina real · S · ~30 min · depende de F2–F5

- **Por MCP, sobre una API de flota** (nunca la del visor en uso):
  1. un subagente modelador abre una COPIA de la mezcladora;
  2. corre la puerta y comprueba que `interfaz.nombres_por_funcion` sale FALLA con 14 casos y sus
     sugerencias;
  3. declara los rótulos y `estados` con UN `edit_batch`;
  4. comprueba que el ítem queda OK y que `delivery_check` no avisa.
- Mismo cierre en los testigos con tablero.
- **Mario abre «Mandos» y lo juzga**: es el gate final.

**Estimación** (tabla de tiempos medidos):
- agentes: F0 15 + F1 55 + F2 50 + F3 50 + F4 45 + F5 40 + F6 30 ≈ 285 min, más el fix aparte
  (~20);
- merges: tres lotes × ~35 min (F1; F2+F3+F4 juntos en una suite; F5+F6);
- con F2, F3 y F4 en paralelo (tope de 3 agentes): **≈ 4,5–5 h de pared**.

## 7. Lo que este plan NO hace

- No renombra piezas ni cambia geometría.
- No toca el texto del programa del PLC, las hojas de «Señales» ni la lista de conductores: ahí el
  código ES el dato.
- No cambia la BOM ni la cotización (D17).
- No traduce designaciones dentro de textos libres (descripciones de escenarios, ERC para el
  agente).
- No agrega temas ni colores.
- No genera la placa de leyenda en los planos. Queda listo el dato para el plano del tablero, en
  un plan aparte.

## 8. Riesgos

| riesgo | mitigación |
|---|---|
| Toda máquina aprobada con mandos vuelve a FALLA al subir `VERSION_REGISTRO` | Es lo pedido (D18). F6 la cierra en la mezcladora y los testigos; la sugerencia de cada caso hace la corrección un solo `edit_batch` |
| Falsos ✗ o ✓ del criterio | F0 lo mide sobre rótulos reales antes de fijar la tabla; cada ejemplo es un test; la tabla es cerrada y no se abre para aprobar |
| `PanelMandos.tsx` pasa de 500 líneas | F3 parte la fila y el segmentado en componentes |
| La fila de cada ítem de un test con tablero cambia de veredicto | Los fixtures declaran sus rótulos; ningún test se relaja |
| El golden del MCP cambia (brief) | Es deliberado: diff revisado y `--congelar` en F1 |
| El rótulo se escribe en jerga del agente («rs_ok») | Regla 3 de D5; la description del campo lleva ejemplos de placa |
| Dos instancias de `insert_project` con el mismo rótulo | Unicidad por aspecto de función (D5) |

## 9. Bitácora

### F0 — medir (2026-10-27)

Sólo lectura. Verifiqué 26 afirmaciones con archivo:línea: se corrigen 4 (A16).

**Lo medido:**
- **Norma.** El §16.3 sale de la checklist DGUV/IFA 3848 (06.2020) sobre IEC 60204-1:2016; la
  webstore de la IEC confirma la ed. 6.0 + AMD1:2021. El texto de la norma no se leyó.
- **Mezcladora.** 15 operables, y caen los 15. Ningún testigo público tiene carril.
- **Criterio D5 sobre 45 rótulos.** Tal como estaba escrito daba 7 falsos ✓; ajustado da 0.
  Quedan 2 falsos ✗: «Paro de emergencia» y «Marcha/paro».

**Ajustes aprobados.** Prevalecen sobre el texto de las D y F de arriba.

- **A1 — Norma.** La `norma` del ítem es «IEC 60204-1:2016 §16.3 (mandos) · criterio de diseño
  (pilotos y sensores)». Sale el «a confirmar».
- **A2 — Nombre del servicio.** Pasa a `services/nombres_aparatos.py` (con
  `tests/test_nombres_aparatos.py`), porque `services/rotulos.py` ya existe: son los rótulos del
  video.
- **A3 — La `Entrada` vive en `calidad/nombres.py`.** `registro.py` (498 líneas) sólo la importa; su
  docstring se compacta y queda ≤ 500.
- **A4 — Claves de `estados`, por tipo y en UNA tabla pura.**
  - selector: `modelo.posiciones`;
  - electroválvula: las posiciones del carrete, no `lados` (la fila `valvulas` del `inicio` suma
    `posiciones`);
  - seccionador y resguardo: `cerrado`/`abierto`;
  - botonera: sus actuadores.
- **A5 — `estados` nunca suprime un dispositivo.** Es estricto al entrar. Al cargar, una clave
  vencida se ignora con aviso. Se tocan `electrico_eval._dispositivo` y `neumatica_eval.dispositivo`,
  con el test del log que trae una clave vencida.
- **A6 — Literales de `add_device`.** `rotulo`, `estados` y `descripcion` van en sus `literales`:
  una cadena que empieza con «=» es expresión.
- **A7 — Criterio D5 ajustado.** Rechaza también un código de catálogo y una designación dentro del
  rótulo. La tabla cerrada de tipos incluye «pos», fotocélula, final, carrera, seguridad,
  emergencia y los estados sueltos. Los falsos ✗ quedan como casos del test.
- **A8 — Lo que el tipo ya nombra queda fuera del ítem.** La seta, el seccionador, el HMI y la válvula
  de corte, si son ÚNICOS en su aspecto, se muestran con su nombre FUNCIONAL por tipo («Parada de
  emergencia», «Interruptor general», «Panel de operador»). Con 2 o más en el aspecto, entran al
  ítem. La mezcladora queda en 13 casos.
- **A9 — Unicidad por (aspecto, clase).** Mando, indicador y sensor se cuentan por separado: -S1 y
  -P1 pueden llamarse los dos «Marcha».
- **A10 — F6.** Espera la cifra que dé el criterio final, y su `edit_batch` lleva `estados` para -S4,
  -QM1 y -B4.
- **A11 — Se recorre la CADENA SERIE.** Lo que vigila un relé de seguridad y lo que rearma un
  pulsador se leen recorriéndola: desde S12/S22, hacia atrás por los NC, hasta la alimentación. No
  basta la red directa del borne: -K2:S12 sólo ve a -B1. S34 directo vale.
- **A12 — `entrega.semaforo` no repite el ítem.** `semaforo_entrega` descarta la regla «nombres por
  función», porque la juzga su ítem (el precedente es `seguridad.electrico`). `delivery_check`
  sigue avisando, y lo repetido nunca bloquea.
- **A13 — Gates de F2.**
  - El defecto sembrado `mando_sin_rotulo`: un tablero con todos los rótulos menos uno → FALLA.
  - Los 4 testigos se re-congelan con «12» (el ítem va en NO_APLICA) usando
    `scripts/testigos.py --en-proceso --congelar`.
- **A14 — El log viejo.** Su gate es `test_neumatica_carril.py` (`carril_v81_golden.json`), y el
  `circuito` suma `rotulo`/`estados`/`descripcion` SÓLO si están declarados.
- **A15 — La sugerencia limpia antes de cortar.** Quita «·», «(…)» y la designación, y después
  recorta a 30 en palabra. Es texto: nunca aprueba.
- **A16 — Citas corregidas.**
  - `piezas_en_tabla` está en 99-121;
  - `erc` deja pasar los avisos justificados;
  - el aparato de `tablero_panel` está en las líneas 301-302.
- **A17 — Resguardo sin `estados`.** Toma por default «Cerrado/Abierto», y `delivery_check` (no la
  puerta) lo avisa: el RESG-2NC se usa también como sensor de recipiente o de cadena floja.
- **A18 — F3.** El seccionador y el resguardo se leen de `senales` (bool), y el selector y la válvula,
  de `textos`. El `Segmentado` recibe el valor leído; no lo guarda en `useState`.

### F1 — el dato y el respaldo (2026-10-27)

**Hecho.**
- `add_device.rotulo` (≤ 30), `estados` (dict, ≤ 30 por nombre) y `descripcion` (≤ 100), con default
  `""`/`{}`, en `literales` (A6) y en `CAMPOS`. La description del modelo lleva ejemplos de placa, y la
  pista de campo es «Lo que hace, como en su placa…».
- `library/electrico/estados.py` (puro) es la tabla A4: `claves`, `validar` y `filtrar`.
  - Al ENTRAR valida el sello de `add_device` (`al_crear`/`al_editar`). Al editar sólo valida si
    cambian `estados` o la ref, así un estado vencido no traba la edición de otro campo.
  - Al CARGAR, los dos caminos (`dispositivo_desde_ficha`, `neumatica_eval.dispositivo`) filtran: lo
    vencido queda en `Dispositivo.estados_vencidos` y el aparato se conserva (A5). `circuito` lo dice
    en `estados_vencidos` + `aviso_estados`.
- `Dispositivo.rotulo/estados/descripcion/estados_vencidos` en `FUERA_DE_FIRMA`.
- `services/nombres_aparatos.py` (A2) da:
  - `Nombres` con `rotulo_de` (cadena D3 + `origen`; A8 en el paso 4);
  - `estados_de`, `grupo_de` (D11), `vigila` y `rearma_a` (A11, por la cadena serie);
  - `ramas` (el cable por sus extremos) y `fila`;
  - `limpiar_nombre_pieza` (A15), `nombre_junta` (D15) y `humanizar` (D14);
  - `para_tabla` + `nombres_en_tabla` para el vivo.
- Consumidores, todos con claves AGREGADAS:
  - el `inicio` del vivo: `rotulo`, `origen`, `grupo`, `estados`, `descripcion` y `rearma` por fila;
    `posiciones` en `valvulas`, `nombre` en `ramas` y `juntas`, y `titulo_escenario`;
  - Tablero → aparatos: `rotulo`/`origen`; el calentamiento dice «Interruptor general (-Q1)»;
  - Neumática: `nombres` por designación;
  - Pruebas: `titulo` por fila;
  - `circuito`: sólo lo declarado (A14).
- `guidelines.py`: el `corto` («con su rótulo»), el `detalle` (ajustado a A8: la seta, el
  seccionador y el panel de operador únicos no lo necesitan) y el golden del MCP re-congelado (sólo
  cambia la línea 11 de las instructions).

**Decisiones con criterio (vetables).**
- **D7 también en el LOG.** `firma_documento` hashea el log entero, así que ponerle rótulo a una
  máquina probada vencía sus escenarios. `escenarios.PARAMS_FUERA_DE_FIRMA` saca esas tres claves de
  `add_device` antes del hash. Un log sin ellas da el hash de siempre: los 4 testigos de
  `test_firma_dispositivo` no se mueven y no hay `COSIM_EPOCH`, `version` ni `GEOM_CACHE_EPOCH`. La
  firma de la PUERTA (`firma_modelo`) sí las ve, a propósito: el nombre es un ítem suyo (F2).
- **El estricto al entrar va en el sello, no en el evaluador.** En el evaluador, una mutación
  cualquiera revertiría el documento entero por un estado vencido de OTRO aparato.
- **Texto que no se cambió.** Las frases de los ítems de Neumática siguen con la designación (F4 las
  muestra con `nombres`), y el `verificar` de `guidelines` NO dice «avisa los aparatos sin rótulo»:
  sería falso hasta que entre la regla de F2, que lo suma.
- **El respaldo por tipo** se llama «Interruptor de resguardo» (una sola forma, D13). `ambar` del
  catálogo se lee «ámbar». La cadena del relé une los rótulos en minúscula: «Seguridad de parada
  de emergencia y tapa del tanque».
- **Lo que no es de un aparato.** Una rama sin conductor conocido se llama «Cable», nunca su id; una
  junta sin pieza hija, su nombre humanizado sin el prefijo `cNN_`.

**Cifras.** `test_nombres_aparatos.py` tiene 28 casos. Suite completa (`-n auto`): un solo rojo,
`test_pruebas_panel` (comparaba la fila entera y faltaba `titulo`). Se corrigió y se re-corrió
verde junto con los gates de documentos; ruff limpio. El golden v81 (`test_neumatica_carril`) quedó
byte-idéntico y las cuatro firmas de `test_firma_dispositivo` no se movieron.
