import os
import sys
import time
import json
import pandas as pd
import numpy as np

# Configure QGIS PROJ before geopandas/pyproj
os.environ['PROJ_DATA'] = r'C:\Program Files\QGIS 4.2.0\share\proj'
os.environ['PROJ_LIB'] = r'C:\Program Files\QGIS 4.2.0\share\proj'

import geopandas as gpd
from shapely.geometry import Point, box, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

t0 = time.time()
print("=" * 80)
print("EXTRACTOR Y ENSAMBLADOR DE MANZANAS CATASTRALES PINTADAS POR RUTA")
print("=" * 80)

# Paths
padron_path = r'D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\padron_nuevas_rutas_distrito1_completo.parquet'
maestro_path = r'D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\maestro_manzanas_calles_alturas.parquet'
mzas_geom_path = r'D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\manzanas_idecor_capital_4326.parquet'

out_viewer_dir = r'D:\Proyectos\sigec-ruta-nueva-catastro-georef\viewer\data'
out_dl_dir = r'D:\Usuarios\jidiaz\Downloads\visor_manzanas_rutas\data'
os.makedirs(out_viewer_dir, exist_ok=True)
os.makedirs(out_dl_dir, exist_ok=True)

# 1. Cargar Maestro de Manzanas
print("[1/5] Cargando maestro de manzanas con calles y alturas...")
maestro = pd.read_parquet(maestro_path, columns=['mza_wfs', 'distrito', 'grupo_lectura', 'cant_suministros', 'calles_perimetrales', 'mza_calles_con_alturas'])
print(f"      Maestro: {len(maestro):,} manzanas catastrales.")

# 2. Cargar Asignación de Rutas Dominantes
print("[2/5] Extrayendo nueva ruta de lectura por manzana...")
padron_rutas = pd.read_parquet(padron_path, columns=['mza_wfs_asignada', 'nueva_ruta_lectura'])
# Calcular ruta dominante por mayoría de votos
route_per_mza = padron_rutas.groupby('mza_wfs_asignada')['nueva_ruta_lectura'].agg(lambda x: int(x.mode()[0]) if not x.empty else 0).reset_index()
route_dict = dict(zip(route_per_mza['mza_wfs_asignada'], route_per_mza['nueva_ruta_lectura']))

# 3. Cargar Geometrías IDECOR
print("[3/5] Cargando geometrías oficiales IDECOR Capital...")
gdf_idecor = gpd.read_parquet(mzas_geom_path)
gdf_idecor['geometry'] = gdf_idecor['geometry'].map(lambda g: make_valid(g) if not g.is_valid else g)
idecor_dict = dict(zip(gdf_idecor['mza_wfs'], gdf_idecor['geometry']))

# 4. Procesar Manzanas Faltantes (periurbanas / nuevos loteos)
print("[4/5] Sintetizando geometrías para manzanas periurbanas no catalogadas...")
all_mzas = set(maestro['mza_wfs'])
missing_mzas = all_mzas - set(idecor_dict.keys())
print(f"      En IDECOR: {len(all_mzas & set(idecor_dict.keys())):,}")
print(f"      Periurbanas a sintetizar: {len(missing_mzas):,}")

if missing_mzas:
    padron_coords = pd.read_parquet(padron_path, columns=['mza_wfs_asignada', 'latitud', 'longitud'])
    padron_coords = padron_coords.dropna(subset=['latitud', 'longitud'])
    coords_missing = padron_coords[padron_coords['mza_wfs_asignada'].isin(missing_mzas)]
    
    # Agregar bounds por manzana
    bounds_df = coords_missing.groupby('mza_wfs_asignada').agg(
        min_lon=('longitud', 'min'),
        max_lon=('longitud', 'max'),
        min_lat=('latitud', 'min'),
        max_lat=('latitud', 'max'),
        cnt=('latitud', 'count')
    ).reset_index()
    
    for _, r in bounds_df.iterrows():
        m_id = r['mza_wfs_asignada']
        if r['min_lon'] == r['max_lon'] and r['min_lat'] == r['max_lat']:
            poly = Point(r['min_lon'], r['min_lat']).buffer(0.00035)
        else:
            poly = box(r['min_lon'] - 0.00015, r['min_lat'] - 0.00015, r['max_lon'] + 0.00015, r['max_lat'] + 0.00015)
        idecor_dict[m_id] = make_valid(poly)

# 5. Armar Colección GeoJSON Optimizada
print("[5/5] Ensamblando y optimizando GeoJSON (5 decimales y Douglas-Peucker 3m)...")

def round_coords(coords, precision=5):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], precision), round(coords[1], precision)]
    return [round_coords(c, precision) for c in coords]

def geom_to_clean_json(geom):
    if geom is None or geom.is_empty:
        return None
    # Simplificar ligeramente (0.00003 deg ~ 3 metros) para ultra-fluidez web
    s = geom.simplify(0.00003, preserve_topology=True)
    if s is None or s.is_empty:
        s = geom
    gj = mapping(s)
    if 'coordinates' not in gj:
        return None
    gj['coordinates'] = round_coords(gj['coordinates'], 5)
    return gj

features = []
skipped = 0

for _, row in maestro.iterrows():
    m_id = row['mza_wfs']
    geom = idecor_dict.get(m_id)
    if geom is None:
        skipped += 1
        continue
    
    gj_geom = geom_to_clean_json(geom)
    if gj_geom is None:
        skipped += 1
        continue
    
    r_id = route_dict.get(m_id, 0)
    
    # Propiedades concisas para rendimiento máximo
    props = {
        'm': m_id,
        'r': int(r_id),
        'g': str(row['grupo_lectura']),
        's': int(row['cant_suministros']),
        'c': str(row['calles_perimetrales']) if pd.notna(row['calles_perimetrales']) else '',
        'a': str(row['mza_calles_con_alturas']) if pd.notna(row['mza_calles_con_alturas']) else ''
    }
    
    features.append({
        'type': 'Feature',
        'geometry': gj_geom,
        'properties': props
    })

geojson_obj = {
    'type': 'FeatureCollection',
    'features': features
}

print(f"      Polígonos procesados: {len(features):,} (omitidos sin coords: {skipped})")

# Exportar GeoJSON minificado
raw_json_str = json.dumps(geojson_obj, separators=(',', ':'))

# Guardar en visor del repositorio
out_repo_geojson = os.path.join(out_viewer_dir, 'manzanas_rutas_distrito1.geojson')
out_repo_js = os.path.join(out_viewer_dir, 'manzanas_rutas_data.js')
with open(out_repo_geojson, 'w', encoding='utf-8') as f:
    f.write(raw_json_str)
with open(out_repo_js, 'w', encoding='utf-8') as f:
    f.write('const MANZANAS_DATA = ')
    f.write(raw_json_str)
    f.write(';\n')

# Guardar en Downloads para el usuario
out_dl_geojson = os.path.join(out_dl_dir, 'manzanas_rutas_distrito1.geojson')
out_dl_js = os.path.join(out_dl_dir, 'manzanas_rutas_data.js')
with open(out_dl_geojson, 'w', encoding='utf-8') as f:
    f.write(raw_json_str)
with open(out_dl_js, 'w', encoding='utf-8') as f:
    f.write('const MANZANAS_DATA = ')
    f.write(raw_json_str)
    f.write(';\n')

size_mb = len(raw_json_str) / (1024 * 1024)
print(f"      Tamaño archivo: {size_mb:.2f} MB")
print(f"      Exportado a:\n        - {out_repo_js}\n        - {out_dl_js}")
print(f"      Tiempo total de ejecución: {time.time() - t0:.2f} s")
print("=" * 80)
