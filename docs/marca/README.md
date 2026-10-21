# Marca de Apolo

El ícono es **la A de taller**: una A blanca abierta (sin cerrar arriba, trazo de puntas
redondeadas) sobre un cuadrado redondeado azul; el travesaño ámbar es la cota del plano.

| color | hex | uso |
|---|---|---|
| azul Apolo | `#2c5fd4` | fondo (cuadrado de 64 con radio 14) |
| blanco | `#ffffff` | la A (trazo 6.5) |
| ámbar cota | `#f0b43c` | el travesaño (trazo 5.5) |

## Archivos

| archivo | qué es |
|---|---|
| `apolo-icono.svg` | **el maestro** (viewBox 64×64). Todo lo demás sale de aquí. |
| `apolo-icono-{16,32,48,180,192,256,512}.png` | PNG con transparencia en las esquinas (favicon, apple-touch, PWA, tienda) |
| `apolo-icono.ico` | ICO multi-tamaño 16/32/48/256, para el instalador de Windows |

La UI lleva su copia en `ui/public/`: `favicon.svg` (el maestro), `favicon.ico` (16/32/48) y
`apple-touch-icon.png` (180). Vite los copia a `dist/` y `scripts/stage_ui.py` al paquete.

## Regenerar

Los PNG y los ICO **no se editan a mano**: se cambia el SVG y se corre

```powershell
.\.venv\Scripts\python.exe scripts\generar_iconos.py
```

que lee la geometría del SVG, la dibuja a 1024 px con Pillow y reduce cada tamaño con LANCZOS.
Pillow es herramienta de desarrollo, no dependencia del paquete. `tests/test_marca.py` verifica
que la copia de la UI sea el maestro y que los tamaños estén completos.
