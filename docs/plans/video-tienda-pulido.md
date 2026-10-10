---
estado: en curso   # implementado | en curso | sin verificar | descartado
nota: Sólo el plan; nada construido. Espera saldo de tokens. La música la consigue Mario (con su licencia)
descripcion: El video de la tienda explica la máquina con sus datos de ingeniería, corta las etapas con ritmo parejo y se ve como un producto terminado
---

# El video de la tienda se ve y se lee como un producto

## Estado y origen

Primera corrida real de [publicacion-tienda](publicacion-tienda.md) F5 sobre la piloto (proyecto
2, revisión 4), el 2026-10-10: `publicar guion` + `publicar generar` sin música → video de 75 s
(2250 fotogramas), zips de 2.9 y 4.3 MB, puerta VERDE. Tiempos: abrir y validar 15.7 s, puerta
25.2 s, entregables 429.7 s, video 138.6 s. Mario: «ya vi y me gustó, y también acepto tus
recomendaciones, pero encárgate tú, el sonido lo voy a encontrar yo. Crea planes, cuando
tengamos tokens, implementamos cambios».

## El problema / lo que hay hoy

Revisado cuadro por cuadro (fotogramas 150, 750, 1350 y 2100):

1. **Los rótulos cuentan piezas, no explican**: «Se suman 2 largueros, «Eje del rodillo», «Tubo
   del rodillo» y 4 piezas más» (`services/rotulos.py:117` `texto_etapa`). No dicen nada que
   le sirva a quien va a fabricar o comprar.
2. **Etapas mal cortadas**: 3 etapas para 99 pasos visuales; la primera dura 29 s y sólo muestra
   dos largueros y un rodillo; un título se corta («Patas y travesaños, Motorreductor y 2…»).
   Capítulos: 00:00, 00:29, 00:43, 00:56 (`services/construccion.py:252` `etapas`).
3. **Aristas rojas en todas las piezas**: el render vivo dibuja las aristas de feature con el
   color de acento (`kernel/render_vivo.py:287`, `actor_aristas` de `render_comun`). Parece CAD
   en depuración, no un producto.
4. **Cierre ilegible**: «Descarga los planos y el modelo 3D» en blanco sobre fondo claro y
   encima de la máquina.
5. **Sin DWG**: el export pide ODA File Converter (gratuito); los PDF sí salen.
6. **Entregables lentos**: 430 s de 610; el video sólo 139 s.

## Decisiones (para vetar)

- **D1. Rótulos con datos de ingeniería**: cada etapa dice QUÉ y POR QUÉ con cifras del modelo:
  catálogo (perfil, Ø de rodillo, serie de cadena, motor kW/rpm), variables (paso, largo, altura)
  y cálculos ya hechos (factor de seguridad de la cadena, flecha). Plantillas por rol en
  `services/rotulos.py` (p. ej. rodillos → «20 rodillos Ø2″ cada 95 mm sobre ejes fijos M12»);
  sin plantilla, el texto de hoy. Máximo 2 líneas.
- **D2. Ritmo parejo**: etapas por GRUPO del documento (Bastidor, Rodillos, Cadenas, Patas,
  Motorreductor, Guardas), con mínimo 6 s y máximo 15 s por etapa; un patrón (20 rodillos)
  aparece en un solo paso con crecimiento rápido, no 20 pasos lentos. Títulos ≤ 32 caracteres,
  sin «y 2 más»: si no caben, se nombra el grupo.
- **D3. Aspecto de producto**: aristas gris oscuro y finas (o ninguna) en el video; el acento de
  color queda sólo para la pieza que entra. Los materiales salen de la tabla única de
  [visor-realista](visor-realista.md) D5 cuando exista; mientras, colores del documento.
- **D4. Cierre legible**: el texto final va en el panel inferior (el mismo del rótulo), con
  contraste mínimo 4.5:1, y la máquina gira completa en la parte superior.
- **D5. DWG como requisito chequeado**: `publicar guion` avisa al empezar si falta ODA (no al
  final, tras 7 minutos) con el enlace de descarga; sin ODA el zip sale sin DWG y lo dice.
- **D6. Entregables en paralelo con el video** si el lock lo permite (el render es fuera de
  `STATE_LOCK`); medir primero qué entregable se lleva los 430 s.
- **D7. La música la pone Mario** con `--musica` y sus datos de licencia en `ficha.yaml`; el plan
  no busca pistas.

## Fases

- **F0 (S, sólo lectura)**: perfilar los 430 s de entregables; contar pasos por grupo de la
  piloto para fijar los topes de D2.
- **F1 (M, `services`)**: D1 y D2 con tests sobre la piloto (títulos ≤ 32, ninguna etapa > 15 s,
  rótulo de rodillos con Ø y paso).
- **F2 (S, `kernel/media`)**: D3 y D4, con captura comparada.
- **F3 (S, `publicacion` + script)**: D5 y D6.
- **F4 (S, verificación)**: regenerar el video de la piloto con la música de Mario; lo juzga él.

## Lo que este plan NO hace

- La máquina andando al final del video: es [visor-realista](visor-realista.md) F4.
- Voz en off, subtítulos en otros idiomas y subida automática a YouTube (D15 de
  publicacion-tienda: manual).

## Riesgos

- Rótulos con cifras equivocadas → sólo cifras leídas del documento o del catálogo, nunca
  escritas a mano; test que compara cada cifra con su fuente.

## Bitácora
