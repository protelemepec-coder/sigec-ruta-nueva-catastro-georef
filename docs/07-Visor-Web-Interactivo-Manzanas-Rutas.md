# 07 - Visor Web Interactivo de Manzanas Catastrales por Ruta de Lectura

**Distrito 1 (EPEC Capital y Periurbano)**  
**Fecha:** 2026-10-23  
**Tecnología:** HTML5, Vanilla CSS3 (Glassmorphism & Dark Theme), Leaflet JS (Canvas Renderer), GeoJSON optimizado.

---

## 1. Objetivo y Alcance

Permitir a los equipos de planificación, supervisores de lectura y auditores de campo inspeccionar visualmente en el navegador la contigüidad espacial de las **18.721 manzanas catastrales** asignadas a las **3.299 rutas nuevas de lectura** del Distrito 1 de EPEC (585.727 suministros), verificando que:
- Solo se dibujen los polígonos de las manzanas catastrales individuales (sin envolventes globales distorsionadas).
- Cada manzana esté pintada con el color único de su ruta de lectura mediante una paleta áurea de alto contraste.
- No existan solapamientos entre rutas en manzanas regulares.
- Se pueda inspeccionar cada manzana al clic (nomenclatura, ruta, ciclo, suministros, calles perimetrales y alturas).
- Se pueda aislar cualquier ruta completa para auditar su compacidad y frontera.

---

## 2. Arquitectura de Datos y Rendimiento

1. **Canvas Rendering a 60 FPS:**
   - La capa vectorial utiliza `L.canvas({ padding: 0.5, tolerance: 4 })` en lugar de SVG, evitando la sobrecarga de 18.000 nodos en el DOM y permitiendo un desplazamiento y zoom instantáneos.
2. **Optimización Topológica:**
   - Geometrías simplificadas mediante el algoritmo de Douglas-Peucker ($\sim 3$ metros de tolerancia) y redondeadas a 5 decimales de precisión ($\sim 1.1$ m), reduciendo el tamaño a solo 12.8 MB.
3. **Doble Mecanismo de Carga (Zero-CORS):**
   - Se distribuye como `data/manzanas_rutas_data.js` (`const MANZANAS_DATA = ...`), permitiendo abrir el archivo `index.html` directamente haciendo doble clic desde el Explorador de Windows (`file:///`) sin requerir un servidor web local ni configuración adicional.
   - También mantiene el archivo estándar `data/manzanas_rutas_distrito1.geojson` para consumo vía HTTP o clientes GIS como QGIS.

---

## 3. Funcionalidades de la Interfaz

- **Barra Superior Glassmorphic:**
  - Métricas en vivo: 18.721 Manzanas, 3.299 Rutas, 585.727 Suministros.
  - Buscador instantáneo por Número de Ruta (ej. `1042`), Nomenclatura de Manzana (ej. `11-01-01-05-23-013`) o Calle (ej. `DEAN FUNES`).
  - Filtro desplegable por Ciclo de Facturación (Ciclos 01 al 20).
  - Selector de modo de color: *Por Ruta (Áureo)*, *Por Ciclo (20 colores)* o *Por Densidad de Suministros*.
- **Panel Inspector Lateral:**
  - Muestra ficha técnica de la manzana seleccionada con etiquetas de calles perimetrales y rangos de altura.
  - Botón *"Aislar y Enfocar esta Ruta Completa"*: atenúa el resto del distrito y ajusta el zoom automáticamente a todas las manzanas de la ruta seleccionada.
- **Mapas Base:**
  - CartoDB Oscuro (predeterminado para máximo contraste).
  - CartoDB Claro.
  - OpenStreetMap.
  - Imagen Satelital de Alta Resolución (ESRI World Imagery).

---

## 4. Rutas de Acceso a los Entregables

- **Visor listo para usar (Downloads):**  
  `D:\Usuarios\jidiaz\Downloads\visor_manzanas_rutas\index.html`
- **Carpeta del Repositorio:**  
  `D:\Proyectos\sigec-ruta-nueva-catastro-georef\viewer\index.html`
- **Script Generador de Datos:**  
  `D:\Proyectos\sigec-ruta-nueva-catastro-georef\scripts\generate_manzanas_viewer_data.py`
