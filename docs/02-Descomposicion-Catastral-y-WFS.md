# 02. Descomposición Catastral y Normalización WFS

## 1. Nomenclatura Catastral Oficial (16 Dígitos)
La columna `dc` en `georef.vw_suministros` responde al estándar de Rentas de la Provincia de Córdoba:
`DD-PP-LL-CC-SS-MMM-PPP`

- `DD`: Departamento (11 = Capital, 31 = Santa María, 08/24 = Colón).
- `PP`: Pedanía (01 = Capital, etc.).
- `LL`: Pueblo / Municipio (01 = Córdoba Capital, etc.).
- `CC`: Circunscripción catastral.
- `SS`: Sección catastral.
- `MMM`: Manzana catastral (3 dígitos).
- `PPP`: Parcela catastral (3 dígitos).

## 2. Manzana Catastral Atómica (13 Dígitos)
`mza_13dig = DD + PP + LL + CC + SS + MMM`
Formato WFS interoperable: `DD-PP-LL-CC-SS-MMM` (clave primaria de la capa `EPEC:vm_manzanas_calles_new`).

## 3. Clave Unificada de Suministro
`ID_SUMINISTRO_CATASTRAL = DISTRITO-GRUPO_LECTURA-MANZANA_WFS-PARCELA`
Ejemplo: `1-16-11-01-01-31-04-003-018`.
