import os, time, oracledb, pandas as pd, numpy as np
from dotenv import load_dotenv

load_dotenv(r"D:\Proyectos\.env")
load_dotenv(r"D:\Proyectos\antigravity-agents-repository\.env")

lib_dir = os.environ.get("OR_INSTANT_CLIENT", r"C:\app\client\product\19.0.0\client_2\bin")
try:
    oracledb.init_oracle_client(lib_dir=lib_dir)
except Exception:
    pass

dsn = oracledb.makedsn(host=os.environ["OR_HOST"], port=int(os.environ.get("OR_PORT", 1521)), service_name=os.environ["OR_SERVICE_NAME"])
conn = oracledb.connect(user=os.environ["OR_USER"], password=os.environ["OR_PASS"], dsn=dsn)

query_all_g16 = """
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
WHERE distrito = 1 AND grupo_lectura = '16' AND dc IS NOT NULL AND LENGTH(TRIM(dc)) = 16
"""

print("[*] Descargando todos los suministros de Distrito 1, Grupo 16...")
t0 = time.time()
df = pd.read_sql(query_all_g16, conn)
t1 = time.time()
conn.close()
df.columns = [c.lower() for c in df.columns]
print(f"[+] Descargados {len(df)} suministros en {t1-t0:.2f} s.")

# 1. Descomposicion Catastral
df['dc_clean'] = df['dc'].astype(str).str.strip()
df['dpto'] = df['dc_clean'].str[0:2]
df['pedania'] = df['dc_clean'].str[2:4]
df['pueblo'] = df['dc_clean'].str[4:6]
df['circ'] = df['dc_clean'].str[6:8]
df['secc'] = df['dc_clean'].str[8:10]
df['mza'] = df['dc_clean'].str[10:13]
df['parc'] = df['dc_clean'].str[13:16]

df['dpp'] = df['dc_clean'].str[0:6]
df['mza_13dig'] = df['dc_clean'].str[0:13]
df['mza_wfs'] = df['dpto'] + '-' + df['pedania'] + '-' + df['pueblo'] + '-' + df['circ'] + '-' + df['secc'] + '-' + df['mza']
df['id_suministro_catastral'] = '1-16-' + df['mza_wfs'] + '-' + df['parc']

# 2. Agrupacion por Manzana Atómica
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

print(f"[+] Total Manzanas a agrupar: {len(mza_stats)}")

# 3. Algoritmo de Bin-Packing Espacial Colindante
# Prioridad: Ordenar por Circunscripcion, Seccion y coordenadas geograficas (Spatial Sweep)
mza_stats['lat_fill'] = mza_stats['lat_mza'].fillna(mza_stats['lat_mza'].mean())
mza_stats['lon_fill'] = mza_stats['lon_mza'].fillna(mza_stats['lon_mza'].mean())

mza_stats = mza_stats.sort_values(by=['circ', 'secc', 'lat_fill', 'lon_fill']).reset_index(drop=True)

TARGET_CAPACITY = 180
TOLERANCIA = 20
MIN_CAPACITY = TARGET_CAPACITY - TOLERANCIA  # 160
MAX_CAPACITY = TARGET_CAPACITY + TOLERANCIA  # 200

rutas_asignadas = []
mza_to_route = {}
mza_to_subdiv = {}

route_id_seq = 16001  # Nomenclatura oficial para Grupo 16: 16001, 16002...

current_route_id = route_id_seq
current_sumi_count = 0
current_mzas = []

for _, row in mza_stats.iterrows():
    mza_id = row['mza_13dig']
    cnt = row['cant_suministros']

    # Caso A: Macro-manzana individual que supera el maximo (ej. complejos de edificios/loteos)
    if cnt > MAX_CAPACITY:
        # Si habia una ruta abierta, cerrarla
        if current_sumi_count > 0:
            rutas_asignadas.append({
                'nueva_ruta_lectura': current_route_id,
                'cant_suministros': current_sumi_count,
                'manzanas': current_mzas.copy()
            })
            for m in current_mzas:
                mza_to_route[m] = current_route_id
            current_route_id += 1
            current_sumi_count = 0
            current_mzas = []

        # Particionar la macro-manzana en fragmentos de ~180 suministros
        num_subrutas = int(np.ceil(cnt / TARGET_CAPACITY))
        mza_to_subdiv[mza_id] = {
            'num_subrutas': num_subrutas,
            'rutas': list(range(current_route_id, current_route_id + num_subrutas))
        }
        for sub_r in range(current_route_id, current_route_id + num_subrutas):
            rutas_asignadas.append({
                'nueva_ruta_lectura': sub_r,
                'cant_suministros': int(cnt / num_subrutas),
                'manzanas': [mza_id]
            })
        current_route_id += num_subrutas
        continue

    # Caso B: Manzana normal -> Evaluar si entra en la ruta actual
    if current_sumi_count + cnt <= MAX_CAPACITY:
        current_mzas.append(mza_id)
        current_sumi_count += cnt
        # Si ya llego al rango optimo [160, 200], evaluar cierre
        if current_sumi_count >= MIN_CAPACITY:
            rutas_asignadas.append({
                'nueva_ruta_lectura': current_route_id,
                'cant_suministros': current_sumi_count,
                'manzanas': current_mzas.copy()
            })
            for m in current_mzas:
                mza_to_route[m] = current_route_id
            current_route_id += 1
            current_sumi_count = 0
            current_mzas = []
    else:
        # Si la ruta actual ya tenia masa critica (>= 120), cerrarla y abrir nueva
        if current_sumi_count >= 120:
            rutas_asignadas.append({
                'nueva_ruta_lectura': current_route_id,
                'cant_suministros': current_sumi_count,
                'manzanas': current_mzas.copy()
            })
            for m in current_mzas:
                mza_to_route[m] = current_route_id
            current_route_id += 1
            current_mzas = [mza_id]
            current_sumi_count = cnt
        else:
            # Forzar inclusion si la ruta venia muy vacia aunque supere levemente el maximo
            current_mzas.append(mza_id)
            current_sumi_count += cnt
            rutas_asignadas.append({
                'nueva_ruta_lectura': current_route_id,
                'cant_suministros': current_sumi_count,
                'manzanas': current_mzas.copy()
            })
            for m in current_mzas:
                mza_to_route[m] = current_route_id
            current_route_id += 1
            current_sumi_count = 0
            current_mzas = []

# Cerrar remanente final si quedo
if current_sumi_count > 0:
    rutas_asignadas.append({
        'nueva_ruta_lectura': current_route_id,
        'cant_suministros': current_sumi_count,
        'manzanas': current_mzas.copy()
    })
    for m in current_mzas:
        mza_to_route[m] = current_route_id

df_rutas_propuestas = pd.DataFrame(rutas_asignadas)
print(f"[+] Total Nuevas Rutas de Lectura generadas: {len(df_rutas_propuestas)}")
print("\nEstadisticas de Carga de las Nuevas Rutas:")
print(df_rutas_propuestas['cant_suministros'].describe())

cumplen_rango = df_rutas_propuestas['cant_suministros'].between(MIN_CAPACITY, MAX_CAPACITY).sum()
print(f"\nRutas dentro del rango de tolerancia [160, 200]: {cumplen_rango} de {len(df_rutas_propuestas)} ({cumplen_rango*100.0/len(df_rutas_propuestas):.1f}%)")

# 4. Asignar la nueva ruta y orden de lectura a nivel de cada suministro individual
print("[*] Asignando nuevas rutas y orden secuencial a cada suministro...")
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

df['nueva_ruta_lectura'] = df['nueva_ruta_lectura'].fillna(16999).astype(int)

# Asignar nuevo orden de lectura secuencial dentro de cada nueva ruta
df = df.sort_values(by=['nueva_ruta_lectura', 'mza_13dig', 'parc', 'calle', 'altura', 'suministro']).reset_index(drop=True)
df['nuevo_orden_lectura'] = df.groupby('nueva_ruta_lectura').cumcount() + 1

print("[+] Asignacion a nivel de suministro completada con exito.")

# 5. Exportar entregables
descargas = os.path.expanduser(r"~\Downloads")
csv_out = os.path.join(descargas, "propuesta_nuevas_rutas_distrito1_grupo16.csv")
cols_export = [
    'suministro', 'distrito', 'grupo_lectura', 'id_suministro_catastral',
    'dc_clean', 'mza_wfs', 'parc', 'calle', 'altura', 'barrio', 'localidad',
    'latitud', 'longitud', 'ruta_actual', 'orden_actual',
    'nueva_ruta_lectura', 'nuevo_orden_lectura'
]
df[cols_export].to_csv(csv_out, index=False, encoding="utf-8-sig")
print(f"[+] Archivo CSV completo exportado a: {csv_out}")

# Exportar tabla resumen de rutas propuestas
resumen_rutas_out = os.path.join(descargas, "resumen_rutas_propuestas_g16.csv")
resumen_rutas = df.groupby('nueva_ruta_lectura').agg(
    cant_suministros=('suministro', 'count'),
    cant_manzanas=('mza_13dig', 'nunique'),
    barrios=('barrio', lambda x: ", ".join([str(b) for b in x.dropna().unique()[:3]])),
    circunscripciones=('circ', lambda x: ", ".join(x.unique())),
    secciones=('secc', lambda x: ", ".join(x.unique())),
    lat_centroide=('latitud', 'mean'),
    lon_centroide=('longitud', 'mean'),
    rutas_anteriores_involucradas=('ruta_actual', lambda x: len(x.unique()))
).reset_index()

resumen_rutas.to_csv(resumen_rutas_out, index=False, encoding="utf-8-sig")
print(f"[+] Resumen de rutas exportado a: {resumen_rutas_out}")

# Mostrar las primeras 15 nuevas rutas
print("\n" + "="*110)
print("PRIMERAS 15 NUEVAS RUTAS DE LECTURA PROPUESTAS (DISTRITO 1, GRUPO 16):")
print("="*110)
print(resumen_rutas.head(15).to_string(index=False))
print("="*110)
