# Catálogo de Datos y Entregables del Proyecto

Los archivos consolidados de resumen se encuentran en esta carpeta (`data/summary/`), mientras que los padrones masivos con el detalle individual suministro por suministro se gestionan en almacenamiento local / data lake debido a su tamaño:

## 📊 Tablas de Resumen Incluidas en el Repositorio
1. `data/summary/resumen_comparativo_grupos_distrito1.csv`:
   - Comparativa integral Antes vs Después de los 20 grupos cíclicos de lectura (1.941 rutas anteriores -> 3.669 rutas nuevas).
2. `data/summary/resumen_auditoria_calles_wfs_por_grupo.csv`:
   - Métrica de coincidencia de direcciones contra la capa WFS `EPEC:vm_manzanas_calles_new` por cada grupo de lectura.
3. `data/summary/resumen_todas_rutas_nuevas_distrito1.csv`:
   - Matriz detallada de las 3.669 rutas con cantidad de suministros, manzanas involucradas, barrios y centroides GPS.
4. `data/summary/resumen_rutas_propuestas_g16.csv`:
   - Detalle del caso piloto Grupo 16 (286 nuevas rutas).

## 💾 Padrones Completos Generados (Disponibles Localmente)
- `padron_distrito1_auditado_calles_wfs.csv` (159,40 MB, 585.472 filas):
  - Ubicación local: `C:\Users\jidiaz\Downloads\padron_distrito1_auditado_calles_wfs.csv`
  - Contiene los 585.472 suministros con sus atributos comerciales, el nuevo identificador catastral unificado, la nueva ruta, el nuevo orden de lectura secuencial y las 6 columnas de auditoría cruzada WFS.
- `padron_nuevas_rutas_distrito1_completo.csv` (95,17 MB, 585.472 filas):
  - Ubicación local: `C:\Users\jidiaz\Downloads\padron_nuevas_rutas_distrito1_completo.csv`
- `EPEC_vm_manzanas_calles_new.csv` (24,18 MB, 267.767 filas):
  - Copia local de la capa WFS completa provincial descargada de GeoServer.
