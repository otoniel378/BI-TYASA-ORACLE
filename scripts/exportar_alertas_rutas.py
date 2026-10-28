"""
scripts/exportar_alertas_rutas.py — Genera los avisos por ruta del "Monitor
materiales críticos" a partir de las noticias clasificadas en Oracle
(mercado_noticias/analytics/rutas_alertas.py) y los deja en un JSON listo para
escribir en la colección alertas_noticias del monitor (un documento por id).

Uso:
    python scripts/exportar_alertas_rutas.py                 # -> alertas_rutas.json
    python scripts/exportar_alertas_rutas.py --salida x.json --dias 21
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from core.db_connector import run_query_params, table_ref  # noqa: E402
from mercado_noticias.analytics.rutas_alertas import DIAS_VIGENCIA, alertas_rutas  # noqa: E402


def _noticias(dias: int) -> pd.DataFrame:
    df = run_query_params(f"""
        SELECT FECHA_PUB, TITULO, FUENTE, URL, VARIABLE_PRINCIPAL, GRUPO_TEMATICO, RAZON
        FROM {table_ref('gold_sentimiento_noticias')}
        WHERE FECHA_PUB >= :desde
    """, {"desde": (pd.Timestamp.now() - pd.Timedelta(days=dias)).to_pydatetime()})
    df.columns = [c.lower() for c in df.columns]
    if not df.empty:
        df["fecha_pub"] = pd.to_datetime(df["fecha_pub"], errors="coerce")
        df = df.drop_duplicates(subset="titulo")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default="alertas_rutas.json")
    ap.add_argument("--dias", type=int, default=DIAS_VIGENCIA)
    ap.add_argument("--docs-dir", help="además, un <id>.json por aviso (para cargarlos con ArtifactData)")
    args = ap.parse_args()
    alertas = alertas_rutas(_noticias(args.dias), dias=args.dias)
    cargado = datetime.now().strftime("%Y-%m-%d %H:%M")
    docs = {r["id"]: {**{k: v for k, v in r.items() if k != "id"}, "activo": True, "cargado": cargado}
            for r in alertas.to_dict("records")}
    Path(args.salida).write_text(json.dumps(docs, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.docs_dir:
        d = Path(args.docs_dir)
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.json"):
            f.unlink()
        for k, v in docs.items():
            (d / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    print(f"{len(docs)} avisos en {alertas['nodo'].nunique() if len(alertas) else 0} lugares -> {args.salida}")
    if len(alertas):
        print(alertas.groupby(["nodo", "lugar"]).size().to_string())


if __name__ == "__main__":
    main()
