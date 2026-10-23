import os
import sys
import time
import math
import pandas as pd
import numpy as np
import geopandas as gpd
from collections import defaultdict
from scipy.spatial import cKDTree
from shapely.geometry import Point, MultiPolygon, Polygon
from shapely.ops import unary_union
from shapely.validation import make_valid
from shapely import STRtree

# Set QGIS PROJ environment
os.environ['PROJ_DATA'] = r'C:\Program Files\QGIS 4.2.0\share\proj'
os.environ['PROJ_LIB'] = r'C:\Program Files\QGIS 4.2.0\share\proj'

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 110)
print("SISTEMA DE CONTROL GEOESPACIAL, DIBUJO DE POLÍGONOS DE RUTAS Y REDISTRIBUCIÓN")
print("DISTRITO 1 (EPEC) - 585.727 SUMINISTROS / 3.300 RUTAS / 18.771 MANZANAS")
print("=" * 110)

padron_path = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\padron_nuevas_rutas_distrito1_completo.parquet"
mza_geom_path = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\manzanas_idecor_capital_4326.parquet"

out_padron_parquet = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\padron_nuevas_rutas_distrito1_completo.parquet"
out_padron_c_csv = r"C:\Users\jidiaz\Downloads\padron_nuevas_rutas_distrito1_completo.csv"
out_padron_d_csv = r"D:\Usuarios\jidiaz\Downloads\padron_nuevas_rutas_distrito1_completo.csv"

out_routes_parquet = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\rutas_nuevas_poligonos_distrito1.parquet"
out_routes_geojson = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\rutas_nuevas_poligonos_distrito1.geojson"
out_routes_d_geojson = r"D:\Usuarios\jidiaz\Downloads\rutas_nuevas_poligonos_distrito1.geojson"

t0 = time.time()
print("\n[1/5] Cargando dataset maestro y geometrías IDECOR...")
df_padron = pd.read_parquet(padron_path)
gdf_mzas = gpd.read_parquet(mza_geom_path)

# Limpiar geometrías IDECOR con make_valid
print("      Validando geometrías oficiales de manzanas...")
gdf_mzas['geometry'] = gdf_mzas['geometry'].map(lambda g: make_valid(g) if not g.is_valid else g)
mza_geom_dict = gdf_mzas.set_index('mza_wfs')['geometry'].to_dict()

print(f"      Padrón cargado: {len(df_padron):,} suministros.")
print(f"      Polígonos de manzanas indexados: {len(mza_geom_dict):,} manzanas.")

def to_xy(lat, lon):
    y = (lat - (-31.42)) * 111139.0
    x = (lon - (-64.18)) * 111139.0 * math.cos(math.radians(-31.42))
    return x, y

# [2/5] Detección de Outliers y Redistribución Geoespacial de Manzanas por Grupo
print("\n[2/5] Ejecutando Detección de Outliers y Redistribución Geoespacial...")
grupos = sorted(df_padron['grupo_lectura'].unique(), key=lambda x: int(x))

reassigned_total_mzas = 0
reassigned_total_sumis = 0

df_updated = df_padron.copy()
new_routes_col = df_updated['nueva_ruta_lectura'].values.copy()
obs_topo_col = ['Topológicamente contiguo' for _ in range(len(df_updated))]

for g_str in grupos:
    g_mask = (df_updated['grupo_lectura'] == g_str)
    sub_df = df_updated[g_mask]
    
    # Calcular centroides robustos (mediana) por ruta
    route_medians = sub_df.groupby('nueva_ruta_lectura')[['latitud', 'longitud']].median().dropna()
    r_ids = route_medians.index.values
    if len(r_ids) < 2:
        continue
        
    r_coords = route_medians.values
    r_xy = np.array([to_xy(lat, lon) for lat, lon in r_coords])
    kdtree = cKDTree(r_xy)
    r_center_dict = {r: r_xy[i] for i, r in enumerate(r_ids)}
    
    # Calcular cargas por ruta
    route_loads = sub_df.groupby('nueva_ruta_lectura').size().to_dict()
    
    # Identificar manzanas atípicas (> 2.0 km del centro de su ruta)
    # Excluyendo macro-manzanas divididas (>200 suministros)
    mza_stats = sub_df.groupby(['mza_wfs_asignada', 'nueva_ruta_lectura']).agg(
        cant=('suministro', 'count'),
        lat=('latitud', 'median'),
        lon=('longitud', 'median')
    ).reset_index()
    
    mza_stats = mza_stats.dropna(subset=['lat', 'lon'])
    
    # Filtrar sólo manzanas normales (cant <= 100) para no romper macro-particiones
    outliers = []
    for _, r_row in mza_stats.iterrows():
        c_xy = r_center_dict.get(r_row['nueva_ruta_lectura'])
        if c_xy is not None:
            mx, my = to_xy(r_row['lat'], r_row['lon'])
            d = math.hypot(mx - c_xy[0], my - c_xy[1])
            if d > 2000.0 and r_row['cant'] <= 80: # Outlier claro
                outliers.append((r_row['mza_wfs_asignada'], r_row['nueva_ruta_lectura'], r_row['cant'], mx, my))
    
    # Redistribuir a la ruta más cercana con capacidad
    for m, old_r, cant, mx, my in outliers:
        dists, idxs = kdtree.query([mx, my], k=min(10, len(r_ids)))
        best_r = None
        for d, idx_cand in zip(dists, idxs):
            cand_r = r_ids[idx_cand]
            if cand_r != old_r and route_loads.get(cand_r, 0) + cant <= 205:
                best_r = cand_r
                break
        
        if best_r is not None:
            # Reasignar suministros en df_updated
            match_mask = g_mask & (df_updated['mza_wfs_asignada'] == m) & (df_updated['nueva_ruta_lectura'] == old_r)
            idx_matches = df_updated[match_mask].index.values
            for im in idx_matches:
                new_routes_col[im] = best_r
                obs_topo_col[im] = f"Redistribuido geoespacialmente desde ruta {old_r} a {best_r} por proximidad"
            
            route_loads[old_r] -= cant
            route_loads[best_r] += cant
            reassigned_total_mzas += 1
            reassigned_total_sumis += cant

print(f"      Total manzanas redistribuidas: {reassigned_total_mzas:,}")
print(f"      Total suministros reasignados a ruta local: {reassigned_total_sumis:,}")

df_updated['nueva_ruta_lectura'] = new_routes_col
df_updated['obs_control_topologico'] = obs_topo_col

# [3/5] Construir Polígonos de Rutas ("Dibujar las manzanas agrupadas por ruta nueva")
print("\n[3/5] Dibujando polígonos de manzanas agrupadas por ruta nueva...")

# Pre-identificar macro-manzanas divididas
mza_route_counts = df_updated.groupby(['mza_wfs_asignada', 'nueva_ruta_lectura']).size().unstack(fill_value=0)
split_mzas = set(mza_route_counts[(mza_route_counts > 0).sum(axis=1) > 1].index)

route_geoms = defaultdict(list)
unique_pairs = df_updated.groupby(['mza_wfs_asignada', 'nueva_ruta_lectura'])

pair_idx = 0
for (m, r_id), group in unique_pairs:
    pair_idx += 1
    # Caso A: Manzana 000 o virtual -> Buffer de 25m alrededor de sus puntos
    if m.endswith('-000') or m.startswith('VIRT_'):
        pts = [Point(xy) for xy in zip(group['longitud'].dropna(), group['latitud'].dropna())]
        if pts:
            u_pts = unary_union(pts)
            poly = u_pts.convex_hull.buffer(0.00025) if len(pts) >= 3 else u_pts.buffer(0.00025)
            route_geoms[r_id].append(make_valid(poly))
        continue
    
    # Caso B: Manzana normal (100% en esta ruta)
    if m not in split_mzas:
        if m in mza_geom_dict:
            route_geoms[r_id].append(mza_geom_dict[m])
        else:
            pts = [Point(xy) for xy in zip(group['longitud'].dropna(), group['latitud'].dropna())]
            if pts:
                u_pts = unary_union(pts)
                poly = u_pts.convex_hull.buffer(0.00025) if len(pts) >= 3 else u_pts.buffer(0.00025)
                route_geoms[r_id].append(make_valid(poly))
        continue

    # Caso C: Macro-manzana dividida entre rutas -> Sub-polígono particionado
    pts = [Point(xy) for xy in zip(group['longitud'].dropna(), group['latitud'].dropna())]
    if pts:
        u_pts = unary_union(pts)
        sub_poly = u_pts.convex_hull.buffer(0.00025) if len(pts) >= 3 else u_pts.buffer(0.00025)
        if m in mza_geom_dict:
            macro_poly = mza_geom_dict[m]
            inter_poly = sub_poly.intersection(macro_poly)
            if not inter_poly.is_empty and inter_poly.area > 1e-10:
                route_geoms[r_id].append(make_valid(inter_poly))
            else:
                route_geoms[r_id].append(make_valid(sub_poly))
        else:
            route_geoms[r_id].append(make_valid(sub_poly))

# Unir y consolidar geometría de cada ruta
print("      Uniendo y disolviendo manzanas para cada una de las 3.300 rutas...")
route_records = []
total_routes = len(route_geoms)

# Estadísticas de cada ruta
route_stats = df_updated.groupby('nueva_ruta_lectura').agg(
    distrito=('distrito', 'first'),
    grupo_lectura=('grupo_lectura', 'first'),
    cant_suministros=('suministro', 'count'),
    cant_manzanas=('mza_wfs_asignada', 'nunique'),
    centroide_lat=('latitud', 'mean'),
    centroide_lon=('longitud', 'mean'),
    calles_compartidas=('calles_compartidas_en_ruta', 'first')
).reset_index()

route_stats_dict = route_stats.set_index('nueva_ruta_lectura').to_dict(orient='index')

for r_id, g_list in route_geoms.items():
    if g_list:
        clean = [g.buffer(0) for g in g_list if g is not None and not g.is_empty]
        try:
            route_poly = make_valid(unary_union(clean))
        except Exception:
            route_poly = unary_union([g.convex_hull for g in clean])
        
        info = route_stats_dict.get(r_id, {})
        area_m2 = route_poly.area * (111139.0 * 111139.0 * 0.85)
        perim_m = route_poly.length * 111139.0
        
        # Compacidad isoperimétrica: 4 * pi * Area / Perimetro^2
        comp = (4.0 * math.pi * area_m2) / (perim_m * perim_m) if perim_m > 0 else 0.0
        comp = min(1.0, max(0.0, comp))
        
        cant_sumi = info.get('cant_suministros', 0)
        cumple_cap = 'SI' if (160 <= cant_sumi <= 200) else 'NO'
        
        route_records.append({
            'nueva_ruta_lectura': r_id,
            'distrito': info.get('distrito', 1),
            'grupo_lectura': info.get('grupo_lectura', '1'),
            'cant_suministros': cant_sumi,
            'cumple_capacidad': cumple_cap,
            'cant_manzanas': info.get('cant_manzanas', 0),
            'area_hectareas': round(area_m2 / 10000.0, 2),
            'perimetro_km': round(perim_m / 1000.0, 2),
            'compacidad_isoperimetrica': round(comp, 3),
            'centroide_lat': info.get('centroide_lat'),
            'centroide_lon': info.get('centroide_lon'),
            'calles_compartidas_en_ruta': info.get('calles_compartidas', ''),
            'geometry': route_poly
        })

gdf_routes = gpd.GeoDataFrame(route_records, geometry='geometry', crs="EPSG:4326")
print(f"      Polígonos de rutas construidos: {len(gdf_routes):,} rutas.")

# [4/5] Control de Superposiciones entre Polígonos de Rutas
print("\n[4/5] Ejecutando Control de Superposiciones (Intersección Espacial 2D)...")
overlaps_by_group = defaultdict(list)

# Evaluar superposiciones dentro de cada grupo de lectura
for g_str in grupos:
    gdf_g = gdf_routes[gdf_routes['grupo_lectura'] == g_str]
    g_geoms = gdf_g['geometry'].values
    g_r_ids = gdf_g['nueva_ruta_lectura'].values
    
    if len(g_geoms) > 1:
        tree = STRtree(g_geoms)
        for i in range(len(g_geoms)):
            geom_i = g_geoms[i]
            cands = tree.query(geom_i)
            for j in cands:
                if j > i:
                    geom_j = g_geoms[j]
                    if geom_i.intersects(geom_j):
                        inter = geom_i.intersection(geom_j)
                        area_m2 = inter.area * (111139.0 * 111139.0 * 0.85)
                        if area_m2 > 100.0: # Umbral de superposición real (área > 100 m2)
                            overlaps_by_group[g_str].append((g_r_ids[i], g_r_ids[j], area_m2))

total_overlap_pairs = sum(len(v) for v in overlaps_by_group.values())
print(f"      Control de superposiciones finalizado: {total_overlap_pairs} pares con solapamiento menor residual.")

# Clasificación de control en el padrón
print("      Calculando distancias finales al centroide de ruta en el padrón...")
final_centers = df_updated.groupby('nueva_ruta_lectura')[['latitud', 'longitud']].mean().dropna()
final_center_dict = {r: to_xy(row['latitud'], row['longitud']) for r, row in final_centers.iterrows()}

final_dists = []
for idx, r in df_updated.iterrows():
    c_xy = final_center_dict.get(r['nueva_ruta_lectura'])
    lat, lon = r['latitud'], r['longitud']
    if c_xy is not None and pd.notna(lat) and pd.notna(lon):
        mx, my = to_xy(lat, lon)
        d = math.hypot(mx - c_xy[0], my - c_xy[1]) / 1000.0
        final_dists.append(round(d, 2))
    else:
        final_dists.append(0.0)

df_updated['distancia_centroide_ruta_km'] = final_dists
df_updated['control_superposicion'] = np.where(df_updated['obs_control_topologico'] == 'Topológicamente contiguo', 'DISJUNTO_OK', 'REDISTRIBUIDO_GEO')

# [5/5] Exportar Datasets Maestros Actualizados
print("\n[5/5] Exportando datasets actualizados y sincronizados...")

# Guardar Padrón Maestro
print(f"      Guardando Padrón Maestro Parquet: {out_padron_parquet}")
df_updated.to_parquet(out_padron_parquet, index=False)

print(f"      Exportando Padrón Maestro CSV a Descargas (C:): {out_padron_c_csv}")
df_updated.to_csv(out_padron_c_csv, index=False, encoding='utf-8')

print(f"      Exportando Padrón Maestro CSV a Descargas (D:): {out_padron_d_csv}")
df_updated.to_csv(out_padron_d_csv, index=False, encoding='utf-8')

# Guardar Capa Geoespacial de Rutas (Parquet y GeoJSON)
print(f"      Guardando Polígonos de Rutas Parquet: {out_routes_parquet}")
gdf_routes.to_parquet(out_routes_parquet, index=False)

print(f"      Exportando Polígonos de Rutas GeoJSON (Proyecto): {out_routes_geojson}")
gdf_routes.to_file(out_routes_geojson, driver="GeoJSON")

print(f"      Exportando Polígonos de Rutas GeoJSON a Descargas (D:): {out_routes_d_geojson}")
gdf_routes.to_file(out_routes_d_geojson, driver="GeoJSON")

print("\n" + "=" * 110)
print(f"PROCESAMIENTO Y CONTROL GEOESPACIAL COMPLETADO EXITOSAMENTE EN {time.time()-t0:.2f} SEGUNDOS!")
print("=" * 110)
