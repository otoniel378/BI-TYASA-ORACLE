"""
bootstrap_dataset_categorias.py — Genera un dataset grande de noticias etiquetadas
por categoría (vía Gemini) para poder entrenar el clasificador LSTM.

Corrida ÚNICA / manual (no forma parte del workflow diario de GitHub Actions).
Amplía la ventana de búsqueda de noticias (más queries por grupo, NewsAPI hasta
30 días atrás) para juntar ~1000-1500 noticias únicas, y las clasifica todas con
el etiquetador Gemini de categorias.py.

Salida: data/categorias_bootstrap.csv (en la raíz del repo, fuera de cache/,
porque este sí es un dataset versionable).

Si data/categorias_bootstrap.csv ya existe, el resultado nuevo se FUSIONA (dedup
por URL) en vez de sobreescribirlo — útil para completar categorías puntuales
sin re-clasificar todo el backlog otra vez.

Uso:
  python scripts/bootstrap_dataset_categorias.py
  python scripts/bootstrap_dataset_categorias.py --grupos "Business,Politics,Tecnología Digital"
  GEMINI_API_KEY=xxx python scripts/bootstrap_dataset_categorias.py
"""

import argparse
import os
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

from datetime import datetime

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Cuántas noticias pedir por grupo temático (más que el pipeline diario, que usa 8).
# buscar_noticias_sector ya trae hasta ~120 resultados en bruto por grupo (8 queries
# x 15 c/u) antes de truncar — pedir 120 aquí evita descartar resultados ya obtenidos
# sin generar llamadas RSS/NewsAPI adicionales.
MAX_POR_GRUPO = 120


def _get_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        import tomllib
        cfg = tomllib.loads((_root / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
        return cfg.get("GEMINI_API_KEY", "")
    except Exception:
        try:
            import tomli
            cfg = tomli.loads((_root / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))
            return cfg.get("GEMINI_API_KEY", "")
        except Exception:
            return ""


def run(grupos_filtro: list[str] | None = None):
    print("=" * 60)
    print(f"TYASA BI — Bootstrap dataset de categorías — {datetime.now()}")
    print("=" * 60)

    gemini_key = _get_gemini_key()
    if not gemini_key:
        print("ERROR: GEMINI_API_KEY no encontrada.")
        sys.exit(1)
    print(f"  Gemini key: ...{gemini_key[-6:]}")

    from mercado_noticias.analytics.noticias import (
        buscar_noticias_sector,
        GRUPOS_INDUSTRIA, GRUPOS_NACIONAL, GRUPOS_INTERNACIONAL,
    )
    from mercado_noticias.analytics.categorias import (
        clasificar_categoria_lote, resultados_a_dataframe, CATEGORIAS_TODAS,
    )

    todos_grupos = {**GRUPOS_INDUSTRIA, **GRUPOS_NACIONAL, **GRUPOS_INTERNACIONAL}
    if grupos_filtro:
        faltantes = [g for g in grupos_filtro if g not in todos_grupos]
        if faltantes:
            print(f"ERROR: grupo(s) no encontrados: {faltantes}")
            sys.exit(1)
        todos_grupos = {g: todos_grupos[g] for g in grupos_filtro}

    todas_noticias: list[dict] = []
    seen_urls: set[str] = set()

    print(f"\n  Buscando noticias en {len(todos_grupos)} grupos temáticos "
          f"(hasta {MAX_POR_GRUPO} por grupo)...")
    for grupo in todos_grupos:
        try:
            nots = buscar_noticias_sector(grupo, max_resultados=MAX_POR_GRUPO)
            nuevas_grupo = 0
            for n in nots:
                url = n.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    n["grupo"] = grupo
                    todas_noticias.append(n)
                    nuevas_grupo += 1
            print(f"    {grupo}: {nuevas_grupo} nuevas (acumulado {len(todas_noticias)})")
        except Exception as e:
            print(f"    [WARN] {grupo}: {e}")

    print(f"\n  Total noticias únicas recolectadas: {len(todas_noticias)}")
    if not todas_noticias:
        print("  Sin noticias para procesar.")
        return

    print(f"\n  Clasificando categoría con Gemini (esto puede tardar varios minutos)...")
    resultados = clasificar_categoria_lote(todas_noticias, gemini_key, max_noticias=None)

    cached = sum(1 for r in resultados if r.get("_cached"))
    nuevas = len(resultados) - cached
    print(f"  Clasificadas: {len(resultados)} ({nuevas} nuevas con Gemini, {cached} desde caché)")

    df = resultados_a_dataframe(resultados)
    df["categoria_final"] = ""  # columna vacía para la revisión manual en Excel

    # data/ vive en la raíz del repo (un nivel arriba de proyecto-tyasaBI), junto a cache/
    data_dir = _root.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "categorias_bootstrap.csv"

    if out_path.exists():
        df_previo = pd.read_csv(out_path, encoding="utf-8-sig")
        antes = len(df_previo)
        df = pd.concat([df_previo, df], ignore_index=True)
        df = df.drop_duplicates(subset="url", keep="first")  # conserva revisiones previas
        print(f"\n  Fusionado con {out_path.name} existente: {antes} previas + "
              f"{len(resultados)} nuevas -> {len(df)} totales (tras dedup)")

    print("\n  Distribución por categoría (dataset completo):")
    for cat in CATEGORIAS_TODAS:
        n = int((df["categoria_gemini"] == cat).sum())
        print(f"    {cat:30s} {n:5d}")

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\n  Guardado: {out_path} ({len(df)} filas)")
    print("\n  LISTO. Siguiente paso: revisar una muestra en Excel (columna "
          "'categoria_final') y correr scripts/aplicar_revision_categorias.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--grupos", type=str, default=None,
                         help="Lista de grupos separados por coma (por defecto: todos)")
    args = parser.parse_args()
    grupos = [g.strip() for g in args.grupos.split(",")] if args.grupos else None
    run(grupos)
