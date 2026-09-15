"""
main.py — Cloud Function HTTP trigger para descarga mensual de indicadores INEGI.
Cloud Scheduler llama a esta función el día 1 de cada mes a las 8:00 AM México (14:00 UTC).

Deploy:
    gcloud functions deploy update-inegi-monthly \
        --gen2 --runtime python311 --region us-central1 \
        --source cloud_functions/update_inegi \
        --entry-point update_inegi \
        --trigger-http --no-allow-unauthenticated \
        --memory 512MB --timeout 300s \
        --set-env-vars PROJECT_ID=project-d0cf2519-d089-47d3-930,DATASET=tyasa_bi,INEGI_TOKEN=2840789b-d1ee-af89-6433-8d1f8a509bf9

Scheduler (ejecutar después del deploy):
    gcloud scheduler jobs create http inegi-monthly-update \
        --location us-central1 \
        --schedule "0 14 1 * *" \
        --uri "$(gcloud functions describe update-inegi-monthly --gen2 --region us-central1 --format='value(serviceConfig.uri)')" \
        --http-method POST \
        --oidc-service-account-email "$(gcloud iam service-accounts list --format='value(email)' --filter='displayName:Default')"
"""

import os
import time
import warnings
from datetime import datetime

import functions_framework
import pandas as pd
import requests
from google.cloud import bigquery

warnings.filterwarnings("ignore")

PROJECT_ID   = os.environ.get("PROJECT_ID",   "project-d0cf2519-d089-47d3-930")
DATASET      = os.environ.get("DATASET",      "tyasa_bi")
INEGI_TOKEN  = os.environ.get("INEGI_TOKEN",  "")
TABLE_FULL   = f"{PROJECT_ID}.{DATASET}.gold_indicadores_inegi"
STAGING_FULL = f"{PROJECT_ID}.{DATASET}._staging_inegi"
BIE_BASE     = "https://www.inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml"
BATCH_SIZE   = 20

INDICADORES = {
    # ── ACTIVIDAD INDUSTRIAL (IMAI) ───────────────────────────────────────────
    "736407": "IMAI_ActividadIndustrial_Indice",
    "736418": "IMAI_Manufactureras_Indice",
    "736414": "IMAI_Construccion_Indice",
    "736475": "IMAI_MetalicasBasicas_331_Indice",
    "736476": "IMAI_HierroAcero_3311_Indice",
    "736481": "IMAI_ProductosMetalicos_332_Indice",
    "736491": "IMAI_MaquinariaEquipo_333_Indice",
    "736526": "IMAI_ActividadIndustrial_VarAnual",
    "736533": "IMAI_Construccion_VarAnual",
    "736594": "IMAI_MetalicasBasicas_331_VarAnual",
    # ── EMIM ─────────────────────────────────────────────────────────────────
    "910468": "EMIM_VolFisico_Desest_Indice",
    "910470": "EMIM_VolFisico_Desest_VarAnual",
    # ── ENEC ─────────────────────────────────────────────────────────────────
    "720332": "ENEC_ValorProd_ObraTotal",
    "720334": "ENEC_ValorProd_Edificacion",
    "720340": "ENEC_ValorProd_Transporte_Urb",
    # ── EMEC ─────────────────────────────────────────────────────────────────
    "718504": "EMEC_Ingresos_ComercioMayor_43",
    "718506": "EMEC_Ingresos_ComercioMenor_46",
    # ── IGAE ─────────────────────────────────────────────────────────────────
    "737173": "IGAE_Secundario_Indice",
    "737149": "IGAE_Secundario_VarAnual",
    # ── BALANZA COMERCIAL SIDERURGIA ──────────────────────────────────────────
    "133094": "BC_Siderurgia_Importaciones",
    "133031": "BC_Siderurgia_Exportaciones",
    # ── INPP ─────────────────────────────────────────────────────────────────
    "910503": "INPP_Manufactura_3133",
    "910502": "INPP_Construccion_23",
    "910501": "INPP_Energia_22",
    "910500": "INPP_Mineria_SinPetroleo",
    "910499": "INPP_Mineria_ConPetroleo",
    "910491": "INPP_SinPetroleo_ConServicios",
    # ── INPC ─────────────────────────────────────────────────────────────────
    "910396": "INPC_Total_Mensual",
    "909294": "INPC_Energeticos_NoSubyacente",
    "910398": "INPC_Energeticos_Gobierno",
    "910393": "INPC_Subyacente_Total",
    # ── IFB ──────────────────────────────────────────────────────────────────
    "741034": "IFB_Construccion",
    "741030": "IFB_Maquinaria_Importada",
    "741025": "IFB_Maquinaria_Nacional",
    # ── CONFIANZA ─────────────────────────────────────────────────────────────
    "701407": "ICE_Construccion",
    "701401": "ICE_Global",
    "334497": "ICC_Confianza_Consumidor",
}


def _fetch_batch(ids: list, token: str) -> list:
    url = f"{BIE_BASE}/INDICATOR/{','.join(ids)}/es/0700/false/BIE/2.0/{token}.json"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [ERROR] Error batch {ids[:2]}: {e}")
        return []

    rows = []
    for serie in data.get("Series", []):
        clave  = str(serie.get("INDICADOR", ""))
        nombre = INDICADORES.get(clave, serie.get("NOMBRE_IND", clave))
        for obs in serie.get("OBS", []):
            periodo = obs.get("PERIODO", "")
            val_str = obs.get("OBS_VALUE", "N/E")
            if "/" not in periodo:
                continue
            year, sub = periodo.split("/", 1)
            if sub.startswith("T"):
                fecha = f"{year}-{(int(sub[1]) - 1) * 3 + 1:02d}"
            else:
                try:
                    fecha = f"{year}-{int(sub):02d}"
                except ValueError:
                    continue
            try:
                valor = float(val_str) if val_str not in ("N/E", "", "N/A", "null") else None
            except ValueError:
                valor = None
            if valor is None:
                continue
            rows.append({"Fecha": fecha, "Clave": clave, "Nombre": nombre, "Valor": valor})
    return rows


def _upsert(client: bigquery.Client, rows: list) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    job_cfg = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=[
            bigquery.SchemaField("Fecha",  "STRING"),
            bigquery.SchemaField("Clave",  "STRING"),
            bigquery.SchemaField("Nombre", "STRING"),
            bigquery.SchemaField("Valor",  "FLOAT64"),
        ],
    )
    client.load_table_from_dataframe(df, STAGING_FULL, job_config=job_cfg).result()
    client.query(f"""
        MERGE `{TABLE_FULL}` T
        USING `{STAGING_FULL}` S
        ON T.Clave = S.Clave AND T.Fecha = S.Fecha
        WHEN MATCHED THEN
            UPDATE SET Nombre = S.Nombre, Valor = S.Valor, Actualizado = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN
            INSERT (Fecha, Clave, Nombre, Valor, Actualizado)
            VALUES (S.Fecha, S.Clave, S.Nombre, S.Valor, CURRENT_TIMESTAMP())
    """).result()
    client.delete_table(STAGING_FULL, not_found_ok=True)
    return len(rows)


@functions_framework.http
def update_inegi(request):
    """Entry point — Cloud Scheduler llama el día 1 de cada mes."""
    if not INEGI_TOKEN:
        msg = "ERROR: variable de entorno INEGI_TOKEN no configurada"
        print(msg)
        return msg, 500

    client = bigquery.Client(project=PROJECT_ID)
    ids    = list(INDICADORES.keys())
    batches = [ids[i:i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]

    all_rows = []
    errores  = []
    for i, batch in enumerate(batches, 1):
        rows = _fetch_batch(batch, INEGI_TOKEN)
        if rows:
            all_rows.extend(rows)
        else:
            errores.extend(batch)
        if i < len(batches):
            time.sleep(1)

    try:
        insertadas = _upsert(client, all_rows)
    except Exception as e:
        msg = f"ERROR upsert BigQuery: {e}"
        print(msg)
        return msg, 500

    msg = (
        f"OK | indicadores={len(INDICADORES)} "
        f"| registros={insertadas} "
        f"| errores_ids={len(errores)} "
        f"| fecha={datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
    )
    print(msg)
    if errores:
        print("IDs con error:", errores)
    return msg, 200
