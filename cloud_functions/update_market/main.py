"""
main.py — Cloud Function HTTP: actualización diaria de variables de mercado en Oracle ADW.

Cloud Scheduler llama a esta función cada día a las 8:45 AM México (14:45 UTC).
Hora elegida para que la BMV (abre 8:30 AM MX) ya tenga 15 min de datos frescos.

Variables de entorno requeridas:
  ORACLE_USER          — usuario Oracle (ADMIN)
  ORACLE_PASSWORD      — contraseña Oracle
  ORACLE_DSN           — nombre TNS (ej. tyasaadw_high)
  ORACLE_WALLET_B64    — wallet comprimido en ZIP y codificado en base64
  ORACLE_WALLET_PASSWORD — contraseña del wallet

Deploy:
  1. Genera ORACLE_WALLET_B64:
       PowerShell:
         $bytes = [IO.File]::ReadAllBytes("C:\\ruta\\wallet.zip")
         [Convert]::ToBase64String($bytes) | Set-Clipboard

  2. Despliega:
       gcloud functions deploy update-market-oracle \\
         --gen2 --runtime python311 --region us-central1 \\
         --source cloud_functions/update_market \\
         --entry-point update_market \\
         --trigger-http --no-allow-unauthenticated \\
         --memory 512MB --timeout 300s \\
         --set-env-vars ORACLE_USER=ADMIN,ORACLE_DSN=tyasaadw_high,\\
ORACLE_PASSWORD=TuPassword,ORACLE_WALLET_PASSWORD=TuWalletPassword,\\
ORACLE_WALLET_B64=TuBase64Aqui

  3. Actualiza (o crea) el trigger en Cloud Scheduler:
       # Actualizar job existente:
       gcloud scheduler jobs update http update-market-daily \\
         --schedule "45 14 * * 1-5" \\
         --location us-central1

       # O crear desde cero:
       gcloud scheduler jobs create http update-market-daily \\
         --schedule "45 14 * * 1-5" \\
         --uri "https://REGION-PROJECT.cloudfunctions.net/update-market-oracle" \\
         --http-method POST \\
         --oidc-service-account-email TU_SA@proyecto.iam.gserviceaccount.com \\
         --location us-central1
"""

import os
import base64
import zipfile
import tempfile
import warnings
import functions_framework
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

warnings.filterwarnings("ignore")

TICKERS = {
    "BZ=F"    : ("Brent_USD",          "Energia"),
    "CL=F"    : ("WTI_USD",            "Energia"),
    "NG=F"    : ("Gas_HenryHub_USD",   "Energia"),
    "TTF=F"   : ("Gas_TTF_Europa",     "Energia"),
    "TIO=F"   : ("Mineral_Hierro",     "Insumos_Acero"),
    "HG=F"    : ("Cobre_USD",          "Insumos_Acero"),
    "ALI=F"   : ("Aluminio_USD",       "Insumos_Acero"),
    "ZNC=F"   : ("Zinc_USD",           "Insumos_Acero"),
    "SLX"     : ("ETF_Acero_Global",   "Sector_Acero"),
    "TX"      : ("Ternium_MX",         "Sector_Acero"),
    "MT"      : ("ArcelorMittal",      "Sector_Acero"),
    "NUE"     : ("Nucor_EAF",          "Sector_Acero"),
    "STLD"    : ("SteelDynamics_EAF",  "Sector_Acero"),
    "BDRY"    : ("ETF_Flete_Seco",     "Logistica"),
    "ZIM"     : ("ZIM_Contenedor",     "Logistica"),
    "MATX"    : ("Matson_Pacifico",    "Logistica"),
    "SBLK"    : ("StarBulk",           "Logistica"),
    "^VIX"    : ("VIX",               "Riesgo_Mercados"),
    "^GSPC"   : ("SP500",             "Riesgo_Mercados"),
    "GC=F"    : ("Oro_USD",           "Riesgo_Mercados"),
    "DX-Y.NYB": ("Dolar_Index",       "Riesgo_Mercados"),
    "TLT"     : ("Bonos_20y",         "Riesgo_Mercados"),
    "^N225"   : ("Nikkei_Japon",      "Asia"),
    "^KS11"   : ("KOSPI_Corea",       "Asia"),
    "FXI"     : ("ETF_China",         "Asia"),
    "EWJ"     : ("ETF_Japon",         "Asia"),
    "EWY"     : ("ETF_Corea",         "Asia"),
    "CNY=X"   : ("USD_CNY",           "Asia"),
    "EWG"     : ("ETF_Alemania",      "Europa"),
    "EEM"     : ("ETF_Emergentes",    "Europa"),
    "EWW"     : ("ETF_Mexico",        "Mexico"),
    "MXN=X"   : ("USD_MXN",          "Mexico"),
    "EURMXN=X": ("EUR_MXN",          "Mexico"),
    "CX"      : ("CEMEX",            "Mexico"),
}

_WALLET_DIR = None


def _setup_wallet() -> str:
    """Extrae el wallet desde ORACLE_WALLET_B64 a /tmp y retorna la ruta."""
    global _WALLET_DIR
    if _WALLET_DIR and os.path.isdir(_WALLET_DIR):
        return _WALLET_DIR

    wallet_b64 = os.environ.get("ORACLE_WALLET_B64", "")
    if not wallet_b64:
        raise RuntimeError("Falta la variable de entorno ORACLE_WALLET_B64")

    tmp_dir = tempfile.mkdtemp(prefix="oracle_wallet_")
    zip_path = os.path.join(tmp_dir, "wallet.zip")

    with open(zip_path, "wb") as f:
        f.write(base64.b64decode(wallet_b64))

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(tmp_dir)

    _WALLET_DIR = tmp_dir
    return tmp_dir


def _get_conn():
    """Crea conexión Oracle usando el wallet extraído en /tmp."""
    import oracledb
    wallet_dir      = _setup_wallet()
    wallet_password = os.environ.get("ORACLE_WALLET_PASSWORD", "")
    return oracledb.connect(
        user            = os.environ.get("ORACLE_USER", "ADMIN"),
        password        = os.environ.get("ORACLE_PASSWORD", ""),
        dsn             = os.environ.get("ORACLE_DSN", "tyasaadw_high"),
        config_dir      = wallet_dir,
        wallet_location = wallet_dir,
        wallet_password = wallet_password,
    )


def _actualizar_precios(dias_atras: int = 10) -> dict:
    import yfinance as yf

    ahora  = datetime.now(timezone.utc)
    inicio = (ahora - timedelta(days=dias_atras)).strftime("%Y-%m-%d")
    rows, errores = [], []

    for ticker, (nombre, categoria) in TICKERS.items():
        try:
            df_t = yf.download(ticker, start=inicio, progress=False, auto_adjust=True)
            if df_t.empty:
                errores.append(f"{nombre}: sin datos")
                continue
            s = df_t["Close"].squeeze()
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = s.dropna()
            for fecha, valor in s.items():
                rows.append((
                    fecha.date(),
                    ticker,
                    nombre,
                    categoria,
                    float(valor) if not np.isnan(float(valor)) else None,
                    ahora,
                ))
        except Exception as e:
            errores.append(f"{nombre}: {e}")

    if not rows:
        return {"filas": 0, "errores": errores, "ultima_fecha": None}

    fechas_unicas = sorted({r[0] for r in rows})
    fechas_str    = ", ".join(f"DATE '{f}'" for f in fechas_unicas)

    conn = _get_conn()
    cur  = conn.cursor()

    # Upsert: borra las fechas descargadas y reinserta
    cur.execute(f"DELETE FROM ADMIN.GOLD_VARIABLES_MERCADO WHERE FECHA IN ({fechas_str})")

    cur.executemany(
        """INSERT INTO ADMIN.GOLD_VARIABLES_MERCADO
           (FECHA, TICKER, NOMBRE, CATEGORIA, VALOR, CARGADO_EN)
           VALUES (:1, :2, :3, :4, :5, :6)""",
        rows,
    )
    conn.commit()
    cur.close()
    conn.close()

    return {
        "filas":        len(rows),
        "errores":      errores,
        "ultima_fecha": str(max(fechas_unicas)),
    }


@functions_framework.http
def update_market(request):
    """Entry point HTTP para Cloud Functions / Cloud Scheduler."""
    try:
        resultado = _actualizar_precios(dias_atras=10)
        msg = (
            f"OK | filas={resultado['filas']} "
            f"| ultima={resultado['ultima_fecha']} "
            f"| errores={len(resultado['errores'])}"
        )
        print(msg)
        if resultado["errores"]:
            print("Errores:", resultado["errores"])
        return msg, 200
    except Exception as exc:
        import traceback
        err = traceback.format_exc()
        print(f"ERROR: {err}")
        return f"ERROR: {exc}", 500
