"""Neumática del catálogo (plan V8.9 D2, D3, D10, D15): ficha, caudal ISO 6358 y cálculo.

PURO: sólo la biblioteca estándar. No importa el resto de `apolo.library` (ni el catálogo ni la
geometría), ni `Document`, ni OCCT: así lo pueden leer el loader, los servicios y la memoria sin
arrastrar nada.

  - `iso6358`: el caudal de un orificio por ISO 6358-1:2013 (C y b) y las conversiones de
    entrada (Qn, área efectiva S, Kv y Cv) a (C, b);
  - `ficha`: el bloque `neumatico:` del YAML, validado al cargar (puertos ISO 5599-3, modelo por
    tipo, ajustes obligatorios, fuente);
  - `calculo`: fuerza, consumo isotermo, caudal pico, régimen con escape sónico, pandeo del
    vástago, energía de impacto y demanda de aire, cada uno con su bloque `calc`;
  - `bobinas` (F1b): la convención de bornes de las bobinas de una electroválvula (A1/A2;
    14A1…12A2) que une su ficha neumática con la eléctrica;
  - `lineas` y `erc` (F1b, D9): las líneas del circuito de aire del carril y su ERC.
"""
