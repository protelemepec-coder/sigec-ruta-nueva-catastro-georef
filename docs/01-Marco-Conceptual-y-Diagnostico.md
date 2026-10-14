# 01. Marco Conceptual y Diagnóstico Inicial

## 1. El Problema de las Rutas de Lectura en SIGEC
En la base de datos comercial y técnica de EPEC (`georef.vw_suministros`), los suministros se organizan tradicionalmente en:
- `distrito` (ej. 1 = Córdoba Capital)
- `grupo_lectura` (ciclo comercial o día hábil de facturación, ej. 01 al 20)
- `ruta_lectura` (código numérico o alfanumérico arbitrario)
- `orden_lectura` (secuencia entera del recorrido del lecturista)

### Deficiencias Detectadas:
1. **Extrema Heterogeneidad**: Coexisten rutas con 10 suministros junto a macro-rutas de más de 1.000 suministros, imposibles de completar en una jornada de 6 horas.
2. **Saltos Geográficos**: Suministros pertenecientes a una misma ruta se ubican en extremos opuestos del barrio o en barrios no colindantes.
3. **Falta de Identidad Catastral**: Las rutas no guardaban relación con la división parcelaria provincial de la Dirección General de Catastro y Rentas de Córdoba.
