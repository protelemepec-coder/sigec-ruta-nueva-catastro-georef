# 03. Algoritmo de Bin-Packing Espacial por Manzana Colindante

## 1. Parámetros de Capacidad
- Capacidad Objetivo ($C_{\text{target}}$): **180 suministros**.
- Tolerancia ($\Delta$): **±20 suministros** (Rango: **[160, 200]**).
- Masa Crítica de Aceptación ($C_{\text{crit}}$): **120 suministros**.

## 2. Barrido Geoespacial (Spatial Sweep)
Las manzanas se ordenan jerárquicamente por:
`[circunscripción, sección, latitud_centroide, longitud_centroide]`
Esto asegura continuidad física sin retrocesos.

## 3. Tratamiento de Casos
1. **Macro-Manzanas (>200 sum.)**: No se mezclan con otras manzanas; se subdividen internamente en $k = \lceil cnt / 180 \rceil$ rutas correlativas.
2. **Manzanas Estándar**: Se acumulan hasta alcanzar el umbral de [160, 200].
3. **Desbordes**: Si la ruta tiene $\ge 120$ suministros se cierra y abre nueva; si tiene $< 120$ se fuerza la inclusión para evitar micro-rutas.
4. **Orden de Lectura**: Dentro de cada ruta, se asigna `nuevo_orden_lectura = 1, 2, ... N` ordenando por `[mza, parc, calle, altura, suministro]`.
