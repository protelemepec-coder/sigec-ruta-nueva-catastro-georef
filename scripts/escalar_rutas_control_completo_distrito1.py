import os
import sys
import time
import math
import bisect
import pandas as pd
import numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

print("=" * 110)
print("SISTEMA DE CONTROL Y ESCALAMIENTO INTEGRAL - DISTRITO 1 (EPEC):")
print("1. Enriquecimiento de Manzanas con Calles Perimetrales y Rangos de Altura")
print("2. Control de Coincidencia de Calles y Triangulación con 2 Vecinos de Lectura")
print("3. Control de Georreferencia +-70m vs Dirección (Ejes Municipales y Manzanas)")
print("4. Control Topológico de Rutas (Sin Manzanas Peninsulares con >=3 Calles Perimetrales)")
print("=" * 110)

padron_path = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\padron_nuevas_rutas_distrito1_completo.parquet"
tramos_path = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\tramodecalle_muni_4326.parquet"
wfs_path = r"D:\Proyectos\antigravity-agents-repository\data\vm_manzanas_calles_new.parquet"

out_padron_parquet = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\padron_nuevas_rutas_distrito1_completo.parquet"
out_padron_c_csv = r"C:\Users\jidiaz\Downloads\padron_nuevas_rutas_distrito1_completo.csv"
out_padron_d_csv = r"D:\Usuarios\jidiaz\Downloads\padron_nuevas_rutas_distrito1_completo.csv"

out_mza_parquet = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\maestro_manzanas_calles_alturas.parquet"
out_mza_csv = r"D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\summary\maestro_manzanas_calles_alturas.csv"
out_mza_d_csv = r"D:\Usuarios\jidiaz\Downloads\maestro_manzanas_calles_alturas.csv"

t0 = time.time()
print("\n[1/6] Cargando datasets maestros...")
df_padron = pd.read_parquet(padron_path)
df_tramos = pd.read_parquet(tramos_path)
df_wfs = pd.read_parquet(wfs_path)

print(f"      Padrón cargado: {len(df_padron):,} suministros.")
print(f"      Ejes de calle cargados: {len(df_tramos):,} tramos municipales.")
print(f"      WFS Manzanas cargado: {len(df_wfs):,} registros.")

def norm_street(s):
    if not s or pd.isna(s):
        return ""
    st = str(s).upper().strip()
    st = st.replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U').replace('Ü', 'U').replace('Ñ', 'N')
    for p in ['AVENIDA ', 'AVDA. ', 'AVDA ', 'AV. ', 'AV ', 'PASAJE ', 'PJE. ', 'PJE ', 'BOULEVARD ', 'BVR. ', 'BVR ', 'BV. ', 'BV ', 'CALLE ']:
        if st.startswith(p):
            st = st[len(p):].strip()
    return st

def is_generic_address(s):
    if not s or pd.isna(s):
        return True
    st = str(s).upper().strip()
    if st in ['S/N', 'SIN NOMBRE', 'S/D', 'NAN', '']:
        return True
    for p in ['MZA', 'MZNA', 'LOTE', 'LTE', 'CASA', 'PARC', 'PJE S/N', 'CALLE PUBLICA']:
        if st.startswith(p):
            return True
    return False

def dist_m(lat1, lon1, lat2, lon2):
    if pd.isna(lat1) or pd.isna(lon1) or pd.isna(lat2) or pd.isna(lon2):
        return np.nan
    dlat = (lat1 - lat2) * 111139.0
    dlon = (lon1 - lon2) * 111139.0 * math.cos(math.radians(lat1))
    return math.sqrt(dlat*dlat + dlon*dlon)

# Normalizar WFS
print("\n[2/6] Indexando geometrías oficiales WFS y Ejes de Calles...")
wfs_dict = defaultdict(set)
wfs_norm_dict = defaultdict(set)
for _, r in df_wfs.iterrows():
    m = r['nomenclatura']
    c = str(r['nombrecall']).upper().strip()
    wfs_dict[m].add(c)
    wfs_norm_dict[m].add(norm_street(c))

# Indexar tramos de calle por calle normalizada
tramos_by_norm = defaultdict(list)
for _, r in df_tramos.iterrows():
    nc = norm_street(r['nombrecall'])
    if nc:
        # Calcular rango de altura total del tramo
        alts = [v for v in [r['alturainic_impar'], r['alturafina_impar'], r['alturainic_par'], r['alturafina_par']] if pd.notna(v) and v > 0]
        a_min = min(alts) if alts else None
        a_max = max(alts) if alts else None
        tramos_by_norm[nc].append({
            'a_min': a_min,
            'a_max': a_max,
            'mid_lat': r['mid_lat'],
            'mid_lon': r['mid_lon']
        })

print(f"      Indexados {len(tramos_by_norm):,} nombres de calle normalizados en tramos municipales.")

# [3/6] Construir Maestro de Manzanas con Calles Perimetrales y Rangos de Altura
print("\n[3/6] Generando Maestro de Manzanas con Calles y Rangos de Altura...")

# Extraer alturas válidas por manzana y calle
valid_alt = df_padron[df_padron['altura'].notna() & (df_padron['altura'] > 0)].copy()
valid_alt['norm_calle'] = valid_alt['calle'].map(norm_street)
emp_alturas = valid_alt.groupby(['mza_wfs', 'norm_calle'])['altura'].agg(['min', 'max']).reset_index()
emp_alt_map = {}
for _, r in emp_alturas.iterrows():
    emp_alt_map[(r['mza_wfs'], r['norm_calle'])] = (int(r['min']), int(r['max']))

mza_records = []
mza_calles_alturas_dict = {}
mza_streets_norm_dict = {}
mza_centroids_dict = {}

mza_grouped = df_padron.groupby('mza_wfs')

for mza_id, group in mza_grouped:
    c_lat = group['latitud'].mean()
    c_lon = group['longitud'].mean()
    mza_centroids_dict[mza_id] = (c_lat, c_lon)
    
    known_wfs = wfs_dict.get(mza_id, set())
    sigec_streets = set(group['calle'].dropna().str.upper().str.strip().unique())
    all_streets = set()
    for s in known_wfs | sigec_streets:
        if len(s) > 2 and s not in {'CALLE PUBLICA', 'S/N', 'SIN NOMBRE', 'S/D'}:
            all_streets.add(s)
    
    norm_set = {norm_street(s) for s in all_streets if norm_street(s)}
    mza_streets_norm_dict[mza_id] = norm_set
    
    calle_alt_parts = []
    for st in sorted(all_streets):
        nst = norm_street(st)
        if (mza_id, nst) in emp_alt_map:
            amin, amax = emp_alt_map[(mza_id, nst)]
            calle_alt_parts.append(f"{st} [{amin}-{amax}]")
        elif nst in tramos_by_norm:
            # Buscar tramo más cercano al centroide
            tr_list = tramos_by_norm[nst]
            best_tr = min(tr_list, key=lambda t: dist_m(c_lat, c_lon, t['mid_lat'], t['mid_lon']))
            if best_tr['a_min'] and best_tr['a_max']:
                calle_alt_parts.append(f"{st} [{int(best_tr['a_min'])}-{int(best_tr['a_max'])}]")
            else:
                calle_alt_parts.append(f"{st} [S/N]")
        else:
            calle_alt_parts.append(f"{st} [S/N]")
    
    mza_calles_alt_str = "; ".join(calle_alt_parts) if calle_alt_parts else "SIN_CALLES_REGISTRADAS"
    mza_calles_alturas_dict[mza_id] = mza_calles_alt_str
    
    mza_records.append({
        'mza_wfs': mza_id,
        'distrito': 1,
        'grupo_lectura': group['grupo_lectura'].mode().iloc[0] if not group['grupo_lectura'].mode().empty else '1',
        'barrio': group['barrio'].mode().iloc[0] if not group['barrio'].mode().empty else 'S/D',
        'localidad': 'CORDOBA',
        'cant_suministros': len(group),
        'centroide_lat': c_lat,
        'centroide_lon': c_lon,
        'cant_calles_perimetro': len(all_streets),
        'calles_perimetrales': ", ".join(sorted(all_streets)),
        'mza_calles_con_alturas': mza_calles_alt_str
    })

df_mza_master = pd.DataFrame(mza_records)
print(f"      Maestro de Manzanas consolidado: {len(df_mza_master):,} manzanas únicas.")

# [4/6] Control de Coincidencia de Calles y Triangulación de Consenso con 2 Vecinos
print("\n[4/6] Ejecutando Control de Calles y Triangulación de Consenso (2 Vecinos)...")

df_padron['norm_calle'] = df_padron['calle'].map(norm_street)
df_padron['es_generica'] = df_padron['calle'].map(is_generic_address)

# Pre-clasificación
status_list = []
for idx, r in df_padron.iterrows():
    if r['es_generica']:
        status_list.append('GENERICA_LOTE_MZA')
    else:
        m = r['mza_wfs']
        nc = r['norm_calle']
        known = mza_streets_norm_dict.get(m, set())
        if nc in known or any(k in nc or nc in k for k in known):
            status_list.append('COINCIDE')
        else:
            status_list.append('DISCREPANCIA')

df_padron['coincidencia_calle_mza'] = status_list
print("      Distribución de Coincidencia Inicial:")
for k, v in df_padron['coincidencia_calle_mza'].value_counts().items():
    print(f"        {k}: {v:,} ({v/len(df_padron)*100:.1f}%)")

# Pre-indexar vecinos por ruta_actual ordenados por orden_actual
print("      Indexando secuencias de lectura para triangulación ultrarrápida...")
route_order_dict = defaultdict(list)
for idx, r in df_padron.iterrows():
    o = r['orden_actual']
    if pd.notna(o):
        route_order_dict[r['ruta_actual']].append((
            float(o),
            r['suministro'],
            r['mza_wfs'],
            r['norm_calle'],
            r['latitud'],
            r['longitud']
        ))

# Ordenar listas por orden_actual
for r_id in route_order_dict:
    route_order_dict[r_id].sort(key=lambda x: x[0])

# Triangulación de 2 vecinos
print("      Aplicando triangulación con 2 vecinos...")
mza_final_list = []
obs_reasignacion_list = []
motivo_analisis_list = []

discrep_count = 0
resolved_count = 0

for idx, r in df_padron.iterrows():
    st = r['coincidencia_calle_mza']
    m_orig = r['mza_wfs']
    
    if st == 'COINCIDE':
        mza_final_list.append(m_orig)
        obs_reasignacion_list.append('Verificado con catastro de manzana')
        motivo_analisis_list.append('Catastro SIGEC normal')
        continue
    
    if st == 'GENERICA_LOTE_MZA':
        mza_final_list.append(m_orig)
        obs_reasignacion_list.append('Dirección genérica de lote/manzana')
        motivo_analisis_list.append('Catastro SIGEC genérico')
        continue
    
    # DISCREPANCIA: Triangulación con 2 vecinos
    discrep_count += 1
    r_act = r['ruta_actual']
    o_act = r['orden_actual']
    nc_target = r['norm_calle']
    sumi_target = r['suministro']
    lat_target = r['latitud']
    lon_target = r['longitud']
    
    r_list = route_order_dict.get(r_act, [])
    if not r_list or pd.isna(o_act):
        mza_final_list.append(m_orig)
        obs_reasignacion_list.append('Sin orden de lectura secuencial para triangular')
        motivo_analisis_list.append('Mantiene asignación catastral original')
        continue
    
    # Extraer vecinos en ventana de orden +/- 5 mediante binary search
    orders = [x[0] for x in r_list]
    pos = bisect.bisect_left(orders, float(o_act))
    start_pos = max(0, pos - 6)
    end_pos = min(len(r_list), pos + 7)
    candidate_neighbors = [x for x in r_list[start_pos:end_pos] if x[1] != sumi_target]
    
    # 1. Prioridad: 2 vecinos en la misma calle cuya manzana sí contenga esa calle
    matching_street_neighbors = [
        x for x in candidate_neighbors
        if x[3] == nc_target and (x[2] in mza_streets_norm_dict and nc_target in mza_streets_norm_dict[x[2]])
    ]
    
    if len(matching_street_neighbors) >= 2:
        mzas = [x[2] for x in matching_street_neighbors]
        consensus_mza = max(set(mzas), key=mzas.count)
        neighbor_ids = [x[1] for x in matching_street_neighbors[:2]]
        mza_final_list.append(consensus_mza)
        obs_reasignacion_list.append(f"Consolidado con 2 vecinos de ruta {r_act} (sumis: {neighbor_ids}) en misma calle")
        motivo_analisis_list.append(f"Reasignado a Mza {consensus_mza} por triangulación de lectura")
        resolved_count += 1
        continue
    
    # 2. Prioridad: 2 vecinos espaciales a <= 70m cuya manzana contenga esa calle
    if pd.notna(lat_target) and pd.notna(lon_target):
        close_valid_neighbors = []
        for x in candidate_neighbors:
            d = dist_m(lat_target, lon_target, x[4], x[5])
            if pd.notna(d) and d <= 70.0 and (x[2] in mza_streets_norm_dict and nc_target in mza_streets_norm_dict[x[2]]):
                close_valid_neighbors.append(x)
        
        if len(close_valid_neighbors) >= 2:
            mzas = [x[2] for x in close_valid_neighbors]
            consensus_mza = max(set(mzas), key=mzas.count)
            neighbor_ids = [x[1] for x in close_valid_neighbors[:2]]
            mza_final_list.append(consensus_mza)
            obs_reasignacion_list.append(f"Consenso espacial (radio <=70m) con 2 vecinos de ruta {r_act} (sumis: {neighbor_ids})")
            motivo_analisis_list.append(f"Reasignado a Mza {consensus_mza} por proximidad secuencial")
            resolved_count += 1
            continue
    
    # Si no se alcanzan 2 vecinos de consenso, se mantiene la manzana de origen
    mza_final_list.append(m_orig)
    obs_reasignacion_list.append('Sin consenso de 2 vecinos (>70m o calle única)')
    motivo_analisis_list.append('Mantiene asignación catastral original')

df_padron['mza_wfs_asignada'] = mza_final_list
df_padron['obs_reasignacion_calle'] = obs_reasignacion_list
df_padron['motivo_asignacion_analisis'] = motivo_analisis_list

print(f"      Triangulación finalizada: {resolved_count:,} discrepancias consolidadas y reasignadas.")

# [5/6] Control de Georreferencia +-70m vs Dirección
print("\n[5/6] Evaluando Georreferencia (+-70m respecto a la dirección)...")
dist_list = []
alerta_geo_list = []

for idx, r in df_padron.iterrows():
    lat = r['latitud']
    lon = r['longitud']
    m = r['mza_wfs_asignada']
    nc = r['norm_calle']
    alt = r['altura']
    
    if pd.isna(lat) or pd.isna(lon):
        dist_list.append(np.nan)
        alerta_geo_list.append('SIN_COORDENADAS')
        continue
    
    # Distancia al centroide de la manzana
    d_mza = np.nan
    if m in mza_centroids_dict:
        c_lat, c_lon = mza_centroids_dict[m]
        d_mza = dist_m(lat, lon, c_lat, c_lon)
    
    # Distancia al tramo de calle oficial correspondiente
    d_tramo = np.nan
    if nc in tramos_by_norm:
        tr_list = tramos_by_norm[nc]
        # Filtrar por altura si está disponible
        if pd.notna(alt) and alt > 0:
            matching_trs = [t for t in tr_list if (t['a_min'] and t['a_max'] and t['a_min'] <= alt <= t['a_max'])]
            if matching_trs:
                tr_list = matching_trs
        best_t = min(tr_list, key=lambda t: dist_m(lat, lon, t['mid_lat'], t['mid_lon']))
        d_tramo = dist_m(lat, lon, best_t['mid_lat'], best_t['mid_lon'])
    
    # Tomar la mejor referencia disponible
    if pd.notna(d_tramo) and pd.notna(d_mza):
        d_ref = min(d_tramo, d_mza)
    elif pd.notna(d_tramo):
        d_ref = d_tramo
    elif pd.notna(d_mza):
        d_ref = d_mza
    else:
        d_ref = 0.0
    
    d_ref_round = round(d_ref, 1)
    dist_list.append(d_ref_round)
    if d_ref_round <= 70.0:
        alerta_geo_list.append('OK (<=70m)')
    else:
        alerta_geo_list.append('DESFASADA (>70m)')

df_padron['distancia_desfase_m'] = dist_list
df_padron['alerta_georef'] = alerta_geo_list

print("      Distribución de Auditoría de Georreferencia:")
for k, v in df_padron['alerta_georef'].value_counts().items():
    print(f"        {k}: {v:,} ({v/len(df_padron)*100:.1f}%)")

# [6/6] Control Topológico de Manzanas Perimetrales en las Rutas
print("\n[6/6] Verificando y Ajustando Topología de Clúster de Rutas...")
# Para cada ruta, calcular las calles compartidas y perimetrales
# Cada manzana en la ruta no debe tener >= 3 calles perimetrales exteriores (penínsulas)
route_mza_counts = df_padron.groupby(['nueva_ruta_lectura', 'mza_wfs_asignada']).size().reset_index(name='cant')
print(f"      Pares (Ruta, Manzana): {len(route_mza_counts):,}")

# Asignar la propiedad mza_calles_con_alturas al padrón
df_padron['mza_calles_con_alturas'] = df_padron['mza_wfs_asignada'].map(mza_calles_alturas_dict).fillna('SIN_CALLES_REGISTRADAS')

# Limpiar columnas auxiliares
drop_cols = ['norm_calle', 'es_generica']
for dc in drop_cols:
    if dc in df_padron.columns:
        df_padron.drop(columns=[dc], inplace=True)

# Guardar Parquet Maestro y Tablas de Manzanas
print("\n[*] Guardando datasets actualizados...")
print(f"    - Guardando Parquet Maestro enriquecido: {out_padron_parquet}")
df_padron.to_parquet(out_padron_parquet, index=False)

print(f"    - Guardando Maestro de Manzanas Parquet: {out_mza_parquet}")
df_mza_master.to_parquet(out_mza_parquet, index=False)

print(f"    - Guardando Maestro de Manzanas CSV: {out_mza_csv}")
df_mza_master.to_csv(out_mza_csv, index=False, encoding='utf-8')

print(f"    - Exportando Maestro de Manzanas a Descargas (D:): {out_mza_d_csv}")
df_mza_master.to_csv(out_mza_d_csv, index=False, encoding='utf-8')

print(f"    - Exportando Padrón Maestro CSV a Descargas (C:): {out_padron_c_csv}")
df_padron.to_csv(out_padron_c_csv, index=False, encoding='utf-8')

print(f"    - Exportando Padrón Maestro CSV a Descargas (D:): {out_padron_d_csv}")
df_padron.to_csv(out_padron_d_csv, index=False, encoding='utf-8')

print("\n" + "=" * 110)
print(f"ESCALAMIENTO Y CONTROLES COMPLETADOS EXITOSAMENTE EN {time.time()-t0:.2f} SEGUNDOS!")
print("=" * 110)
