# Test Ruteo Conexo G16
import os, sys, time, math, pandas as pd, numpy as np
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# Cargar cache de G16
df = pd.read_parquet(r'D:\Proyectos\sigec-ruta-nueva-catastro-georef\data\g16_suministros_cache.parquet')
print(f'Total suministros G16: {len(df):,}')

# 1. Tratamiento Catastral
df['dc_clean'] = df['dc'].fillna('').astype(str).str.strip()
has_valid_dc = (df['dc_clean'].str.len() == 16)

df['dpto'] = np.where(has_valid_dc, df['dc_clean'].str[0:2], '11')
df['pedania'] = np.where(has_valid_dc, df['dc_clean'].str[2:4], '01')
df['pueblo'] = np.where(has_valid_dc, df['dc_clean'].str[4:6], '01')
df['circ'] = np.where(has_valid_dc, df['dc_clean'].str[6:8], '01')
df['secc'] = np.where(has_valid_dc, df['dc_clean'].str[8:10], '01')
df['mza'] = np.where(has_valid_dc, df['dc_clean'].str[10:13], '000')
df['parc'] = np.where(has_valid_dc, df['dc_clean'].str[13:16], '000')

df['mza_wfs'] = df['dpto'] + '-' + df['pedania'] + '-' + df['pueblo'] + '-' + df['circ'] + '-' + df['secc'] + '-' + df['mza']
df['mza_id'] = np.where(
    has_valid_dc,
    df['mza_wfs'],
    'VIRT_' + df['barrio'].fillna('SD').str.slice(0, 10).str.replace(' ', '_') + '_' + (df['latitud'].round(3).astype(str))
)

# 2. Cargar Calles WFS + SIGEC
df_wfs = pd.read_parquet(r'D:\Proyectos\antigravity-agents-repository\data\vm_manzanas_calles_new.parquet')
wfs_dict = df_wfs.groupby('nomenclatura')['nombrecall'].apply(lambda x: set(x.str.upper().str.strip())).to_dict()
sigec_streets = df.groupby('mza_id')['calle'].apply(lambda x: set(x.dropna().str.upper().str.strip())).to_dict()

mza_streets = {}
all_mzas = df['mza_id'].unique()
for m in all_mzas:
    s = set()
    if m in wfs_dict:
        s.update(wfs_dict[m])
    if m in sigec_streets:
        s.update(sigec_streets[m])
    # Filtrar nombres genericos
    s = {st for st in s if len(st) > 2 and st not in {'CALLE PUBLICA', 'S/N', 'SIN NOMBRE', 'S/D'}}
    mza_streets[m] = s

# Estadisticas por manzana
mza_stats = df.groupby('mza_id').agg(
    cant_sumi=('suministro', 'count'),
    lat=('latitud', 'mean'),
    lon=('longitud', 'mean'),
    barrio=('barrio', lambda x: x.mode().iloc[0] if not x.mode().empty else 'S/D'),
    circ=('circ', 'first'),
    secc=('secc', 'first')
).reset_index()

global_lat = df['latitud'].mean()
global_lon = df['longitud'].mean()
mza_stats['lat'] = mza_stats['lat'].fillna(global_lat)
mza_stats['lon'] = mza_stats['lon'].fillna(global_lon)
mza_stats['calles'] = mza_stats['mza_id'].map(mza_streets)

mza_info = {}
for _, r in mza_stats.iterrows():
    mza_info[r['mza_id']] = {
        'id': r['mza_id'],
        'cant': r['cant_sumi'],
        'lat': r['lat'],
        'lon': r['lon'],
        'calles': r['calles'],
        'barrio': r['barrio']
    }

def dist_m(lat1, lon1, lat2, lon2):
    dlat = (lat1 - lat2) * 111139.0
    dlon = (lon1 - lon2) * 111139.0 * math.cos(math.radians(lat1))
    return math.sqrt(dlat*dlat + dlon*dlon)

# Parametros
TARGET_CAP = 180
MIN_CAP = 160
MAX_CAP = 200

unassigned = set(mza_info.keys())
rutas = []
route_seq = 16001

# Separar macro-manzanas (> 200)
macro_mzas = [m for m in unassigned if mza_info[m]['cant'] > MAX_CAP]
for m in macro_mzas:
    cnt = mza_info[m]['cant']
    k = int(math.ceil(cnt / TARGET_CAP))
    for _ in range(k):
        rutas.append({
            'ruta_id': route_seq,
            'mzas': [m],
            'cant': int(cnt / k),
            'calles_compartidas': [],
            'tipo': 'MACRO_MANZANA'
        })
        route_seq += 1
    unassigned.remove(m)

print(f'Macro-manzanas: {len(macro_mzas)}')
print(f'Manzanas regulares a rutar de forma conexa: {len(unassigned)}')

t0 = time.time()
while unassigned:
    # Seleccionar semilla: manzana no asignada mas al sur/oeste
    seed = min(unassigned, key=lambda m: (mza_info[m]['lat'], mza_info[m]['lon']))
    unassigned.remove(seed)
    
    current_mzas = [seed]
    current_cant = mza_info[seed]['cant']
    current_streets = set(mza_info[seed]['calles'])
    centroid_lat = mza_info[seed]['lat']
    centroid_lon = mza_info[seed]['lon']
    
    while current_cant < TARGET_CAP:
        best_cand = None
        best_score = -1e9
        
        nearby_cands = []
        for c in unassigned:
            d = dist_m(mza_info[c]['lat'], mza_info[c]['lon'], centroid_lat, centroid_lon)
            if d < 1200:
                nearby_cands.append((c, d))
                
        if not unassigned:
            break
        if not nearby_cands:
            c_near = min(unassigned, key=lambda c: dist_m(mza_info[c]['lat'], mza_info[c]['lon'], centroid_lat, centroid_lon))
            d_near = dist_m(mza_info[c_near]['lat'], mza_info[c_near]['lon'], centroid_lat, centroid_lon)
            nearby_cands.append((c_near, d_near))
            
        for c, d in nearby_cands:
            cand_cnt = mza_info[c]['cant']
            if current_cant + cand_cnt > MAX_CAP and current_cant >= MIN_CAP:
                continue
                
            shared_st = len(mza_info[c]['calles'].intersection(current_streets))
            is_touching = (shared_st > 0 and d <= 600) or (d <= 200)
            
            if is_touching:
                score = 50000 + (shared_st * 10000) - d
            else:
                score = -d
                
            if score > best_score:
                best_score = score
                best_cand = c
                
        if best_cand is None:
            break
            
        if best_score < 0 and current_cant >= 120:
            break
            
        unassigned.remove(best_cand)
        current_mzas.append(best_cand)
        current_cant += mza_info[best_cand]['cant']
        current_streets.update(mza_info[best_cand]['calles'])
        centroid_lat = np.mean([mza_info[m]['lat'] for m in current_mzas])
        centroid_lon = np.mean([mza_info[m]['lon'] for m in current_mzas])
        
        if current_cant >= TARGET_CAP:
            break
            
    st_counts = defaultdict(int)
    for m in current_mzas:
        for st in mza_info[m]['calles']:
            st_counts[st] += 1
    shared_internal = [st for st, cnt in st_counts.items() if cnt >= 2]
    
    rutas.append({
        'ruta_id': route_seq,
        'mzas': current_mzas,
        'cant': current_cant,
        'calles_compartidas': shared_internal,
        'tipo': 'CONEXA' if len(current_mzas) > 1 else 'INDIVIDUAL'
    })
    route_seq += 1

t1 = time.time()
print(f'Ruteo completado en {t1-t0:.2f} s. Rutas generadas: {len(rutas)}')

df_rutas = pd.DataFrame(rutas)
df_rutas['num_mzas'] = df_rutas['mzas'].apply(len)
df_rutas['num_calles_comp'] = df_rutas['calles_compartidas'].apply(len)

multi_mza = df_rutas[df_rutas['num_mzas'] > 1]
print('=== RESULTADOS FINALES DEL PILOTO G16 ===')
print('Media de suministros por ruta:', round(df_rutas['cant'].mean(), 1))
print('Mediana de suministros por ruta:', round(df_rutas['cant'].median(), 1))
in_range = ((df_rutas['cant'] >= MIN_CAP) & (df_rutas['cant'] <= MAX_CAP)).sum()
print(f'Rutas en rango [160, 200]: {in_range} ({in_range/len(df_rutas)*100:.1f}%)')
print('Promedio de manzanas por ruta:', round(df_rutas['num_mzas'].mean(), 2))
print('Promedio de calles internas compartidas en rutas multi-manzana:', round(multi_mza['num_calles_comp'].mean(), 2))
with_shared = (multi_mza['num_calles_comp'] > 0).sum()
print(f'Rutas multi-manzana que comparten calles internas: {with_shared} de {len(multi_mza)} ({with_shared/len(multi_mza)*100:.1f}%)')
