---
estado: en curso
nota: contrato escrito 2026-10-29; F1 sin lanzar
descripcion: La BOM sirve para comprar y para cortar: cada chapa con su espesor, cada perfil con el corte medido, cada perno con su arandela y su tuerca una sola vez
---

# La BOM sirve para comprar y para cortar, sin leer el nombre de la pieza

## Estado y origen

Tanda de 6 pilotos de familia (2026-10-28/29: tolva, carro, mesa de trabajo, soporte de paneles,
rack, rodillos por cadena). Las re-revisiones de taller a ciegas, con la puerta v19 APROBADA, siguen
dejando MEDIA que NO son de cada máquina sino de la fábrica; se repiten en casi todas y ningún
modelador las puede corregir desde fuera. Regla de Mario: «defecto visto → arregla la fábrica»
(determinista, para todas las PCs).

## El problema / lo que hay hoy

Medido en los reportes de `rerevisor1` de `C:\t\maq\<slug>\` (sólo lectura):

1. **Chapa a medida sin espesor ni norma en la BOM** (tolva: «las filas A-MEDIDA de chapa sólo traen
   longitud_mm y material acero, sin espesor, grado ni norma»; rack: montante de chapa plegada «ref
   A-MEDIDA, norma vacía»). La lista de corte ya mide la chapa (`Feature.chapa`,
   [lista-de-corte-medida](lista-de-corte-medida.md) F1), la BOM no la lee.
2. **El ángulo medido no llega a la BOM** (rack: «c30 dice L=765.4 ∠33.2°/33.2° y c32_1, la misma
   pieza, L=765.4 sin ángulo»; paneles: dos filas para la misma diagonal, una con ∠17.7° y otra
   recta). Es la decisión F1-i de lista-de-corte-medida («el BOM no cambia»): las copias de un
   patrón no heredan `miter` y la BOM agrupa por lo declarado (`library/bom.py:101`).
3. **Piezas distintas en una fila** (paneles: «ANG-75X6 L=706.8, cant. 3» con taladros distintos en
   cada una): la BOM agrupa por ref + largo + ∠, no por la pieza que se fabrica.
4. **Tuerca repetida** (carro: 8 «TUERCA-M10 DIN 934 (unión declarada sin pieza modelada)» además
   de las 8 DIN 985 modeladas: la BOM compra 16 tuercas para 8 pernos): `tornilleria_declarada.py`
   no reconoce como suya la tuerca modelada de otra norma.
5. **Sin arandelas** (rack, carro, tolva, paneles: «sin ninguna arandela en la BOM», EN 1090-2 la
   pide sobre agujero sobremedida y bajo vibración): `join_bolted` no pone arandela y el catálogo no
   tiene DIN 125 (los modeladores las agregan a mano o las olvidan).
6. **Pernos de un patrón «aislados»** (paneles: `check_assembly` da 26 piezas aisladas, las de los
   comandos fuente de cada unión con perno; las copias sí tienen su contacto).

## Decisiones (para vetar)

- **D1. Chapa en la BOM por su ficha**: una pieza con `Feature.chapa` sale con espesor, material con
  su norma (la del material resuelto) y su desarrollo (el MISMO de la lista de corte, una fuente:
  `chapa_ficha`).
- **D2. Corte medido en la BOM** (revierte F1-i de lista-de-corte-medida): la fila de un perfil de
  catálogo cortable lleva el largo exterior y los ángulos MEDIDOS (`cutlist_medida`), y agrupa por
  la medida; una copia de patrón agrupa con su original. Lo declarado se contrasta como en la lista.
- **D3. Agrupar por la pieza que se fabrica**: dos piezas a medida o cortadas de la misma ref que
  difieren en sus taladros (u otra operación) no comparten fila; cada una con su marca (pieza de
  plano). Criterio de igualdad = la firma geométrica que ya comparten las instancias (`mesh_key` +
  volumen), no el nombre.
- **D4. La tornillería declarada no duplica la modelada**: si una unión perno tiene su tuerca (o
  perno) modelada, de la norma que sea, no suma la declarada. Una fila por designación, como hoy.
- **D5. `join_bolted` con arandela**: refs DIN 125 (M6–M20, acero zincado e inox A2) en el catálogo
  y `join_bolted` pone arandela bajo la tuerca (y bajo la cabeza si el agujero es sobremedida o
  colisado: ISO 273 serie gruesa o ranura) por defecto, con el largo del perno recalculado con ella;
  `arandela: false` la quita (el default de un log viejo reproduce lo de antes: campo nuevo con
  default compatible, como `add_joint(arrastrar=False)`, y sube la `version` del comando sólo si el
  executor cambia lo que ya generaba). Opción `tuerca: "din985"` (autoblocante) para lo que vibra.
- **D6. Los pernos del comando fuente de un patrón llevan su contacto** como sus copias.

## Alternativas descartadas

- **Que cada modelador nombre espesor y ángulo en el nombre**: frágil, no lo lee ningún cálculo y
  ya falló en tres máquinas.

## Fases

- **F1 (M, `library` + `commands` + catálogo)**: D1–D6 con tests sobre los `.apolo` reales de la
  tanda (sólo lectura): la tolva da el espesor de cada chapa; el rack y los paneles dan una fila por
  pieza con su ∠; el carro compra 8 tuercas, no 16; un `join_bolted` nuevo trae arandelas en la BOM;
  los pernos fuente del patrón de paneles no salen aislados. Lo que hoy ya sale bien no cambia
  (testigos y listas existentes idénticas salvo lo que mentía).

## Lo que este plan NO hace

- Planos de despiece nuevos ni marcas en los planos (la marca de D3 sale en la BOM y el CSV).

## Riesgos

- **Que D3 parta en mil filas** piezas que sólo difieren por ruido de la geometría: tolerancia de
  volumen relativa y test con las 480 piezas de la clasificadora (las filas no pueden crecer salvo
  donde hay taladros distintos de verdad).
