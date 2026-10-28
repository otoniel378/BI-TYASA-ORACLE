"""
scripts/update_semaforo_ferros.py — Recalcula el semáforo de alerta de alzas en
ferroaleaciones (mercado_fastmarkets/alerta_alzas.py) y lo guarda en Oracle
(GOLD_SEMAFORO_FERROS, GOLD_SEMAFORO_METRICAS; ver setup_semaforo_ferros_oracle.py).

Además deja memoria automática: si una serie queda en rojo o su último mes sale
del rango normal (rupturas.bandas_normales), registra un evento en
GOLD_EVENTOS_HISTORICOS con las noticias de ferroaleaciones del periodo y una
síntesis de Gemini — así el catálogo se va llenando solo con lo que pase de aquí
en adelante (para lo histórico no hay archivo de noticias confiable).

Correr después de cargar precios nuevos de Fastmarkets
(scripts/backfill_fastmarkets_historico.py). También corre mensual en
.github/workflows/update_semaforo_ferros.yml.

Uso:
    python scripts/update_semaforo_ferros.py
    python scripts/update_semaforo_ferros.py --sin-eventos     # no registra eventos automáticos
"""

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import numpy as np
import oracledb
import pandas as pd
from dotenv import load_dotenv

from mercado_fastmarkets.alerta_alzas import (
    AMARILLO, MERCADO_HUELLA_YF, cargar_externas, construir_panel, metricas, prediccion_actual, walk_forward,
)
from mercado_fastmarkets.loaders import FERROALEACIONES
from mercado_noticias.analytics.rupturas import TIPOS_IMPACTO, bandas_normales, normalizar_mensual
from mercado_noticias.loaders import PATRON_FERROALEACIONES

load_dotenv()

DESDE = "1995-01-01"
AUC_CONFIABLE, EPISODIOS_CONFIABLE = 0.65, 3   # por debajo, el semáforo se muestra como "señal débil"
DIAS_NOTICIAS_EVENTO = 30


def _get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        import tomllib
        cfg = tomllib.loads((_root / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
        return cfg.get("GEMINI_API_KEY", "")
    except Exception:
        return ""


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


def _cargar_precios(cursor) -> pd.DataFrame:
    simbolos = list(FERROALEACIONES)
    placeholders = ",".join(f":s{i}" for i in range(len(simbolos)))
    cursor.execute(f"""
        SELECT SYMBOL, FECHA, VALOR FROM ADMIN.BRONZE_FASTMARKETS_PRECIOS
        WHERE MEDIDA = 'Mid' AND TIPO = 'HISTORICO' AND SYMBOL IN ({placeholders})
    """, {f"s{i}": s for i, s in enumerate(simbolos)})
    df = pd.DataFrame(cursor.fetchall(), columns=["symbol", "fecha", "valor"])
    df["serie"] = df["symbol"].map(lambda s: FERROALEACIONES[s][0])
    df["valor"] = df["valor"].astype(float)
    ancho = normalizar_mensual(df[["fecha", "serie", "valor"]])
    return ancho[ancho.index >= DESDE]


def _nan_a_none(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v


def _guardar(conn, oos: pd.DataFrame, actual: pd.DataFrame, met: pd.DataFrame):
    cursor = conn.cursor()
    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
    cursor.execute("DELETE FROM ADMIN.GOLD_SEMAFORO_FERROS")
    cursor.execute("DELETE FROM ADMIN.GOLD_SEMAFORO_METRICAS")
    filas = [
        (r.serie, r.fecha.to_pydatetime(), "backtest", float(r.prob), None,
         _nan_a_none(float(r.alza_fut)), None if pd.isna(r.y) else int(r.y))
        for r in oos.itertuples()
    ] + [
        (r.serie, r.fecha.to_pydatetime(), "actual", float(r.prob), r.semaforo, None, None)
        for r in actual.itertuples()
    ]
    cursor.executemany("""
        INSERT INTO ADMIN.GOLD_SEMAFORO_FERROS (SERIE, FECHA, TIPO, PROB, SEMAFORO, ALZA_FUT, Y)
        VALUES (:1, :2, :3, :4, :5, :6, :7)
    """, filas)
    cursor.executemany("""
        INSERT INTO ADMIN.GOLD_SEMAFORO_METRICAS
            (SERIE, EPISODIOS, DETECTADOS, PCT_DETECTADOS, FALSAS_POR_ANIO, ACIERTAN, AUC, PROB_BASE, CONFIABLE)
        VALUES (:1, :2, :3, :4, :5, :6, :7, :8, :9)
    """, [
        (r.serie, int(r.episodios), int(r.detectados), _nan_a_none(r.pct_detectados),
         _nan_a_none(r.falsas_por_anio), _nan_a_none(r.aciertan), _nan_a_none(r.auc), _nan_a_none(r.prob_base),
         int(bool(r.auc >= AUC_CONFIABLE and r.episodios >= EPISODIOS_CONFIABLE)) if pd.notna(r.auc) else 0)
        for r in met.itertuples()
    ])
    conn.commit()
    cursor.close()
    print(f"  Guardadas {len(filas)} probabilidades y {len(met)} filas de métricas")


def _guardar_mercado_mensual(conn) -> None:
    """Reemplaza GOLD_MERCADO_MENSUAL con la historia mensual desde 2000 de las
    variables de la huella de impacto (pocos cientos de filas por variable)."""
    mercado = cargar_externas("2000-01-01", MERCADO_HUELLA_YF)
    if mercado.empty:
        print("  Aviso: sin datos de mercado (yfinance); GOLD_MERCADO_MENSUAL no se toca")
        return
    filas = [(f.to_pydatetime(), var, float(v))
             for var in mercado.columns for f, v in mercado[var].dropna().items()]
    cursor = conn.cursor()
    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
    cursor.execute("DELETE FROM ADMIN.GOLD_MERCADO_MENSUAL")
    cursor.executemany("INSERT INTO ADMIN.GOLD_MERCADO_MENSUAL (FECHA, VARIABLE, VALOR) VALUES (:1, :2, :3)", filas)
    conn.commit()
    cursor.close()
    print(f"  Mercado mensual: {len(filas)} filas ({', '.join(mercado.columns)})")


def _noticias_ferro(cursor, hasta: datetime) -> list[tuple]:
    cursor.execute("""
        SELECT TITULO, RAZON, URL FROM ADMIN.GOLD_SENTIMIENTO_NOTICIAS
        WHERE FECHA_PUB BETWEEN :desde AND :hasta
          AND (VARIABLE_PRINCIPAL = 'ferroaleaciones' OR REGEXP_LIKE(TITULO, :patron, 'i'))
        ORDER BY FECHA_PUB DESC
        FETCH FIRST 8 ROWS ONLY
    """, {"desde": hasta - timedelta(days=DIAS_NOTICIAS_EVENTO), "hasta": hasta, "patron": PATRON_FERROALEACIONES})
    return cursor.fetchall()


def _sintetizar(serie: str, motivo: str, noticias: list[tuple], api_key: str) -> tuple[str, str, str | None]:
    """(nombre, descripcion, tipo_impacto). Sin Gemini o si no responde en formato,
    se guarda la descripción estadística y tipo None (la página usa entonces la
    huella de mercado): mejor registrar algo que perder el evento."""
    nombre_fb = f"{serie}: {motivo}"
    desc_fb = f"Señal automática en {serie}: {motivo}."
    if not api_key:
        return nombre_fb, desc_fb, None
    contexto = "; ".join(f"{t} ({r})" for t, r, _ in noticias[:6]) or "sin noticias de ferroaleaciones en el periodo"
    prompt = (
        f"El precio de {serie} (Fastmarkets/LME) muestra: {motivo}. Noticias recientes: {contexto}. "
        "Para TYASA (acería mexicana de horno eléctrico que compra ferroaleaciones), explica la causa probable "
        "solo con base en esas noticias; si no la explican, dilo. Responde EXACTAMENTE en este formato:\n"
        "NOMBRE: <máximo 8 palabras>\nDESCRIPCION: <máximo 2 frases>\n"
        f"TIPO: <uno de: {' | '.join(TIPOS_IMPACTO)} | Sin determinar>"
    )
    try:
        from mercado_noticias.analytics.ai_analysis import _call_gemini_text
        resp = _call_gemini_text(prompt, api_key, max_output_tokens=220, temperature=0.3)
        m_n = re.search(r"NOMBRE:\s*(.+)", resp)
        m_d = re.search(r"DESCRIPCION:\s*(.+?)(?:\nTIPO:|$)", resp, re.DOTALL)
        m_t = re.search(r"TIPO:\s*(.+)", resp)
        tipo = m_t.group(1).strip() if m_t else None
        return ((m_n.group(1).strip() if m_n else nombre_fb)[:200],
                (m_d.group(1).strip() if m_d else desc_fb)[:2000],
                tipo if tipo in TIPOS_IMPACTO else None)
    except Exception as e:
        print(f"  Aviso: Gemini no respondió ({e}); se guarda descripción estadística")
        return nombre_fb, desc_fb, None


def _registrar_eventos(conn, precios: pd.DataFrame, actual: pd.DataFrame, api_key: str):
    cursor = conn.cursor()
    cursor.execute("ALTER SESSION DISABLE PARALLEL DML")
    n = 0
    for r in actual.itertuples():
        bandas = bandas_normales(precios[r.serie].dropna())
        ult = bandas.iloc[-1]
        motivos = []
        if r.semaforo == "Rojo":
            motivos.append(f"alerta roja, {r.prob:.0%} de probabilidad de subir más de 20% en 3 meses")
        if ult["fuera"]:
            lado = "por arriba" if ult["precio"] > ult["banda_sup"] else "por abajo"
            motivos.append(f"precio fuera de su rango normal ({lado})")
        if not motivos:
            continue
        mes = bandas.index[-1]
        noticias = _noticias_ferro(cursor, datetime.now())
        nombre, descripcion, tipo = _sintetizar(r.serie, " y ".join(motivos), noticias, api_key)
        fuente = "; ".join(u for _, _, u in noticias) or "Detección automática del semáforo de ferroaleaciones"
        cursor.execute("""
            MERGE INTO ADMIN.GOLD_EVENTOS_HISTORICOS t
            USING (SELECT :id AS ID FROM dual) s ON (t.ID = s.ID)
            WHEN MATCHED THEN UPDATE SET
                FECHA_FIN = :fecha, NOMBRE = :nombre, DESCRIPCION = :descripcion,
                VARIABLES_RELACIONADAS = :serie, FUENTE = :fuente, TIPO_IMPACTO = :tipo
            WHEN NOT MATCHED THEN INSERT
                (ID, FECHA_INICIO, FECHA_FIN, NOMBRE, DESCRIPCION, VARIABLES_RELACIONADAS, FUENTE, TIPO_IMPACTO)
                VALUES (:id, :fecha, :fecha, :nombre, :descripcion, :serie, :fuente, :tipo)
        """, {"id": f"auto_ferro_{r.serie}_{mes:%Y%m}", "fecha": mes.to_pydatetime(), "nombre": nombre,
              "descripcion": descripcion, "serie": r.serie, "fuente": fuente[:500], "tipo": tipo})
        conn.commit()
        n += 1
        print(f"  Evento automático {r.serie} {mes:%Y-%m}: {nombre}")
    cursor.close()
    print(f"  {n} eventos automáticos registrados")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sin-eventos", action="store_true", help="No registra eventos automáticos")
    args = parser.parse_args()

    conn = get_conn()
    try:
        precios = _cargar_precios(conn.cursor())
        print(f"Precios: {precios.shape[1]} series, {precios.index.min():%Y-%m} a {precios.index.max():%Y-%m}")
        externas = cargar_externas()
        print(f"Variables externas: {list(externas.columns)}")
        panel = construir_panel(precios, externas)
        oos = walk_forward(panel)
        met = metricas(oos, AMARILLO)
        actual = prediccion_actual(panel)
        tot = met[met["serie"] == "Total"].iloc[0]
        print(f"Validación: {int(tot.detectados)}/{int(tot.episodios)} alzas detectadas a tiempo, "
              f"{tot.falsas_por_anio:.2f} falsas alarmas por serie al año, AUC {tot.auc:.2f}")
        print(actual.round(3).to_string(index=False))
        _guardar(conn, oos, actual, met)
        _guardar_mercado_mensual(conn)
        if not args.sin_eventos:
            _registrar_eventos(conn, precios, actual, _get_gemini_key())
    finally:
        conn.close()


if __name__ == "__main__":
    main()
