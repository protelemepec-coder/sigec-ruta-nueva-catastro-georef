import os
import sys
import time
import io
import re
import requests
import urllib3
import pandas as pd
import numpy as np

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 110)
print("🚀 DESCARGA DE CAPA WFS Y AUDITORÍA DE CONTROL CRUZADO AUTOMATIZADA EN TODO EL PADRÓN (DISTRITO 1)")
print("=" * 110)

# 1. Descarga completa de la capa WFS EPEC:vm_manzanas_calles_new
url = "https://maaysp-ws.cba.gov.ar/EPEC/wfs"
auth = ("EPEC_comercial", "Bratis-c0m3rc14l")
params = {
    "service": "WFS",
    "version": "1.1.0",
    "request": "GetFeature",
    "typeName": "EPEC:vm_manzanas_calles_new",
    "maxFeatures": 350000,
    "outputFormat": "csv",
    "propertyName": "nomenclatura,nombrecall,tipo"
}

print("[*] Descargando capa completa EPEC:vm_manzanas_calles_new desde el geoservicio WFS...")
t0 = time.time()
resp = requests.get(url, auth=auth, params=params, verify=False, timeout=120)
if resp.status_code != 200:
    print(f"[-] Error al descargar WFS: Status {resp.status_code}")
    sys.exit(1)

t1 = time.time()
print(f"[+] Descarga completada en {t1 - t0:.2f} s. Tamaño recibido: {len(resp.content) / (1024 * 1024):.2f} MB")

# Cargar CSV en DataFrame
df_wfs = pd.read_csv(io.StringIO(resp.text))
df_wfs = df_wfs.dropna(subset=['nomenclatura', 'nombrecall'])
df_wfs['nomenclatura'] = df_wfs['nomenclatura'].astype(str).str.strip()
df_wfs['nombrecall'] = df_wfs['nombrecall'].astype(str).str.strip().str.upper()

# Eliminar duplicados exactos (nomenclatura, nombrecall)
df_wfs_unique = df_wfs[['nomenclatura', 'nombrecall', 'tipo']].drop_duplicates().reset_index(drop=True)
print(f"[+] Total registros WFS únicos (manzana-calle): {len(df_wfs_unique):,} correspondientes a {df_wfs_unique['nomenclatura'].nunique():,} manzanas catastrales.")

# Guardar copia local en formatos eficientes
descargas = os.path.expanduser(r"~\Downloads")
repo_data = r"D:\Proyectos\antigravity-agents-repository\data"
os.makedirs(repo_data, exist_ok=True)

# Formato 1: CSV para uso directo del usuario
wfs_csv_path = os.path.join(descargas, "EPEC_vm_manzanas_calles_new.csv")
df_wfs_unique.to_csv(wfs_csv_path, index=False, encoding="utf-8-sig")
print(f"[+] Capa guardada en CSV: {wfs_csv_path}")

# Formato 2: Parquet para máxima eficiencia analítica
wfs_parquet_path = os.path.join(repo_data, "vm_manzanas_calles_new.parquet")
df_wfs_unique.to_parquet(wfs_parquet_path, index=False)
print(f"[+] Capa guardada en Parquet de alta velocidad: {wfs_parquet_path}")

# 2. Construir Diccionario Indexado de Manzanas y Calles Perimetrales
print("\n[*] Construyendo índice y motor de tokens de calles perimetrales...")
STOPWORDS_CALLES = {'CALLE', 'AVENIDA', 'AV', 'BV', 'BOULEVARD', 'PASAJE', 'PJE', 'PJE.', 'DE', 'DEL', 'LA', 'LAS', 'LOS', 'EL', 'Y', 'SAN', 'SANTA'}

def clean_street(s):
    # Eliminar puntos, comas y múltiples espacios
    s = re.sub(r'[^\w\s]', ' ', s.upper())
    return ' '.join(s.split())

def extract_tokens(s):
    cleaned = clean_street(s)
    tokens = set([t for t in cleaned.split() if len(t) > 2 and t not in STOPWORDS_CALLES])
    return tokens

# Agrupar por manzana
wfs_dict = {}
grouped = df_wfs_unique.groupby('nomenclatura')['nombrecall'].unique()

for mza_nom, calles_arr in grouped.items():
    calles_list = [c for c in calles_arr if c]
    calles_clean_list = [clean_street(c) for c in calles_list]
    
    # Mapeo de tokens a calle original
    token_to_street = {}
    for c_orig in calles_list:
        for t in extract_tokens(c_orig):
            if t not in token_to_street:
                token_to_street[t] = c_orig
                
    wfs_dict[mza_nom] = {
        'calles_raw': calles_list,
        'calles_clean': set(calles_clean_list),
        'calles_str': '; '.join(calles_list),
        'cant_calles': len(calles_list),
        'tokens': set(token_to_street.keys()),
        'token_map': token_to_street
    }

print(f"[+] Índice en memoria optimizado para {len(wfs_dict):,} manzanas catastrales.")

# 3. Cargar el Padrón Completo de Distrito 1 (585,472 suministros)
padron_path = os.path.join(descargas, "padron_nuevas_rutas_distrito1_completo.csv")
print(f"\n[*] Cargando padrón completo desde: {padron_path}...")
t_load0 = time.time()
df_padron = pd.read_csv(padron_path, low_memory=False)
t_load1 = time.time()
print(f"[+] Padrón cargado ({len(df_padron):,} suministros) en {t_load1 - t_load0:.2f} s.")

# 4. Auditoría de Control Cruzado Automatizada sobre los 585.472 suministros
print("\n[*] Ejecutando auditoría cruzada suministro por suministro...")
t_aud0 = time.time()

n_rows = len(df_padron)
tiene_wfs_col = ['NO'] * n_rows
cant_calles_col = [0] * n_rows
calles_perimetro_col = [''] * n_rows
coincide_col = ['SIN_COBERTURA_WFS'] * n_rows
tipo_coincidencia_col = ['SIN_COBERTURA_WFS'] * n_rows
calle_detectada_col = [''] * n_rows

mza_series = df_padron['mza_wfs'].astype(str).values
calle_series = df_padron['calle'].fillna('').astype(str).values

for i in range(n_rows):
    mza_val = mza_series[i]
    calle_val = calle_series[i]
    
    mza_info = wfs_dict.get(mza_val)
    if not mza_info:
        continue
        
    tiene_wfs_col[i] = 'SI'
    cant_calles_col[i] = mza_info['cant_calles']
    calles_perimetro_col[i] = mza_info['calles_str']
    
    calle_clean = clean_street(calle_val)
    if not calle_clean:
        coincide_col[i] = 'NO'
        tipo_coincidencia_col[i] = 'CALLE_VACIA_EN_SUMINISTRO'
        continue
        
    # Nivel 1: Coincidencia Exacta o Subcadena
    matched_exact = False
    for c_clean in mza_info['calles_clean']:
        if calle_clean == c_clean or calle_clean in c_clean or c_clean in calle_clean:
            coincide_col[i] = 'SI'
            tipo_coincidencia_col[i] = 'EXACTA_O_CONTENIDA'
            calle_detectada_col[i] = c_clean
            matched_exact = True
            break
            
    if matched_exact:
        continue
        
    # Nivel 2: Coincidencia por Intersección de Tokens Relevantes
    sumi_tokens = extract_tokens(calle_clean)
    common_tokens = sumi_tokens & mza_info['tokens']
    if common_tokens:
        first_token = sorted(list(common_tokens), key=len, reverse=True)[0]
        coincide_col[i] = 'SI'
        tipo_coincidencia_col[i] = 'TOKEN_COINCIDENTE'
        calle_detectada_col[i] = mza_info['token_map'].get(first_token, first_token)
    else:
        coincide_col[i] = 'NO'
        tipo_coincidencia_col[i] = 'DISCREPANCIA_CALLE'

t_aud1 = time.time()
print(f"[+] Auditoría de 585.472 suministros completada en {t_aud1 - t_aud0:.2f} s ({len(df_padron)/(t_aud1 - t_aud0):,.0f} sum/s).")

# 5. Asignar columnas auditadas al DataFrame
df_padron['tiene_calles_wfs'] = tiene_wfs_col
df_padron['cant_calles_wfs'] = cant_calles_col
df_padron['calles_perimetro_wfs'] = calles_perimetro_col
df_padron['coincide_calle_perimetro'] = coincide_col
df_padron['tipo_coincidencia'] = tipo_coincidencia_col
df_padron['calle_wfs_detectada'] = calle_detectada_col

# 6. Estadísticas Globales de la Auditoría
total_sumi = len(df_padron)
con_wfs = (df_padron['tiene_calles_wfs'] == 'SI').sum()
sin_wfs = total_sumi - con_wfs
coinciden_si = (df_padron['coincide_calle_perimetro'] == 'SI').sum()
discrepancias = (df_padron['coincide_calle_perimetro'] == 'NO').sum()

pct_wfs = con_wfs / total_sumi * 100
pct_coincide_sobre_wfs = coinciden_si / con_wfs * 100 if con_wfs > 0 else 0
pct_coincide_global = coinciden_si / total_sumi * 100

print("\n" + "=" * 110)
print("🎯 RESULTADOS FINALES DE LA AUDITORÍA DE CALLES WFS EN TODO EL PADRÓN (DISTRITO 1)")
print("=" * 110)
print(f"Total Suministros Auditados:               {total_sumi:>10,}")
print(f"Suministros con Manzana Digitalizada WFS:  {con_wfs:>10,} ({pct_wfs:5.1f}%)")
print(f"Suministros sin Cobertura WFS (rural/borde):{sin_wfs:>10,} ({sin_wfs/total_sumi*100:5.1f}%)")
print(f"Dirección Confirmada en Perímetro Manzana: {coinciden_si:>10,} ({pct_coincide_global:5.1f}% global | {pct_coincide_sobre_wfs:5.1f}% de las con WFS)")
print(f"Discrepancias Toponímicas / Esquinas:      {discrepancias:>10,} ({discrepancias/con_wfs*100:5.1f}% de las con WFS)")
print("=" * 110)

print("\nDesglose por Tipo de Coincidencia:")
print(df_padron['tipo_coincidencia'].value_counts().to_string())

# 7. Resumen por Grupo de Lectura
resumen_grupos = df_padron.groupby('grupo_lectura').agg(
    total_suministros=('suministro', 'count'),
    con_wfs=('tiene_calles_wfs', lambda x: (x == 'SI').sum()),
    coinciden_perimetro=('coincide_calle_perimetro', lambda x: (x == 'SI').sum()),
    discrepancias=('coincide_calle_perimetro', lambda x: (x == 'NO').sum()),
    sin_cobertura_wfs=('coincide_calle_perimetro', lambda x: (x == 'SIN_COBERTURA_WFS').sum())
).reset_index()

resumen_grupos['pct_cobertura_wfs'] = (resumen_grupos['con_wfs'] / resumen_grupos['total_suministros'] * 100).round(1)
resumen_grupos['pct_coincidencia_sobre_wfs'] = (resumen_grupos['coinciden_perimetro'] / resumen_grupos['con_wfs'] * 100).round(1)
resumen_grupos['pct_coincidencia_global'] = (resumen_grupos['coinciden_perimetro'] / resumen_grupos['total_suministros'] * 100).round(1)

# Ordenar por grupo
resumen_grupos['g_num'] = pd.to_numeric(resumen_grupos['grupo_lectura'], errors='coerce')
resumen_grupos = resumen_grupos.sort_values(by='g_num').drop(columns=['g_num']).reset_index(drop=True)

print("\nResumen de Auditoría por Grupo de Lectura:")
print(resumen_grupos[['grupo_lectura', 'total_suministros', 'con_wfs', 'pct_cobertura_wfs', 'coinciden_perimetro', 'pct_coincidencia_sobre_wfs', 'discrepancias']].to_string(index=False))

# 8. Exportar Entregables Finales en .CSV
print("\n" + "=" * 110)
print("💾 EXPORTANDO ENTREGABLES FINALES EN FORMATO .CSV...")
print("=" * 110)

# Archivo A: Padrón Completo Auditado con Columnas de Control WFS
padron_auditado_csv = os.path.join(descargas, "padron_distrito1_auditado_calles_wfs.csv")
print(f"[*] Escribiendo {padron_auditado_csv}...")
df_padron.to_csv(padron_auditado_csv, index=False, encoding="utf-8-sig")
print(f"[+] Archivo Padrón Auditado CSV generado exitosamente ({os.path.getsize(padron_auditado_csv)/(1024*1024):.2f} MB).")

# Archivo B: Resumen de Auditoría por Grupo en CSV
resumen_grupos_csv = os.path.join(descargas, "resumen_auditoria_calles_wfs_por_grupo.csv")
resumen_grupos.to_csv(resumen_grupos_csv, index=False, encoding="utf-8-sig")
print(f"[+] Archivo Resumen por Grupo CSV generado exitosamente: {resumen_grupos_csv}")

print("\n" + "=" * 110)
print("✅ PROCESO COMPLETO FINALIZADO CON ÉXITO.")
print("=" * 110)
