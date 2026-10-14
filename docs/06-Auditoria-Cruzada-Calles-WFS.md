# 06. Auditoría de Control Cruzado con la Capa WFS

## 1. Capa WFS `EPEC:vm_manzanas_calles_new`
- Descargada en 2,69 segundos (24,18 MB, 120.263 registros únicos, 30.230 manzanas).
- Contiene los nombres oficiales de las calles perimetrales de cada manzana catastral.

## 2. Resultados sobre los 585.472 Suministros
- Suministros con manzana en WFS: **529.127 (90,4%)**.
- Suministros con calle confirmada en el perímetro: **464.990 (87,9% de las con WFS / 79,4% global)**.
  * Exacta o contenida: 420.558 (79,5%).
  * Token coincidente / normalización: 44.432 (8,4%).
- Discrepancias / Esquinas / Entradas técnicas: 64.135 (12,1%).
- En grupos urbanos históricos (01, 02, 04, 06, 10, 12, 18, 19), la coincidencia oscila entre el **95,5% y el 98,6%**.
