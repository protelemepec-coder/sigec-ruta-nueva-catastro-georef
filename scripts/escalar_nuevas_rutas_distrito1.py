import os, sys, time, math, oracledb, pandas as pd, numpy as np
from collections import defaultdict
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
load_dotenv(r'D:/Proyectos/.env')
load_dotenv(r'D:\Proyectosntigravity-agents-repository\.env')

lib_dir = os.environ.get('OR_INSTANT_CLIENT', r'C:pp\client\product9.0.0\client_2in')
try:
    oracledb.init_oracle_client(lib_dir=lib_dir)
except Exception:
    pass

dsn = oracledb.makedsn(
    host=os.environ['OR_HOST'],
    port=int(os.environ.get('OR_PORT', 1521)),
    service_name=os.environ['OR_SERVICE_NAME']
)
conn = oracledb.connect(user=os.environ['OR_USER'], password=os.environ['OR_PASS'], dsn=dsn)

TARGET_CAPACITY = 180
TOLERANCIA = 20
MIN_CAPACITY = TARGET_CAPACITY - TOLERANCIA
MAX_CAPACITY = TARGET_CAPACITY + TOLERANCIA

GRUPOS_CICLICOS = [str(i) for i in range(1, 21)]

print('=' * 110)
print('ESCALAMIENTO MASIVO: RUTAS CONEXAS CON MAXIMA COMPARTICION DE CALLES INTERNAS - DISTRITO 1 (EPEC)')
print('Grupos a procesar:', len(GRUPOS_CICLICOS))
print('=' * 110)

wfs_path = 'D:/Proyectos/antigravity-agents-repository/data/vm_manzanas_calles_new.parquet'
print('[*] Cargando capa WFS oficial...')
df_wfs = pd.read_parquet(wfs_path)
wfs_dict = df_wfs.groupby('nomenclatura')['nombrecall'].apply(lambda x: set(x.str.upper().str.strip())).to_dict()
print('[+] Capa WFS indexada con', len(wfs_dict), 'manzanas.')

def dist_m(lat1, lon1, lat2, lon2):
    dlat = (lat1 - lat2) * 111139.0
    dlon = (lon1 - lon2) * 111139.0 * math.cos(math.radians(lat1))
    return math.sqrt(dlat*dlat + dlon*dlon)

all_routes_summary = []
all_groups_summary = []
all_supplies_records = []

total_t0 = time.time()

for g_str in GRUPOS_CICLICOS:
    g_num = int(g_str)
    print('\n[*] Procesando Grupo de Lectura', g_str, '...')
    t_start = time.time()

    query = 'SELECT suministro, distrito, grupo_lectura, ruta_lectura as ruta_actual, orden_lectura as orden_actual, calle, altura, barrio, localidad, datos_adicionales_domicilio, latitud, longitud, dc FROM georef.vw_suministros WHERE distrito = 1 AND grupo_lectura = ' + repr(g_str)
    df = pd.read_sql(query, conn)
    df.columns = [c.lower() for c in df.columns]
    n_sumi = len(df)
    n_rutas_ant = df['ruta_actual'].nunique()

    if n_sumi == 0:
        print('[-] Grupo', g_str, 'sin suministros. Omitiendo.')
        continue

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
    df['mza_id'] = df['mza_id'].fillna('VIRT_SD_0.0').astype(str)

    # 2. Calles Combinadas WFS + SIGEC
    sigec_streets = df.groupby('mza_id')['calle'].apply(lambda x: set(x.dropna().str.upper().str.strip())).to_dict()
    mza_streets = {}
    for m in df['mza_id'].unique():
        s = set()
        if m in wfs_dict:
            s.update(wfs_dict[m])
        if m in sigec_streets:
            s.update(sigec_streets[m])
        s = {st for st in s if len(st) > 2 and st not in {'CALLE PUBLICA', 'S/N', 'SIN NOMBRE', 'S/D'}}
        mza_streets[m] = s

    # 3. Estadisticas por Manzana
    global_lat_mean = df['latitud'].mean()
    global_lon_mean = df['longitud'].mean()
    mza_stats = df.groupby('mza_id', dropna=False).agg(
        cant_sumi=('suministro', 'count'),
        lat=('latitud', 'mean'),
        lon=('longitud', 'mean'),
        barrio=('barrio', lambda x: x.mode().iloc[0] if not x.mode().empty else 'S/D'),
        localidad=('localidad', lambda x: x.mode().iloc[0] if not x.mode().empty else 'S/D'),
        circ=('circ', 'first'),
        secc=('secc', 'first')
    ).reset_index()

    mza_stats['lat'] = mza_stats['lat'].fillna(global_lat_mean)
    mza_stats['lon'] = mza_stats['lon'].fillna(global_lon_mean)
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

    # 4. Agrupamiento Conexo
    unassigned = set(mza_info.keys())
    rutas = []
    route_seq = g_num * 1000 + 1

    mza_to_route = {}
    mza_to_subdiv = {}

    macro_mzas = [m for m in unassigned if mza_info[m]['cant'] > MAX_CAPACITY]
    for m in macro_mzas:
        cnt = mza_info[m]['cant']
        k = int(math.ceil(cnt / TARGET_CAPACITY))
        sub_rutas = list(range(route_seq, route_seq + k))
        mza_to_subdiv[m] = {'num_subrutas': k, 'rutas': sub_rutas}
        mza_to_route[m] = sub_rutas[0]
        for sub_r in sub_rutas:
            rutas.append({
                'nueva_ruta_lectura': sub_r,
                'grupo_lectura': g_str,
                'cant_suministros': int(cnt / k),
                'manzanas': [m],
                'calles_compartidas': [],
                'tipo': 'MACRO_MANZANA'
            })
        route_seq += k
        unassigned.remove(m)

    while unassigned:
        seed = min(unassigned, key=lambda m: (mza_info[m]['lat'], mza_info[m]['lon']))
        unassigned.remove(seed)

        current_mzas = [seed]
        current_cant = mza_info[seed]['cant']
        current_streets = set(mza_info[seed]['calles'])
        centroid_lat = mza_info[seed]['lat']
        centroid_lon = mza_info[seed]['lon']

        while current_cant < TARGET_CAPACITY:
            if not unassigned:
                break

            best_cand = None
            best_score = -1e9

            nearby_cands = []
            for c in unassigned:
                d = dist_m(mza_info[c]['lat'], mza_info[c]['lon'], centroid_lat, centroid_lon)
                if d < 1200:
                    nearby_cands.append((c, d))

            if not nearby_cands:
                c_near = min(unassigned, key=lambda c: dist_m(mza_info[c]['lat'], mza_info[c]['lon'], centroid_lat, centroid_lon))
                d_near = dist_m(mza_info[c_near]['lat'], mza_info[c_near]['lon'], centroid_lat, centroid_lon)
                nearby_cands.append((c_near, d_near))

            for c, d in nearby_cands:
                cand_cnt = mza_info[c]['cant']
                if current_cant + cand_cnt > MAX_CAPACITY and current_cant >= MIN_CAPACITY:
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

            if current_cant >= TARGET_CAPACITY:
                break

        st_counts = defaultdict(int)
        for m in current_mzas:
            for st in mza_info[m]['calles']:
                st_counts[st] += 1
        shared_internal = [st for st, c in st_counts.items() if c >= 2]

        rutas.append({
            'nueva_ruta_lectura': route_seq,
            'grupo_lectura': g_str,
            'cant_suministros': current_cant,
            'manzanas': current_mzas,
            'calles_compartidas': shared_internal,
            'tipo': 'CONEXA' if len(current_mzas) > 1 else 'INDIVIDUAL'
        })
        for m in current_mzas:
            mza_to_route[m] = route_seq
        route_seq += 1

    df['nueva_ruta_lectura'] = df['mza_id'].map(mza_to_route)

    for mza, sub_info in mza_to_subdiv.items():
        sub_rutas = sub_info['rutas']
        k = len(sub_rutas)
        idx_mza = df[df['mza_id'] == mza].index
        mza_sub_assign = [sub_rutas[i % k] for i in range(len(idx_mza))]
        df.loc[idx_mza, 'nueva_ruta_lectura'] = mza_sub_assign

    df['nueva_ruta_lectura'] = df['nueva_ruta_lectura'].fillna(route_seq).astype(int)

    route_shared_dict = {r['nueva_ruta_lectura']: ', '.join(r['calles_compartidas']) for r in rutas}
    route_shared_count_dict = {r['nueva_ruta_lectura']: len(r['calles_compartidas']) for r in rutas}
    route_tipo_dict = {r['nueva_ruta_lectura']: r['tipo'] for r in rutas}

    df['geo_centroide_lat'] = df['mza_id'].map(lambda m: round(mza_info[m]['lat'], 4) if m in mza_info else round(global_lat_mean, 4))
    df['geo_centroide_lon'] = df['mza_id'].map(lambda m: round(mza_info[m]['lon'], 4) if m in mza_info else round(global_lon_mean, 4))
    df['geo_quad'] = 'Q' + (df['geo_centroide_lat'].abs() * 100).astype(int).astype(str) + (df['geo_centroide_lon'].abs() * 100).astype(int).astype(str)

    df['calles_perimetrales_mza'] = df['mza_id'].map(lambda m: ', '.join(sorted(mza_info[m]['calles'])) if m in mza_info else '')
    df['cant_calles_perimetro'] = df['mza_id'].map(lambda m: len(mza_info[m]['calles']) if m in mza_info else 0)
    df['calles_compartidas_en_ruta'] = df['nueva_ruta_lectura'].map(route_shared_dict)
    df['cant_calles_compartidas'] = df['nueva_ruta_lectura'].map(route_shared_count_dict)
    df['tipo_contiguidad'] = df['nueva_ruta_lectura'].map(route_tipo_dict)

    df['id_suministro_catastral_geo'] = '1-' + g_str + '-' + df['mza_wfs'] + '-' + df['parc'] + '-' + df['geo_quad']

    df = df.sort_values(by=['nueva_ruta_lectura', 'mza_wfs', 'calle', 'altura', 'parc']).reset_index(drop=True)
    df['orden_lectura_sugerido'] = df.groupby('nueva_ruta_lectura').cumcount() + 1

    df_rutas_grp = pd.DataFrame(rutas)
    multi_mza = df_rutas_grp[df_rutas_grp['manzanas'].apply(len) > 1]
    shared_mean = multi_mza['calles_compartidas'].apply(len).mean() if not multi_mza.empty else 0.0

    t_elapsed = time.time() - t_start
    n_rutas_nuevas = len(rutas)
    media_sumi = df_rutas_grp['cant_suministros'].mean()
    mediana_sumi = df_rutas_grp['cant_suministros'].median()
    pct_range = ((df_rutas_grp['cant_suministros'] >= MIN_CAPACITY) & (df_rutas_grp['cant_suministros'] <= MAX_CAPACITY)).mean() * 100

    print('[+] Grupo', g_str, 'procesado en', round(t_elapsed, 1), 's | Suministros:', n_sumi, '| Rutas:', n_rutas_ant, '->', n_rutas_nuevas, '| Media:', round(media_sumi, 1), '| Rango:', round(pct_range, 1), '% | Calles comp:', round(shared_mean, 2))

    all_groups_summary.append({
        'grupo_lectura': g_str,
        'suministros_totales': n_sumi,
        'rutas_anteriores': n_rutas_ant,
        'rutas_nuevas': n_rutas_nuevas,
        'media_suministros_ruta': round(media_sumi, 1),
        'mediana_suministros_ruta': round(mediana_sumi, 1),
        'pct_en_rango_160_200': round(pct_range, 1),
        'calles_compartidas_promedio': round(shared_mean, 2),
        'tiempo_segundos': round(t_elapsed, 1)
    })

    for r in rutas:
        all_routes_summary.append({
            'nueva_ruta_lectura': r['nueva_ruta_lectura'],
            'grupo_lectura': r['grupo_lectura'],
            'cant_suministros': r['cant_suministros'],
            'cant_manzanas': len(r['manzanas']),
            'cant_calles_compartidas': len(r['calles_compartidas']),
            'tipo_contiguidad': r['tipo'],
            'manzanas': ', '.join(r['manzanas']),
            'calles_compartidas': ', '.join(r['calles_compartidas'])
        })

    all_supplies_records.append(df[[
        'suministro', 'distrito', 'grupo_lectura', 'nueva_ruta_lectura', 'orden_lectura_sugerido',
        'ruta_actual', 'orden_actual', 'calle', 'altura', 'barrio', 'localidad',
        'latitud', 'longitud', 'dc', 'mza_wfs', 'id_suministro_catastral_geo',
        'geo_centroide_lat', 'geo_centroide_lon', 'geo_quad',
        'cant_calles_perimetro', 'calles_perimetrales_mza',
        'cant_calles_compartidas', 'calles_compartidas_en_ruta', 'tipo_contiguidad'
    ]])

conn.close()
total_time = time.time() - total_t0
print('\n[+] Escalamiento de 20 grupos finalizado en', round(total_time/60, 2), 'minutos.')

df_all_supplies = pd.concat(all_supplies_records, ignore_index=True)
df_all_routes = pd.DataFrame(all_routes_summary)
df_all_groups = pd.DataFrame(all_groups_summary)

descargas = os.path.expanduser(r'~\Downloads')
repo_summary = 'D:/Proyectos/sigec-ruta-nueva-catastro-georef/data/summary'
os.makedirs(repo_summary, exist_ok=True)

padron_csv_path = os.path.join(descargas, 'padron_nuevas_rutas_distrito1_completo.csv')
print('[*] Guardando padron completo en CSV:', padron_csv_path, '...')
df_all_supplies.to_csv(padron_csv_path, index=False, encoding='utf-8-sig')

padron_parquet_path = os.path.join(repo_summary, 'padron_nuevas_rutas_distrito1_completo.parquet')
print('[*] Guardando padron en Parquet:', padron_parquet_path, '...')
df_all_supplies.to_parquet(padron_parquet_path, index=False)

routes_csv_path = os.path.join(repo_summary, 'resumen_todas_rutas_nuevas_distrito1.csv')
df_all_routes.to_csv(routes_csv_path, index=False, encoding='utf-8-sig')
df_all_routes.to_csv(os.path.join(descargas, 'resumen_todas_rutas_nuevas_distrito1.csv'), index=False, encoding='utf-8-sig')

groups_csv_path = os.path.join(repo_summary, 'resumen_comparativo_grupos_distrito1.csv')
df_all_groups.to_csv(groups_csv_path, index=False, encoding='utf-8-sig')
df_all_groups.to_csv(os.path.join(descargas, 'resumen_comparativo_grupos_distrito1.csv'), index=False, encoding='utf-8-sig')

print('=' * 110)
print('ESCALAMIENTO COMPLETADO EXITOSAMENTE')
print('Total suministros:', len(df_all_supplies))
print('Total rutas nuevas:', len(df_all_routes))
print('Media global:', round(df_all_routes['cant_suministros'].mean(), 1), 'suministros/ruta')
multi_total = df_all_routes[df_all_routes['cant_manzanas'] > 1]
print('Promedio global calles compartidas (multi-mza):', round(multi_total['cant_calles_compartidas'].mean(), 2), 'calles/ruta')
print('=' * 110)
