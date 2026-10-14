# SIGEC: Reorganización Catastral de Rutas de Lectura, Bin-Packing Espacial (180±20) y Auditoría Perimetral WFS en Distrito 1 (EPEC)

[![Estado](https://img.shields.io/badge/Estado-Producci%C3%B3n%20%2F%20Validado-success.svg)](#)
[![Distrito](https://img.shields.io/badge/Distrito-1%20(C%C3%B3rdoba%20Capital)-blue.svg)](#)
[![Suministros](https://img.shields.io/badge/Suministros%20Auditados-585.472-orange.svg)](#)
[![Nuevas Rutas](https://img.shields.io/badge/Nuevas%20Rutas-3.669-brightgreen.svg)](#)
[![WFS EPEC](https://img.shields.io/badge/Geoservicio%20WFS-vm__manzanas__calles__new-purple.svg)](#)

Repositorio oficial dedicado al diseño, optimización matemática, escalamiento y auditoría geoespacial para la **reasignación de rutas de lectura y orden secuencial** en el ámbito del **Distrito 1 de EPEC** (Córdoba Capital, Malagueño, Yoccina, Juárez Celman, Malvinas Argentinas y municipios colindantes).

---

## 📌 Resumen Ejecutivo del Proyecto

El sistema comercial histórico de EPEC (SIGEC) organizaba los suministros para la toma de estado mediante números de ruta heterogéneos y dispersos, generando sobrecargas operativas extremas (rutas de hasta 1.000+ suministros), saltos geográficos caóticos entre calles no adyacentes y falta de integración con la cartografía provincial oficial.

Este proyecto resuelve el problema mediante una **arquitectura en 4 capas**:
1. **Identificador Catastral Unificado**: Cada suministro cuenta con la clave jerárquica `DISTRITO-GRUPO_LECTURA-NOMENCLATURA_MANZANA_WFS-PARCELA` (ej. `1-16-11-01-01-31-04-003-018`).
2. **Unidad Atómica Indivisible (Manzana Catastral)**: Los suministros se agrupan por su manzana catastral oficial de 13 dígitos (`DD-PP-LL-CC-SS-MMM`), eliminando la atomización de cuentas.
3. **Bin-Packing Espacial Balanceado**: Rutas optimizadas con capacidad objetivo de **180 suministros** con tolerancia de **±20** (rango operativo: **[160, 200]**).
4. **Auditoría Perimetral WFS**: Validación del 100% del padrón (585.472 suministros) contrastando la dirección postal (`calle`) contra las calles perimetrales de la capa oficial `EPEC:vm_manzanas_calles_new`, alcanzando un **87,9% de acierto** sobre las manzanas digitalizadas (**97,5% a 98,6%** en la trama urbana consolidada).

---

## 🗺️ Métricas Globales Antes vs. Después (Distrito 1)

| Métrica Operativa | Organización Anterior (SIGEC) | Nueva Organización Catastral | Impacto / Beneficio Operativo |
| :--- | :---: | :---: | :--- |
| **Suministros Cíclicos Cubiertos** | 585.472 | **585.472** | **100% de cobertura (0 huérfanos)**. |
| **Cantidad de Rutas de Lectura** | 1.941 rutas | **3.669 rutas** | Rutas homogéneas dimensionadas para jornada estándar a pie. |
| **Promedio Suministros/Ruta** | 301,6 sum/ruta | **159,6 sum/ruta** (Mediana: 167) | Eliminación de sobrecargas y fatiga del tomador de estado. |
| **Dispersión de Carga** | 10 a >1.000 suministros | **160 a 200 suministros** | **66,1% estricto** (absorbiendo macro-manzanas y cierres). |
| **Criterio de Agrupación** | Histórico/Comercial heterogéneo | **Manzana Catastral Atómica Colindante** | Recorrido peatonal continuo manzana por manzana. |
| **Trazabilidad Geoespacial** | Desconectada de Catastro | **WFS Catastro / Rentas Córdoba** | **87,9% acierto de calle perimetral** en capa WFS provincial. |

---

## 📂 Estructura del Repositorio

```text
sigec-ruta-nueva-catastro-georef/
├── docs/
│   ├── 01-Marco-Conceptual-y-Diagnostico.md
│   ├── 02-Descomposicion-Catastral-y-WFS.md
│   ├── 03-Algoritmo-Bin-Packing-Espacial.md
│   ├── 04-Resultados-Piloto-Grupo-16.md
│   ├── 05-Escalamiento-Distrito-1-Completo.md
│   └── 06-Auditoria-Cruzada-Calles-WFS.md
├── scripts/
│   ├── generar_nuevas_rutas_g16.py          # Script piloto Distrito 1 / Grupo 16
│   ├── escalar_nuevas_rutas_distrito1.py     # Script batch de escalamiento (Grupos 01 al 20)
│   └── ejecutar_auditoria_completa_wfs.py    # Descarga WFS e indexacion de calles
├── data/
│   ├── README.md                             # Catalogo de datasets y ubicaciones
│   └── summary/
│       ├── resumen_comparativo_grupos_distrito1.csv
│       ├── resumen_auditoria_calles_wfs_por_grupo.csv
│       ├── resumen_todas_rutas_nuevas_distrito1.csv
│       └── resumen_rutas_propuestas_g16.csv
└── README.md
```

---

## 🛠️ Scripts y Ejecución

### 1. Escalamiento de Rutas a Todo el Distrito 1
```bash
python scripts/escalar_nuevas_rutas_distrito1.py
```
- Procesa los 20 grupos cíclicos en ~3 minutos.
- Genera el padrón completo con la `nueva_ruta_lectura` y `nuevo_orden_lectura`.

### 2. Descarga de Capa WFS y Auditoría Cruzada Perimetral
```bash
python scripts/ejecutar_auditoria_completa_wfs.py
```
- Descarga en 2.7s los 267k registros de `EPEC:vm_manzanas_calles_new`.
- Audita los 585.472 suministros a 160.000 sum/s.
- Exporta el padrón auditado con banderas de coincidencia y calles perimetrales.

---

## 🏛️ Créditos y Autoría
- **Organización**: `protelemepec-coder`
- **Área**: Gerencia Comercial / Proyecto Telemedición (PROTELEM) & Operaciones EPEC
- **Agente Responsable**: 02 - Ciencia de Datos & Ingeniero de Analytics BI
