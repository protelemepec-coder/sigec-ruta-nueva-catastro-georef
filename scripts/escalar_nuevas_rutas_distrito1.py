import os
import sys
import time
import oracledb
import pandas as pd
import numpy as np
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno
load_dotenv(r"D:\Proyectos\.env")
load_dotenv(r"D:\Proyectos\antigravity-agents-repository\.env")

lib_dir = os.environ.get("OR_INSTANT_CLIENT", r"C:\app\client\product\19.0.0\client_2\bin")
try:
    oracledb.init_oracle_client(lib_dir=lib_dir)
except Exception:
    pass

dsn = oracledb.makedsn(
    host=os.environ["OR_HOST"],
    port=int(os.environ.get("OR_PORT", 1521)),
    service_name=os.environ["OR_SERVICE_NAME"]
)
conn = oracledb.connect(user=os.environ["OR_USER"], password=os.environ["OR_PASS"], dsn=dsn)

# Parametros de Bin-Packing
TARGET_CAPACITY = 180
TOLERANCIA = 20
MIN_CAPACITY = TARGET_CAPACITY - TOLERANCIA  # 160
MAX_CAPACITY = TARGET_CAPACITY + TOLERANCIA  # 200

# Grupos regulares cíclicos a escalar (1 al 20)
GRUPOS_CICLICOS = [str(i) for i in range(1, 21)]

print("=" * 110)
print("🚀 ESCALAMIENTO DE REASIGNACIÓN CATASTRAL DE RUTAS DE LECTURA - DISTRITO 1 (EPEC)")
print(f"Grupos a procesar: {len(GRUPOS_CICLICOS)} grupos ({', '.join(GRUPOS_CICLICOS)})")
print(f"Capacidad objetivo por ruta: {TARGET_CAPACITY} suministros (Rango de tolerancia: [{MIN_CAPACITY}, {MAX_CAPACITY}])")
print("=" * 110)

all_routes_summary = []
all_groups_summary = []
all_supplies_records = []

total_t0 = time.time()

for g_str in GRUPOS_CICLICOS:
    g_num = int(g_str)
    print(f"\n[*] Procesando Grupo de Lectura {g_str}...")
    t_start = time.time()

    query = f"""
    SELECT 
        suministro,
        distrito,
        grupo_lectura,
        ruta_lectura as ruta_actual,
        orden_lectura as orden_actual,
        calle,
        altura,
        barrio,
        localidad,
        datos_adicionales_domicilio,
        latitud,
        longitud,
        dc
    FROM georef.vw_suministros
    WHERE distrito = 1 AND grupo_lectura = '{g_str}'
    """
    df = pd.read_sql(query, conn)
    df.columns = [c.lower() for c in df.columns]
    n_sumi = len(df)
    n_rutas_ant = df['ruta_actual'].nunique()

    if n_sumi == 0:
        print(f"[-] Grupo {g_str} sin suministros. Omitiendo.")
        continue

    # 1. Tratamiento Catastral
    df['dc_clean'] = df['dc'].fillna('').astype(str).str.strip()
    has_valid_dc = (df['dc_clean'].str.len() == 16)

    # Descomposición estándar para válidos
    df['dpto'] = np.where(has_valid_dc, df['dc_clean'].str[0:2], '11')
    df['pedania'] = np.where(has_valid_dc, df['dc_clean'].str[2:4], '01')
    df['pueblo'] = np.where(has_valid_dc, df['dc_clean'].str[4:6], '01')
    df['circ'] = np.where(has_valid_dc, df['dc_clean'].str[6:8], '01')
    df['secc'] = np.where(has_valid_dc, df['dc_clean'].str[8:10], '01')
    df['mza'] = np.where(has_valid_dc, df['dc_clean'].str[10:13], '000')
    df['parc'] = np.where(has_valid_dc, df['dc_clean'].str[13:16], '000')

    # Para casos sin DC, armar agrupación territorial por barrio y coordenadas
    df['mza_13dig'] = np.where(
        has_valid_dc,
        df['dc_clean'].str[0:13],
        'VIRT_' + df['barrio'].fillna('SD').str.slice(0, 10).str.replace(' ', '_') + '_' + (df['latitud'].round(3).astype(str))
    )

    df['mza_wfs'] = df['dpto'] + '-' + df['pedania'] + '-' + df['pueblo'] + '-' + df['circ'] + '-' + df['secc'] + '-' + df['mza']
    df['id_suministro_catastral'] = f'1-{g_str}-' + df['mza_wfs'] + '-' + df['parc']

    # 2. Agrupación a nivel Manzana Atómica
    mza_stats = df.groupby('mza_13dig').agg(
        cant_suministros=('suministro', 'count'),
        lat_mza=('latitud', 'mean'),
        lon_mza=('longitud', 'mean'),
        barrio=('barrio', lambda x: x.mode().iloc[0] if not x.mode().empty else 'S/D'),
        localidad=('localidad', lambda x: x.mode().iloc[0] if not x.mode().empty else 'S/D'),
        circ=('circ', 'first'),
        secc=('secc', 'first'),
        mza_wfs=('mza_wfs', 'first'),
        rutas_actuales=('ruta_actual', lambda x: list(x.unique()))
    ).reset_index()

    global_lat_mean = df['latitud'].mean()
    global_lon_mean = df['longitud'].mean()
    mza_stats['lat_fill'] = mza_stats['lat_mza'].fillna(global_lat_mean)
    mza_stats['lon_fill'] = mza_stats['lon_mza'].fillna(global_lon_mean)

    # Ordenamiento espacial continuo (Spatial Sweep)
    mza_stats = mza_stats.sort_values(by=['circ', 'secc', 'lat_fill', 'lon_fill']).reset_index(drop=True)

    # 3. Bin-Packing Espacial
    rutas_asignadas = []
    mza_to_route = {}
    mza_to_subdiv = {}

    route_id_seq = g_num * 1000 + 1  # Ejemplo: G1 -> 1001, G16 -> 16001, G20 -> 20001
    current_route_id = route_id_seq
    current_sumi_count = 0
    current_mzas = []

    for _, row in mza_stats.iterrows():
        mza_id = row['mza_13dig']
        cnt = row['cant_suministros']

        # Caso A: Macro-manzana individual (> 200 suministros)
        if cnt > MAX_CAPACITY:
            if current_sumi_count > 0:
                rutas_asignadas.append({
                    'nueva_ruta_lectura': current_route_id,
                    'grupo_lectura': g_str,
                    'cant_suministros': current_sumi_count,
                    'manzanas': current_mzas.copy()
                })
                for m in current_mzas:
                    mza_to_route[m] = current_route_id
                current_route_id += 1
                current_sumi_count = 0
                current_mzas = []

            # Subdividir macro-manzana internamente
            num_subrutas = int(np.ceil(cnt / TARGET_CAPACITY))
            mza_to_subdiv[mza_id] = {
                'num_subrutas': num_subrutas,
                'rutas': list(range(current_route_id, current_route_id + num_subrutas))
            }
            for sub_r in range(current_route_id, current_route_id + num_subrutas):
                rutas_asignadas.append({
                    'nueva_ruta_lectura': sub_r,
                    'grupo_lectura': g_str,
                    'cant_suministros': int(cnt / num_subrutas),
                    'manzanas': [mza_id]
                })
            current_route_id += num_subrutas
            continue

        # Caso B: Manzana normal
        if current_sumi_count + cnt <= MAX_CAPACITY:
            current_mzas.append(mza_id)
            current_sumi_count += cnt
            if current_sumi_count >= MIN_CAPACITY:
                rutas_asignadas.append({
                    'nueva_ruta_lectura': current_route_id,
                    'grupo_lectura': g_str,
                    'cant_suministros': current_sumi_count,
                    'manzanas': current_mzas.copy()
                })
                for m in current_mzas:
                    mza_to_route[m] = current_route_id
                current_route_id += 1
                current_sumi_count = 0
                current_mzas = []
        else:
            if current_sumi_count >= 120:
                rutas_asignadas.append({
                    'nueva_ruta_lectura': current_route_id,
                    'grupo_lectura': g_str,
                    'cant_suministros': current_sumi_count,
                    'manzanas': current_mzas.copy()
                })
                for m in current_mzas:
                    mza_to_route[m] = current_route_id
                current_route_id += 1
                current_mzas = [mza_id]
                current_sumi_count = cnt
            else:
                current_mzas.append(mza_id)
                current_sumi_count += cnt
                rutas_asignadas.append({
                    'nueva_ruta_lectura': current_route_id,
                    'grupo_lectura': g_str,
                    'cant_suministros': current_sumi_count,
                    'manzanas': current_mzas.copy()
                })
                for m in current_mzas:
                    mza_to_route[m] = current_route_id
                current_route_id += 1
                current_sumi_count = 0
                current_mzas = []

    if current_sumi_count > 0:
        rutas_asignadas.append({
            'nueva_ruta_lectura': current_route_id,
            'grupo_lectura': g_str,
            'cant_suministros': current_sumi_count,
            'manzanas': current_mzas.copy()
        })
        for m in current_mzas:
            mza_to_route[m] = current_route_id

    # 4. Mapear a nivel de cada suministro
    df['nueva_ruta_lectura'] = df['mza_13dig'].map(mza_to_route)

    # Resolver macro-manzanas
    for mza, sub_info in mza_to_subdiv.items():
        sub_rutas = sub_info['rutas']
        k = len(sub_rutas)
        mza_mask = (df['mza_13dig'] == mza)
        sub_indices = df[mza_mask].sort_values(by=['parc', 'altura', 'suministro']).index
        chunk_size = int(np.ceil(len(sub_indices) / k))
        for i, r_id in enumerate(sub_rutas):
            part_idx = sub_indices[i * chunk_size : min((i + 1) * chunk_size, len(sub_indices))]
            df.loc[part_idx, 'nueva_ruta_lectura'] = r_id

    df['nueva_ruta_lectura'] = df['nueva_ruta_lectura'].fillna(g_num * 1000 + 999).astype(int)

    # Orden correlativo de lectura por ruta
    df = df.sort_values(by=['nueva_ruta_lectura', 'mza_13dig', 'parc', 'calle', 'altura', 'suministro']).reset_index(drop=True)
    df['nuevo_orden_lectura'] = df.groupby('nueva_ruta_lectura').cumcount() + 1

    # Métricas y Resumen de Rutas de este grupo
    resumen_rutas_g = df.groupby('nueva_ruta_lectura').agg(
        grupo_lectura=('grupo_lectura', 'first'),
        cant_suministros=('suministro', 'count'),
        cant_manzanas=('mza_13dig', 'nunique'),
        barrios=('barrio', lambda x: ", ".join([str(b) for b in x.dropna().unique()[:3]])),
        localidad=('localidad', lambda x: x.mode().iloc[0] if not x.mode().empty else 'S/D'),
        circunscripciones=('circ', lambda x: ", ".join(x.unique())),
        secciones=('secc', lambda x: ", ".join(x.unique())),
        lat_centroide=('latitud', 'mean'),
        lon_centroide=('longitud', 'mean'),
        rutas_anteriores_involucradas=('ruta_actual', lambda x: len(x.unique()))
    ).reset_index()

    all_routes_summary.append(resumen_rutas_g)

    # Guardar campos clave de los suministros
    cols_keep = [
        'suministro', 'distrito', 'grupo_lectura', 'id_suministro_catastral',
        'dc_clean', 'mza_wfs', 'parc', 'calle', 'altura', 'barrio', 'localidad',
        'latitud', 'longitud', 'ruta_actual', 'orden_actual',
        'nueva_ruta_lectura', 'nuevo_orden_lectura'
    ]
    all_supplies_records.append(df[cols_keep])

    # Estadísticas consolidadas del grupo
    n_rutas_nuevas = len(resumen_rutas_g)
    media_sumi = resumen_rutas_g['cant_suministros'].mean()
    mediana_sumi = resumen_rutas_g['cant_suministros'].median()
    en_tolerancia = resumen_rutas_g['cant_suministros'].between(MIN_CAPACITY, MAX_CAPACITY).sum()
    pct_tolerancia = (en_tolerancia / n_rutas_nuevas * 100) if n_rutas_nuevas > 0 else 0

    t_end = time.time()
    print(f"[+] Grupo {g_str:>2}: {n_sumi:>6} sumi | {n_rutas_ant:>3} rutas ant -> {n_rutas_nuevas:>3} rutas nuevas | Media: {media_sumi:5.1f} | Tol [{MIN_CAPACITY}-{MAX_CAPACITY}]: {pct_tolerancia:5.1f}% | Tiempo: {t_end-t_start:.1f}s")

    all_groups_summary.append({
        'grupo_lectura': g_num,
        'cant_suministros': n_sumi,
        'cant_manzanas_unicas': len(mza_stats),
        'rutas_anteriores': n_rutas_ant,
        'rutas_nuevas': n_rutas_nuevas,
        'promedio_sumi_anterior': round(n_sumi / n_rutas_ant, 1),
        'promedio_sumi_nuevo': round(media_sumi, 1),
        'mediana_sumi_nuevo': int(mediana_sumi),
        'rutas_en_tolerancia': en_tolerancia,
        'pct_en_tolerancia': round(pct_tolerancia, 1)
    })

conn.close()

# 5. Consolidación Global
print("\n" + "=" * 110)
print("📊 CONSOLIDANDO ENTREGABLES GLOBALES DE DISTRITO 1...")
print("=" * 110)

df_all_routes = pd.concat(all_routes_summary, ignore_index=True)
df_all_groups = pd.DataFrame(all_groups_summary).sort_values(by='grupo_lectura').reset_index(drop=True)
df_all_supplies = pd.concat(all_supplies_records, ignore_index=True)

descargas = os.path.expanduser(r"~\Downloads")

# Archivo 1: Resumen de Grupos (Comparativo Antes vs Despues)
f_grupos = os.path.join(descargas, "resumen_comparativo_grupos_distrito1.csv")
df_all_groups.to_csv(f_grupos, index=False, encoding="utf-8-sig")
print(f"[+] Archivo 1 exportado: {f_grupos}")

# Archivo 2: Matriz Resumen de Todas las Nuevas Rutas de Distrito 1 (~3,500 rutas)
f_rutas = os.path.join(descargas, "resumen_todas_rutas_nuevas_distrito1.csv")
df_all_routes.to_csv(f_rutas, index=False, encoding="utf-8-sig")
print(f"[+] Archivo 2 exportado: {f_rutas}")

# Archivo 3: Padrón Completo Consolidado de Suministros Distrito 1
f_padron = os.path.join(descargas, "padron_nuevas_rutas_distrito1_completo.csv")
df_all_supplies.to_csv(f_padron, index=False, encoding="utf-8-sig")
print(f"[+] Archivo 3 exportado: {f_padron}")

total_time = time.time() - total_t0
print("\n" + "=" * 110)
print("🎯 RESUMEN FINAL DEL ESCALAMIENTO AL DISTRITO 1:")
print("=" * 110)
print(f"Total Suministros Procesados: {len(df_all_supplies):,}")
print(f"Total Nuevas Rutas Creadas:   {len(df_all_routes):,}")
print(f"Rutas Anteriores Reemplazadas: {df_all_groups['rutas_anteriores'].sum():,}")
print(f"Promedio Global Suministros/Ruta: {df_all_routes['cant_suministros'].mean():.1f}")
print(f"Cumplimiento en Rango [160, 200]: {df_all_routes['cant_suministros'].between(MIN_CAPACITY, MAX_CAPACITY).sum() / len(df_all_routes) * 100:.1f}%")
print(f"Tiempo Total de Ejecución: {total_time:.1f} segundos ({total_time/60:.2f} min)")
print("=" * 110)

print("\nTabla Comparativa por Grupo de Lectura:")
print(df_all_groups.to_string(index=False))
