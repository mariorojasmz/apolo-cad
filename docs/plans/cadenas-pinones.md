---
estado: en curso
nota: F1 y F2 en main; falta F3 (demo por MCP con la API reiniciada, que se hace al modelar la máquina piloto)
descripcion: El catálogo trae cadenas de rodillos y piñones reales (ASA 40, que es lo que se vende en Lima, e ISO 08B/10B/12B) y una cadena se arma sola entre dos piñones, con eslabones pares y su verificación de potencia
---

# El agente pone piñones y cadenas reales, y la cadena se arma sola entre dos piñones

## Estado y origen

Mario (2026-10-08) eligió como máquina piloto de [publicacion-tienda](publicacion-tienda.md) un
transportador de rodillos motorizado por cadena. Al revisar el catálogo salió que no hay piñones
ni cadenas, y Mario pidió: «seria bueno tener el catalogo de piñones y cadenas». Después: «cuando
tengas el plan, implementalo defrente, no me preguntes».

## Lo que hay hoy

Medido sobre `main` en `9199fa9`.

- **El catálogo (256 refs) no tiene piñones ni cadenas.**
  - `85_transmision.yaml` trae poleas dentadas sin dientes («POLEA-40…125», builder `pulley`),
    poleas en V y tensores de banda.
  - `20_rodillos.yaml` trae rodillos de gravedad Ø50/60/80 con eje pasante (builder `roller`,
    `builders.py:37`).
- **`create_conveyor` sólo cuelga el motor, sin transmisión.**
  - `library/conveyor.py:120-123` pone el motorreductor «colgado bajo el larguero».
  - `CreateConveyorParams` (`commands/models.py:310`) no expone el largo del rodillo ni la
    transmisión.
- **Cómo se agrega una familia** (precedente: [garruchas-catalogo](garruchas-catalogo.md)):
  - YAML en `library/data/` con prefijo alto para que cargue al final y no reordene refs.
  - El builder va en un módulo propio, porque `builders.py` está congelado en 847 líneas;
    `loader.py` une los registros y rechaza nombres repetidos.
  - La cuenta vive en `tests/test_catalog_datadriven.py:133` (`len(CATALOG) == 256`) y en el
    CLAUDE.md raíz.
- **Anclas**: `insert_component` transforma las anclas LOCALES del componente a mundo con su
  matriz (`commands/registry.py:1760-1765`, `kernel/matrix.py::transform_anchors`). Hoy las
  anclas son por CATEGORÍA (`library/catalog.py:78`, `_CATEGORY_ANCHORS`: chumaceras,
  sinfín, garruchas), no por familia ni por parámetros.
- **Archivos congelados** (`tests/test_tamano_archivos.py`):
  - `commands/registry.py` (2207 líneas), que tiene TODOS los executors;
  - `commands/models.py` (1359);
  - `library/rules.py` (928);
  - `library/engineering/report.py` (555).

  Un comando nuevo no cabe en `registry.py` sin sacar antes otras tantas líneas.
- **Dónde entra una regla de ingeniería**: `services/engineering_rules.py::structure_rules`
  (55 líneas). La comparten `/api/checks` y la memoria de cálculo.
- **Exclusión del FEA**: `library/checks.py` `FEA_HARDWARE_CATS` no incluye `transmision`, así
  que una polea dentro de un grupo FEA se malla.
- **`test_contrato_comandos.py`** guarda versión + huella del código de cada executor. La huella
  es la de la función, no la de sus helpers (`:20-22`, `:289`).

## Lo que se revisó antes de escribir esto

Hubo dos investigaciones (2026-10-08, agentes con navegador) y cuentas propias.

**Mercado de Lima.**
- Las casas de transmisión venden las dos normas: ANSI, que en Perú llaman **«ASA»** o
  «americana» (35, 40, 50, 60, 80), e ISO 606 serie B, que llaman **«BS»** o «europea» (06B,
  08B, 10B…). Los distribuidores revisados:
  - Rodasur (Av. Guillermo Dansey 1912, Cercado);
  - Provinsur (Chorrillos);
  - Ducasse (Miraflores), que vende Tsubaki, Martin y Rexnord;
  - MUCASA, MegaChain, Vercelli, EMSAC y J.REMES.
- **ASA tiene más stock.** En Rodasur, 58 de 95 piñones son ASA (contado con la API de su tienda).
- Nombres locales: «PIÑON SIMPLE PASO ASA 40/1 B Z20 1/2″» («B» = con cubo); «catalina», el
  piñón grande; «candado», el eslabón de unión. El piñón se compra con agujero sin terminar y se
  maquina en taller con chaveta y prisionero.
- **Precios** (Rodasur, marca Donghua; sin decir si incluyen IGV): piñón ASA 40-1 14T S/12,
  15T S/16, 30T S/32; 08B-1 14T S/14; cadena ASA 40-1 Max-Gold S/18 (la unidad, metro o caja,
  no está clara).
- No se encontró en Lima un fabricante de transportadores rodillo a rodillo con ficha técnica:
  los locales hacen polines para banda.

**Datos de norma y de fabricante** (convención: [L] leído, [D] derivado, [E] estimado).

Cadenas (iwis ELITE pp. 26-29 con la tabla ISO 606; Tsubaki EU y US):

| | ASA 40-1 | ASA 40-2 | 08B-1 | 08B-2 | 10B-1 | 12B-1 |
|---|---|---|---|---|---|---|
| paso p | 12,70 | 12,70 | 12,70 | 12,70 | 15,875 | 19,05 |
| rodillo d1 | 7,92 | 7,92 | 8,51 | 8,51 | 10,16 | 12,07 |
| ancho interior b1 | 7,85 | 7,85 | 7,75 | 7,75 | 9,65 | 11,68 |
| perno d2 | 3,98 | 3,98 | 4,45 | 4,45 | 5,08 | 5,72 |
| alto de placa h2 | 12,07 | 12,07 | 11,81 | 11,81 | 14,73 | 16,13 |
| espesor de placa | 1,50 | 1,50 | 1,60 | 1,60 | 1,70 | 1,85 |
| paso transversal pt | — | 14,38 | — | 13,92 | — | — |
| ancho sobre perno | 17,8 | 32,3 | 17,0 | 31,0 | 19,6 | 22,7 |
| rotura mín (kN) | 13,9 | 27,8 | 17,8 | 31,1 | 22,2 | 28,9 |
| kg/m | 0,62 | 1,27 | 0,69 | 1,34 | 0,93 | 1,15 |

Piñones:
- **ASA 40-1, tipo B** (Tsubaki US 40B{z}; Martin 40B15/16 coinciden). Ancho de diente 7,21.

  | z | d0 | de | cubo | largo | piloto | agujero máx | kg |
  |---|---|---|---|---|---|---|---|
  | 12 | 49,07 | 55,1 | 39,7 | 22,2 | 12,7 | 25,4 | 0,20 |
  | 14 | 57,07 | 63,2 | 42,9 | 22,2 | 12,7 | 28,6 | 0,27 |
  | 15 | 61,09 | 67,3 | 46,0 | 22,2 | 12,7 | 31,8 | 0,32 |
  | 16 | 65,10 | 71,4 | 50,8 | 22,2 | 15,9 | 34,9 | 0,36 |
  | 17 | 69,11 | 75,7 | 54,0 | 25,4 | 15,9 | 36,5 | 0,47 |
  | 18 | 73,13 | 79,8 | 58,7 | 25,4 | 15,9 | 38,1 | 0,55 |
  | 19 | 77,17 | 83,8 | 63,5 | 25,4 | 15,9 | 44,5 | 0,65 |
  | 20 | 81,18 | 87,9 | 66,7 | 25,4 | 15,9 | 47,6 | 0,71 |
  | 30 | 121,49 | 128,5 | 82,6 | 25,4 | 15,9 | 57,2 | 1,35 |
  | 45 | 182,07 | 189,2 | 88,9 | 28,6 | 19,05 | 60,3 | 2,40 |
  | 60 | 242,67 | 249,9 | 88,9 | 28,6 | 19,05 | 60,3 | 3,57 |
- **ASA 40-2 dúplex**: Tsubaki D40B14 (cubo 42,9, largo 38,1, 0,48 kg) y Martin D40B15H (cubo
  46,0, largo 38,1, agujero máx 31,75, 0,56 kg). Piloto y d0/de, los del simple de igual z [E].
- **ASA 40 doble-simple** (dos cadenas simples en un cubo, el que se usa rodillo a rodillo):
  Tsubaki DS40A15, largo 35,7; distancia entre hileras 28,6 [E, cota «C» del plano].
- **08B-1 con cubo** (TYMA y Chiaravalli; SKF lo verifica). Ancho de diente 7,2.

  | z | d0 | de | cubo | piloto | largo | kg | agujero máx |
  |---|---|---|---|---|---|---|---|
  | 9 | 37,13 | 41,00 | 24 | 10 | 25 | 0,09 | |
  | 12 | 49,07 | 53,00 | 33 | 10 | 28 | 0,21 | |
  | 14 | 57,07 | 61,80 | 41 | 10 | 28 | 0,32 | 24 |
  | 15 | 61,09 | 65,50 | 45 | 10 | 28 | 0,38 | |
  | 16 | 65,10 | 69,50 | 50 | 12 | 28 | 0,46 | |
  | 17 | 69,11 | 73,60 | 52 | 12 | 28 | 0,51 | |
  | 18 | 73,14 | 77,80 | 56 | 12 | 28 | 0,59 | |
  | 19 | 77,16 | 81,70 | 60 | 12 | 28 | 0,67 | |
  | 20 | 81,19 | 85,80 | 64 | 12 | 28 | 0,76 | |
  | 25 | 101,33 | 105,80 | 70 | 14 | 28 | 1,01 | |
  | 28 | 113,42 | 118,00 | 70 | 16 | 30 | 1,17 | 46 |
  | 30 | 121,50 | 126,10 | 80 | 16 | 30 | 1,46 | |
  | 38 | 153,80 | 158,60 | 90 | 16 | 35 | 2,32 | 50 |
- **08B-2 dúplex** (Chiaravalli): ancho total 21,0, ancho por diente 7,0. Cubo / piloto / largo /
  kg por z:
  - z14: 42 / 12 / 35 / 0,44
  - z15: 46 / 12 / 35 / 0,52
  - z17: 54 / 14 / 35 / 0,73
  - z19: 62 / 14 / 35 / 0,97
  - z21: 70 / 16 / 40 / 1,29
  - z25: 80 / 16 / 40 / 1,82
  - z38: 110 / 20 / 40 / 3,84

  d0 y de, del simple de igual z; los de z21 con la fórmula [D].
- **08B-1 doble-simple** (TYMA 08B-1-z-DS): ancho total 31,0, distancia entre hileras 23,8,
  piloto 10–16. z14, como los cabezales Interroll serie 3500 de 1/2″; cubo, el del simple z14
  [E].
- **10B-1** (TYMA): ancho de diente 9,1. z15: 76,36 / 83,0 / cubo 57 / piloto 12 / L 30. z19:
  96,45 / 103,3 / 70 / 14 / 30.
- **12B-1** (TYMA): ancho de diente 11,1. z15: 91,63 / 99,8 / 70 / 14 / 35. El peso de las tres
  va estimado por volumen [E].

**Forma del diente y fórmulas.**
- Paso primitivo d0 = p/sin(180°/z). Verificado: z14 = 57,07, z57 = 230,54.
- Fórmulas de ISO 606 transcritas en patentes [L]:
  - fondo df = d0 − d1;
  - radio de asiento ri = 0,505·d1 … 0,505·d1 + 0,069·∛d1;
  - ángulo de asiento α = 120°−90°/z … 140°−90°/z;
  - radio de flanco re entre 0,12·d1·(z+2) y 0,008·d1·(z²+180), que es el mayor [D].
- Diámetro exterior:
  - BS: da máx = d0 + 1,25p − d1 [D]; reproduce el Martin D08B14 (64,439);
  - ANSI: de = p·(0,6 + cot(180°/z)) [D]; reproduce los Tsubaki z12, z14 y z60.

**Selección** (fuentes: Tsubaki «Chain Drive Selection», ACA 2001 adaptada de ASME B29.1 para
15 000 h, Renold).
- Largo en eslabones: L = (z1+z2)/2 + 2C/p + p·((z2−z1)/2π)²/C. Centros para un L dado: la
  fórmula inversa de Tsubaki.
- **Potencia nominal ASA 40-1 en HP** (ACA):

  | z | 10 rpm | 25 | 50 | 100 | 300 | 1000 |
  |---|---|---|---|---|---|---|
  | 14 | 0,07 | 0,17 | 0,34 | 0,66 | 1,88 | 5,98 |
  | 15 | 0,08 | 0,19 | 0,36 | 0,70 | 2,02 | 6,41 |
  | 16 | 0,08 | 0,20 | 0,39 | 0,75 | 2,15 | 6,84 |
  | 17 | 0,09 | 0,21 | 0,41 | 0,80 | 2,29 | 7,27 |
  | 18 | 0,09 | 0,22 | 0,43 | 0,84 | 2,42 | 7,69 |
  | 19 | 0,10 | 0,24 | 0,46 | 0,89 | 2,56 | 8,12 |
- Factor de servicio con motor eléctrico (ACA/Tsubaki): suave 1,0, moderado 1,3, fuerte 1,5.
- Factor por hileras: 1,7 (dos).
- No hay tabla numérica publicada para 08B-1. El cuadro de Renold es una gráfica.
- Práctica recomendada:
  - centros 30–50 p;
  - abrazamiento ≥ 120° (Renold pide además ≥ 6 dientes engranados);
  - z ≥ 17 lo normal (Renold ideal ≥ 19); menos de 17, sólo lento y liviano;
  - piñón grande ≤ 114 dientes;
  - eslabones PARES: impar exige eslabón acodado, que Renold desaconseja y ACA desclasifica;
  - flecha del ramal flojo ≈ 4 % del vano (Tsubaki);
  - recorrido de ajuste ≥ 2 % de alargamiento o 2 pasos (Renold);
  - con grasa, v ≤ 4 m/s.

**Rodillo a rodillo.**
- Interroll 3500 usa cabezales Z14 de 1/2″, simples o dobles (hileras a 22 mm), con 0,5 m/s
  máximo con cadena.
- Hytrol 199-CRR usa cadena n.º 40 de rodillo a rodillo con pasos de 8p y 12p exactos, y **un lazo
  aparte n.º 60 del reductor al rodillo motriz**.
- Con dos piñones iguales, L = z + 2t/p. El paso de rodillos t tiene que ser múltiplo de p/2 con L
  par [D]:

  | piñón | t | L |
  |---|---|---|
  | Z14 | 76,2 | 26 |
  | Z14 | 101,6 | 30 |
  | Z15 | 95,25 | 30 |
  | Z15 | 107,95 | 32 |

## Decisiones

(Aprobadas por adelantado; las que la implementación corrija se anotan en la Bitácora.)

- **D1 — ASA (ANSI B29.1) es la norma por defecto, con su nombre local; ISO 606 B («BS») es la
  segunda familia.** Es lo que más se vende en Lima y lo que usa el rodillo a rodillo americano;
  la BS sirve para repuestos de máquinas europeas o chinas y para los cabezales tipo Interroll.
  Cada ref dice en su `description` que **ASA 40 y 08B no son intercambiables** aunque los dos
  sean de 1/2″, y el comando de cadena rechaza mezclarlas (D7).
- **D2 — 44 refs nuevas (256 → 300), en `111_cadenas_pinones.yaml`, categoría `transmision`
  (ya existe).** El prefijo 111 carga al final y no reordena el enum de `insert_component`;
  `transmision` ya va al subsistema «Transmisión» en `grouping.py` y `Tree.tsx`, así que la UI
  no se toca.
  - 6 cadenas: `CADENA-ASA40-1`, `CADENA-ASA40-2`, `CADENA-08B-1`, `CADENA-08B-2`,
    `CADENA-10B-1`, `CADENA-12B-1`.
  - 38 piñones, todos de la tabla de arriba:
    - ASA 40-1 tipo B ×11: `PINON-ASA40-1-Z15`…
    - ASA 40-2 dúplex ×2: `PINON-ASA40-2-Z14`, `-Z15`.
    - ASA 40 doble-simple ×1: `PINON-ASA40-DS-Z15`.
    - 08B-1 ×13.
    - 08B-2 ×7.
    - 08B-1 doble-simple ×1: `PINON-08B-DS-Z14`.
    - 10B-1 ×2.
    - 12B-1 ×1.
  - Nombres como en la tienda: «Piñón ASA 40-1 Z15 (tipo B)», «Cadena ASA 40-1».
  - Fuera de v1, por falta de datos de cubo verificados: ASA 35/50/60/80 y 06B/16B.
- **D3 — Lo no publicado se declara, no se disimula** (como D3 de garruchas). Cada ref lleva
  `no_publicado: "…"` en specs con lo [E] y el YAML comenta la fuente de cada valor. El piloto se
  rotula «agujero piloto, a maquinar con chaveta y prisionero» (`piloto_mm`, `agujero_max_mm` en
  specs).
- **D4 — Sin `cost`.** Los precios de Rodasur son de otra marca (Donghua), sin IGV claro y con la
  unidad de la cadena dudosa; quedan en el comentario del YAML. El costeo cae a su estimación por
  peso y la declara.
- **D5 — Builders en un módulo nuevo, `library/builders_transmision.py`.**
  - `sprocket`: dientes con la forma ISO 606. d0, de, df, ancho de diente, cubo, largo y piloto
    son reales; los flancos son representativos (radio re máx y ri mín). Una, dos hileras
    (dúplex, a pt) o doble-simple (dos placas a su distancia). Un solo sólido. **Marco
    canónico**: origen en el eje, en el plano medio de la hilera 1; eje +Z; el cubo hacia −Z; un
    asiento de diente centrado en +X.
  - Geometría de eslabón para la cadena (placa interior/exterior en estadio, rodillo, perno), la
    usa el comando de D7.
  - La matemática pura va en `library/transmision.py`: d0, de, eslabones ↔ centros, el camino de
    paso y las posiciones de los rodillos, la tabla de potencia y los factores. La usan el
    executor y la regla, y no duplican cuentas.
- **D6 — Anclas por familia.** Los piñones publican:
  - `eje`;
  - `hilera_1` y, si tiene dos, `hilera_2` (origen en el plano medio de cada hilera, eje +Z);
  - `fase` (origen en el centro de un asiento a radio d0/2; da el ángulo de los dientes).

  `component_anchors` acepta anclas calculadas desde los params de la familia, sin romper las de
  categoría (`library/catalog.py`, que no está congelado).
- **D7 — Comando `create_chain` («Cadena»), RELACIONAL entre dos piñones existentes.** Params:
  `name`, `cadena` (ref), `pinon_a`, `pinon_b` (feature ids; A = motriz), `hilera_a`/`hilera_b`
  (1 o 2, default 1), `detalle` (`eslabones` | `simple`, default `eslabones`), `potencia_kw` y
  `rpm_a` (opcionales, aceptan `=expr`) y `servicio` (`suave` | `moderado` | `fuerte`, default
  `moderado`).
  - Cada regenerate lee las anclas VIVAS de los dos piñones: si la variable que mueve un rodillo
    cambia, la cadena la sigue.
  - Valida y rechaza con su corrección:
    - misma norma y paso que la cadena (mezclar ASA con BS → error que dice «no son
      intercambiables»);
    - ejes paralelos (≤ 0,5°);
    - hileras coplanares (≤ 1 mm, con el desfase medido);
    - centros mayores que (de_a + de_b)/2 + holgura;
    - cadena doble sólo sobre dúplex; doble-simple con cadena simple.
  - **Eslabones** = el menor número PAR cuyo centro exacto es ≥ C. El resto se publica como
    holgura, no se esconde.
  - **Geometría**: los rodillos de la cadena caen en los ASIENTOS de cada piñón (los da su ancla
    `fase`) dentro del arco abrazado; los tramos rectos reparten los eslabones restantes. Así no
    interfiere con los dientes por construcción, aunque los piñones tengan cualquier fase. Va
    construida en un marco local y colocada con matriz, con `mesh_key` compartido entre lazos
    idénticos: un transportador de 30 lazos tesela una sola vez. `simple` = una banda envolvente
    por hilera, para máquinas grandes.
  - **Una Feature** con `component` = la ref de la cadena y `cut_length` = eslabones × p: la BOM
    pesa por kg/m y muestra el largo (más los eslabones, si `bom.py` lo admite sin crecer
    congelados).
  - Declara `fasten` contacto cadena ↔ cada piñón (`{cmd}_a`, `{cmd}_b`): la sujeción queda
    declarada (la cadena cuelga de sus piñones) y la puerta de entrega no la cuenta como choque.
- **D8 — `registry.py` no crece.** El executor nuevo va en `commands/exec_transmision.py` y sus
  params en `commands/models_transmision.py`. Para que quepan la línea de `CommandSpec` y el
  import, se SACAN de `registry.py` los executors de `create_take_up` y `create_drive_roller` a
  `commands/exec_rodillos.py`, sin cambiar su código. Si la huella cambia por la mudanza, se
  actualiza sólo la huella (refactor), sin subir versión. Pista nueva en `pistas.py`.
- **D9 — Regla «Transmisión por cadena»** en `library/engineering/cadena.py` (pura), llamada desde
  `services/engineering_rules.structure_rules`. Recalcula cada `create_chain` del log con la
  matemática de D5 (no guarda estado nuevo). Por cadena, un bloque `calc`:
  - **ERROR** si los eslabones son impares (no debería pasar) o si el abrazamiento del piñón chico
    es < 120°.
  - **AVISO** si z_chico < 17, la relación es > 7,6 o la holgura de redondeo supera el 4 % del
    vano. También si C queda fuera de 30–50 p, **salvo en los lazos 1:1 cortos** (rodillo a
    rodillo, por diseño a 6–12 p): ahí no se avisa.
  - **Potencia** sólo con `potencia_kw` y `rpm_a`: P·f_servicio ≤ P_nominal(z, rpm) × factor de
    hileras, interpolando la tabla ACA de la ASA 40-1. Para 08B se usa la tabla de la ASA 40-1
    como sustituto DECLARADO (la 08B-1 es más fuerte: 17,8 contra 13,9 kN), con
    norma «ASME B29.1 (tabla ACA)». 10B/12B, o rpm fuera de la tabla → `no_aplica` con su
    motivo; jamás se inventa una capacidad.
  - Siempre informa la velocidad de la cadena y, si pasa de 4 m/s, el aviso de lubricación.
- **D10 — `transmision` entra a `FEA_HARDWARE_CATS`** (no a `HARDWARE_CATS`). Piñones y poleas son
  geometría representativa: mallarlos mentiría rigidez. Su peso entra como carga sustituta,
  como el resto del herraje.
- **D11 — Sin bump de `GEOM_CACHE_EPOCH` ni de versiones.** Sólo se agregan refs, builders que
  ninguna ref existente usa y un comando nuevo. La mudanza de D8 no cambia geometría.
- **D12 — No hay tool MCP nueva** (MCP fino: `run_command` cubre el comando). Si el golden
  congela la lista de comandos o de catálogo, se re-congela a propósito.

## Alternativas descartadas

- **La cadena como componente cortable insertado con `insert_component`**: saldría recta; un lazo
  depende de dónde están los dos piñones.
- **Que el comando de cadena cree también sus piñones**: en rodillo a rodillo cada rodillo lleva
  UN piñón doble-simple compartido por dos lazos; la BOM listaría dos simples por rodillo, que no
  es lo que se compra.
- **Girar el piñón B para que engrane**: mutaría una pieza de otro comando. Asentar los rodillos
  de la cadena en los asientos de cada piñón da el mismo resultado sin tocarlo.
- **Rodillos de catálogo con cabezal de piñón (Interroll)**: en Lima se suelda un piñón al tubo;
  rodillo + piñón doble-simple soldado (`fasten` soldadura) es lo que el taller fabrica y cotiza.
- **Potencia de 08B por la gráfica de Renold**: no es un dato publicado como número.
- **Agregar la transmisión como opción de `create_conveyor`**: no expone el largo del rodillo y
  ataría la cadena a una sola máquina; el comando relacional sirve también para la mezcladora o
  un motor → eje.

## Fases

**F0 — Investigación y lectura del código** (hecha; es este documento).

**F1 — Catálogo** (`library` · M · depende de F0). Entra:
- el YAML de D2/D3;
- `builders_transmision.py` y `transmision.py` (D5);
- las anclas por familia (D6) y `FEA_HARDWARE_CATS` (D10);
- conteos: `test_catalog_datadriven` y el CLAUDE.md raíz.

Tests en `tests/test_catalog_cadenas.py`:
- las 44 refs cargan, son `transmision`, tienen `weight > 0` y construyen con `volume > 0`;
- d0 y de del sólido (bbox) = tabla ± 0,5 mm;
- ancho de diente y cubo reales; un dúplex tiene dos hileras a pt;
- las anclas `eje`/`hilera_k`/`fase` en el marco canónico;
- d0 = p/sin(180/z); eslabones ↔ centros ida y vuelta;
- la tabla ACA interpola bien y fuera de rango da None;
- el loader rechaza un builder repetido.

**F2 — Comando y regla** (`commands` + `library/engineering` + `services` · M/L · depende de F1):
`create_chain` (D7, D8) y la regla (D9). Tests en `tests/test_cadena.py`:
- dos piñones por `insert_component` en ejes paralelos + `create_chain`: eslabones pares, largo
  = L·p, dos `fasten` contacto declarados;
- interferencia cadena ↔ piñón dentro de la tolerancia con fases arbitrarias;
- editar la variable de los centros mueve la cadena en el regenerate;
- errores: ASA con BS, ejes no paralelos, hileras desfasadas, centros chicos, cadena doble sobre
  piñón simple;
- un lazo 1:1 Z15 a 95,25 mm da 30 eslabones sin holgura;
- `mesh_key` compartido entre dos lazos iguales;
- la regla: ERROR con abrazamiento < 120° y AVISO con z < 17; la potencia con la tabla, ok y
  excedida; `no_aplica` en 10B; ningún aviso de centros en un lazo 1:1 corto;
- `/api/checks` la muestra;
- `test_contrato_comandos` verde (D11), pista presente y golden MCP re-congelado si hace falta.
- Medir: tiempo de regenerate y teselado de 30 lazos con `eslabones` contra `simple`. Si
  `eslabones` pasa de ~5 s en total, el default cambia a `simple` y se anota.

**F3 — Verifica** (S · depende de F2).
- La sesión principal revisa el diff, re-corre pytest + ruff (y `npm test` + `npm run build` si
  se tocó `ui/`) y mergea.
- Con la API reiniciada desde el árbol principal, demo por MCP: motorreductor + 2 piñones + cadena
  ASA 40-1. Debe dar `delivery_check` verde, la regla en `engineering_check` y un render aislado.
- Las reglas durables van a `library/CLAUDE.md` y `commands/CLAUDE.md` en una línea cada una; se
  actualizan conteos y la Bitácora.

## Lo que este plan NO hace

- No incluye ASA 35/50/60/80 ni 06B/16B (v2, cuando haya datos de cubo verificados).
- No hace tensores ni patines de cadena, ni eslabón acodado (impares).
- No anima la cadena en el estudio de movimiento: los piñones giran con sus juntas y la cadena
  queda en su pose de diseño.
- No modela el chavetero ni el prisionero: se rotulan (D3).
- No incluye guardas de cadena de catálogo (se modelan como chapa), cotización firme ni el
  transportador piloto, que es trabajo de modelado de [publicacion-tienda](publicacion-tienda.md)
  una vez esto esté en `main`.

## Riesgos

| riesgo | mitigación |
|---|---|
| Muchos eslabones vuelven lento el regenerate o el render | Instancias por `mesh_key` (D7) y `detalle: simple`; F2 mide 30 lazos y cambia el default si hace falta |
| Datos [E] tomados como verdad | `no_publicado` en specs y comentario de fuente en el YAML (D3); el piloto se maquina |
| Choque de huella en `test_contrato_comandos` por la mudanza de D8 | Se actualiza sólo la huella, porque no cambió la geometría |
| El golden del MCP o un conteo de UI congela la lista de comandos | Re-congelar a propósito; revisar el diff del golden |
| La UI no ofrece selector de pieza para `pinon_a`/`pinon_b` | Declarar los campos como lo hace `snap_to` con su `target`; si la UI no los soporta, se anota y queda para el agente (es su usuario principal) |
| Un piñón que se mueve DESPUÉS de la cadena en el log no arrastra la cadena | El orden del log manda: se documenta en la pista; el agente coloca los piñones antes |

## Bitácora

### F2 (2026-10-08): `create_chain` y su regla — en `main`

- Implementó un subagente en un worktree. La sesión principal hizo cherry-pick a su worktree
  (sin choques), re-corrió pytest (**2517 passed, 5 skipped**, 7:35) y ruff (verde), corrigió
  los conteos del CLAUDE.md raíz (2522 tests, 54 comandos) y mergeó `--ff-only`.
- Archivos:
  - `commands/exec_transmision.py` (269 líneas);
  - `models_transmision.py` (93);
  - `exec_rodillos.py` (47);
  - `library/engineering/cadena.py` (171);
  - `services/transmision_rules.py` (72);
  - 35 tests en `tests/test_cadena.py`.

  `registry.py` baja de 2207 a 2185 (D8). Las huellas de los executors mudados no cambiaron:
  sólo entró la de `create_chain` (v1). El golden del MCP no cambió.
- **Medido** (30 lazos 1:1 Z15 doble-simple a 95,25, hileras alternadas):
  - `eslabones`: 0,5 s de regenerate + 3,2–3,9 s de teselado, ~4,5 s en el peor caso;
  - `simple`: 0,06 + 0,5 s.

  El default sigue en `eslabones`, pero justo bajo el umbral.
  - `Shape.moved` de build123d copia el BRep entero y lo descarta. `kernel/shapes.place_matrix`
    coloca compartiendo la TShape: 30 lazos bajaron de 1,45 a 0,47 s.
- **Correcciones a D7–D9:**
  - `simple` NO es una banda por hilera, que cortaría los dientes: son las bandas de placas a
    cada lado de los dientes, sin interferencia, igual que la cadena completa.
  - Lazos idénticos van en UNA regla: 30 páginas iguales ahogaban la memoria.
  - La «holgura > 4 % del vano» se lee como flecha del ramal flojo (Tsubaki); leída literal,
    no podía dispararse nunca.
  - `no_aplica` va en su campo y `estado` sigue en ok/aviso/error, para que la memoria y la UI
    no cambien.
  - Aviso nuevo: un piñón movido después de la cadena en el log. Un piñón ubicado con `add_mate`
    tampoco arrastra la cadena, porque los mates se resuelven al final del regenerate. Va en la
    descripción del comando.
  - La pista admite sólo una frase de ≤ 120 caracteres: la guía de montaje (piñones primero,
    ASA vs BS, eslabones pares, pasos de rodillo Z14 → 76,2/101,6 y Z15 → 95,25/107,95) quedó
    en la descripción del comando, que es la que lee el agente.
  - La UI ofrece selector de pieza sólo en campos llamados `feature`/`target`
    (`ui/src/forms/SchemaForm.tsx:36`): `pinon_a`/`pinon_b` salen como texto.
- Salida de la regla:
  - lazo 1:1 Z15 a 95,25: AVISO por z < 17; 30 eslabones sin holgura, 180° de abrazamiento, sin
    aviso de centros;
  - Z15 → Z30 con 0,37 kW a 100 rpm y C = 516,6: 104 eslabones, 173°, 0,32 m/s, FS de potencia
    1,09.
- Pendiente fuera de alcance: `api/scene._cached_render` recalcula el volumen de cada pieza
  instanciada (~1,6 s del teselado de 30 lazos); se podría cachear por `mesh_key`.

### F1 (2026-10-08): catálogo — en `main` (`b28692b`)

- Implementó un subagente en un worktree. Su rebase chocó con `4b49d62` (otra sesión puso V8 en
  la línea «Estado actual»): la sesión principal trajo el commit por cherry-pick a su worktree,
  combinó la línea (V8 + 300 refs + 2416 tests), re-corrió pytest (**2411 passed, 5 skipped**,
  5:16) y ruff (verde) y mergeó `--ff-only`.
- Archivos:
  - `library/transmision.py` (406 líneas, matemática pura);
  - `builders_transmision.py` (298);
  - `111_cadenas_pinones.yaml` (201, 44 refs);
  - `tests/test_catalog_cadenas.py` (176 tests).

  `loader.ANCLAS` une las anclas por familia con la misma regla que los builders (repetida o
  huérfana = error). `Component.anchors` se llena al cargar; `component_anchors` suma categoría
  + familia, así que las anclas de las garruchas siguen intactas.
- Medido: piñón z14 0,08 s, z30 0,16 s, z60 0,33 s, dúplex 0,12 s; tramo recto de 40 eslabones
  0,5 s; un lazo de 70 eslabones fusionado ~1,1 s, sin fusionar ~0,15 s.
- **Lo que corrigió la implementación:**
  - **Ángulo de asiento**: el MÁXIMO (140°−90°/z). Con el mínimo, los dientes ASA terminan en
    punta antes de llegar al exterior publicado.
  - **Rodillos de la cadena**: asentarlos hasta los puntos de tangencia del círculo primitivo los
    mete en los dientes. Ahora siguen el casco convexo de los asientos de los dos piñones. La
    holgura se cuelga hacia afuera con cuerdas de exactamente un paso. Si las fases no dejan
    cadena para un tramo recto, el estiramiento va a los rodillos del medio y se publica en
    `separacion_max` (hasta ~14,3 mm en lazos 1:1). Interferencia rodillo ↔ diente: cero en 96
    lazos con fases al azar.
  - **Cubos publicados más grandes que el paso libre de la cadena**: `PINON-ASA40-1-Z12` (Ø39,7,
    confirmado en Tsubaki) y `PINON-08B-1-Z9` (Ø24) solapan una cadena de placas en estadio
    (253 y 13 mm³). Queda declarado en su `no_publicado` y fijado por un test.
  - **Dúplex**: entre hileras se usa el Ø del cubo, no el Ø de garganta ISO.
  - **Valores [D] nuevos**: 08B-2 Z21 de = 92,58 (ISO da máx); ancho de diente ASA 40-2 = 7,07
    (fórmula ANSI).
  - **Pesos [E]**: volumen × 7,85e-6. El 3D reproduce los pesos publicados dentro del ±5 %.
  - **Specs nuevas** para que el comando las compare: `serie`, `cadena` (la ref compatible) y
    `tipo`.
- No hay test que dependa de que las poleas se mallen (D10). No se pudo revisar si el grupo FEA
  del 38 tiene una polea: el 38 no está en esta PC.
