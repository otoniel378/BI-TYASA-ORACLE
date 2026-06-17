"""
update_market_data.py — Actualiza datos de mercado en Oracle ADW.

Actualiza:
  - GOLD_VARIABLES_MERCADO: precios diarios desde yfinance (solo datos nuevos)
  - GOLD_QUIEBRES_DETECTADOS: re-calcula quiebres estructurales

Uso:
    python scripts/update_market_data.py
    python scripts/update_market_data.py --full   # recarga desde inicio
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import math
from datetime import datetime, timedelta
import numpy as np
import oracledb
from dotenv import load_dotenv

load_dotenv()

try:
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("Instala dependencias: pip install yfinance pandas")
    sys.exit(1)

TICKERS = {
    'BZ=F'    : ('Brent_USD',          'Energia'),
    'CL=F'    : ('WTI_USD',            'Energia'),
    'NG=F'    : ('Gas_HenryHub_USD',   'Energia'),
    'TTF=F'   : ('Gas_TTF_Europa',     'Energia'),
    'TIO=F'   : ('Mineral_Hierro',     'Insumos_Acero'),
    'HG=F'    : ('Cobre_USD',          'Insumos_Acero'),
    'ALI=F'   : ('Aluminio_USD',       'Insumos_Acero'),
    'SLX'     : ('ETF_Acero_Global',   'Sector_Acero'),
    'TX'      : ('Ternium_MX',         'Sector_Acero'),
    'MT'      : ('ArcelorMittal',      'Sector_Acero'),
    'NUE'     : ('Nucor_EAF',          'Sector_Acero'),
    'STLD'    : ('SteelDynamics_EAF',  'Sector_Acero'),
    'BDRY'    : ('ETF_Flete_Seco',     'Logistica'),
    'ZIM'     : ('ZIM_Contenedor',     'Logistica'),
    'MATX'    : ('Matson_Pacifico',    'Logistica'),
    'SBLK'    : ('StarBulk',           'Logistica'),
    '^VIX'    : ('VIX',                'Riesgo_Mercados'),
    '^GSPC'   : ('SP500',              'Riesgo_Mercados'),
    'GC=F'    : ('Oro_USD',            'Riesgo_Mercados'),
    'DX-Y.NYB': ('Dolar_Index',        'Riesgo_Mercados'),
    'TLT'     : ('Bonos_20y',          'Riesgo_Mercados'),
    '^N225'   : ('Nikkei_Japon',       'Asia'),
    '^KS11'   : ('KOSPI_Corea',        'Asia'),
    'FXI'     : ('ETF_China',          'Asia'),
    'EWJ'     : ('ETF_Japon',          'Asia'),
    'EWY'     : ('ETF_Corea',          'Asia'),
    'EWG'     : ('ETF_Alemania',       'Europa'),
    'EEM'     : ('ETF_Emergentes',     'Europa'),
    'EWW'     : ('ETF_Mexico',         'Mexico'),
    'MXN=X'   : ('USD_MXN',           'Mexico'),
}


def get_conn() -> oracledb.Connection:
    wallet_dir = os.environ.get("ORACLE_WALLET_DIR", "")
    params = {
        "user":     os.environ.get("ORACLE_USER", "ADMIN"),
        "password": os.environ.get("ORACLE_PASSWORD", ""),
        "dsn":      os.environ.get("ORACLE_DSN", ""),
    }
    if wallet_dir:
        params["config_dir"]      = wallet_dir
        params["wallet_location"] = wallet_dir
        wallet_pw = os.environ.get("ORACLE_WALLET_PASSWORD", "")
        if wallet_pw:
            params["wallet_password"] = wallet_pw
    return oracledb.connect(**params)


def get_max_fecha(conn: oracledb.Connection, ticker: str):
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT MAX(FECHA) FROM ADMIN.GOLD_VARIABLES_MERCADO WHERE TICKER = :1",
            [ticker]
        )
        row = cursor.fetchone()
        return row[0] if row and row[0] else None
    finally:
        cursor.close()


def update_variables(full: bool = False, batch_size: int = 5000):
    print("\nActualizando GOLD_VARIABLES_MERCADO...")
    conn = get_conn()
    ahora = datetime.utcnow()

    INSERT = """
        INSERT INTO ADMIN.GOLD_VARIABLES_MERCADO
            (FECHA, TICKER, NOMBRE, CATEGORIA, VALOR, CARGADO_EN)
        VALUES (:1,:2,:3,:4,:5,:6)
    """

    total_nuevas = 0
    for ticker, (nombre, categoria) in TICKERS.items():
        try:
            if full:
                start_date = "2024-01-01"
                c = conn.cursor()
                c.execute("DELETE FROM ADMIN.GOLD_VARIABLES_MERCADO WHERE TICKER = :1", [ticker])
                conn.commit()
                c.close()
            else:
                max_fecha = get_max_fecha(conn, ticker)
                if max_fecha:
                    start_date = (max_fecha + timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    start_date = "2024-01-01"

            today_str = datetime.utcnow().strftime("%Y-%m-%d")
            if start_date >= today_str:
                continue

            df_t = yf.download(ticker, start=start_date, progress=False, auto_adjust=True)
            if len(df_t) < 1:
                continue

            s = df_t["Close"].squeeze()
            if isinstance(s, pd.DataFrame):
                s = s.iloc[:, 0]
            s = s.dropna()

            rows = []
            for fecha, valor in s.items():
                v = float(valor)
                rows.append((
                    fecha.date(),
                    ticker,
                    nombre,
                    categoria,
                    None if np.isnan(v) else v,
                    ahora,
                ))

            if not rows:
                continue

            cursor = conn.cursor()
            try:
                for i in range(math.ceil(len(rows) / batch_size)):
                    cursor.executemany(INSERT, rows[i*batch_size:(i+1)*batch_size])
                    conn.commit()
                total_nuevas += len(rows)
                print(f"  +{len(rows)} {nombre}")
            finally:
                cursor.close()

        except Exception as e:
            print(f"  ERROR {nombre}: {e}")

    conn.close()
    print(f"  Total filas nuevas: {total_nuevas:,}")


def recalculate_quiebres():
    print("\nRecalculando quiebres estructurales...")
    try:
        from scipy import stats as sp_stats
    except ImportError:
        print("  scipy no instalado, omitiendo calculo de quiebres.")
        return

    conn = get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT NOMBRE, CATEGORIA, FECHA, VALOR
            FROM ADMIN.GOLD_VARIABLES_MERCADO
            WHERE FECHA >= SYSDATE - 400
            ORDER BY NOMBRE, FECHA
        """)
        rows = cursor.fetchall()
    finally:
        cursor.close()

    if not rows:
        conn.close()
        print("  Sin datos en GOLD_VARIABLES_MERCADO.")
        return

    df = pd.DataFrame(rows, columns=["NOMBRE", "CATEGORIA", "FECHA", "VALOR"])
    df["VALOR"] = pd.to_numeric(df["VALOR"], errors="coerce")
    df = df.dropna(subset=["VALOR"])

    nuevos = []
    ahora = datetime.utcnow().date()

    for nombre, grp in df.groupby("NOMBRE"):
        grp = grp.sort_values("FECHA").reset_index(drop=True)
        n = len(grp)
        if n < 40:
            continue

        categoria = grp["CATEGORIA"].iloc[0]
        valores = grp["VALOR"].values
        mejor_f, mejor_corte = 0.0, n // 2

        for cut in range(20, n - 20):
            f = abs(np.mean(valores[cut:]) - np.mean(valores[:cut])) / (np.std(valores) + 1e-9)
            if f > mejor_f:
                mejor_f, mejor_corte = f, cut

        a, b = valores[:mejor_corte], valores[mejor_corte:]
        media_pre  = float(np.mean(a))
        media_post = float(np.mean(b))
        sigma_val  = float(np.std(valores))
        cambio_pct = ((media_post - media_pre) / (abs(media_pre) + 1e-9)) * 100

        if len(a) > 1 and len(b) > 1:
            _, p_value = sp_stats.ttest_ind(a, b, equal_var=False)
        else:
            p_value = 1.0

        if abs(cambio_pct) < 5 or mejor_f < 1.0:
            continue

        sigma_n = abs(cambio_pct / 10.0)
        if sigma_n > 3.0:
            severidad = "Critico"
        elif sigma_n > 2.0:
            severidad = "Alto"
        else:
            severidad = "Moderado"

        fecha_corte = grp["FECHA"].iloc[mejor_corte]
        if hasattr(fecha_corte, 'date'):
            fecha_corte = fecha_corte.date()

        qid = f"auto_{nombre.replace(' ','_')}_{ahora}"
        nuevos.append((
            qid, nombre, categoria,
            fecha_corte, ahora,
            float(mejor_f), float(p_value), sigma_n,
            float(cambio_pct), media_pre, media_post, severidad, 1
        ))

    if not nuevos:
        conn.close()
        print("  Sin quiebres significativos.")
        return

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ADMIN.GOLD_QUIEBRES_DETECTADOS WHERE ID LIKE 'auto_%'")
        conn.commit()
        INSERT_Q = """
            INSERT INTO ADMIN.GOLD_QUIEBRES_DETECTADOS
                (ID, VARIABLE, CATEGORIA, FECHA_CORTE, FECHA_DETECT,
                 F_STAT, P_VALUE, SIGMA, CAMBIO_PCT, MEDIA_PRE, MEDIA_POST, SEVERIDAD, ACTIVO)
            VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13)
        """
        cursor.executemany(INSERT_Q, nuevos)
        conn.commit()
        print(f"  {len(nuevos)} quiebres actualizados.")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true",
                        help="Re-descarga todo desde 2024-01-01")
    args = parser.parse_args()

    update_variables(full=args.full)
    recalculate_quiebres()
    print("\nActualizacion de mercado completada.")
