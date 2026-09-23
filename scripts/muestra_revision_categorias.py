"""
muestra_revision_categorias.py — Toma una muestra estratificada de
data/categorias_bootstrap.csv (generado por bootstrap_dataset_categorias.py)
para revisión manual en Excel.

~25-30 noticias por categoría (~400 en total). La columna 'categoria_final'
queda vacía para que el usuario la llene: si la deja vacía se acepta la
sugerencia de Gemini ('categoria_gemini') tal cual.

Categorías con muy pocos ejemplos totales (< --min-para-muestra) se EXCLUYEN
de la muestra de revisión — separar unos pocos ejemplos para "gold" dejaría
0 para entrenar, así que todos sus ejemplos van directo a categorias_train.csv
(sin validación gold para esa categoría por ahora).

Si data/categorias_revision.csv ya existe, la muestra nueva se FUSIONA (por URL)
en vez de sobreescribirla, para no perder revisiones manuales ya hechas —
útil para completar solo las categorías que se ampliaron después.

Uso:
  python scripts/muestra_revision_categorias.py [--por-categoria 30]
  python scripts/muestra_revision_categorias.py --categorias "Tecnología,Business,Politics"
"""

import argparse
import sys
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

import pandas as pd

from mercado_noticias.analytics.categorias import CATEGORIAS_TODAS

DATA_DIR = _root.parent / "data"


def run(por_categoria: int = 30, min_para_muestra: int = 15, categorias_filtro: list[str] | None = None,
        min_reserva_train: int = 5):
    src = DATA_DIR / "categorias_bootstrap.csv"
    if not src.exists():
        print(f"ERROR: no existe {src}. Corre primero bootstrap_dataset_categorias.py")
        sys.exit(1)

    df = pd.read_csv(src, encoding="utf-8-sig")
    print(f"Dataset bootstrap: {len(df)} filas")

    categorias = categorias_filtro or CATEGORIAS_TODAS

    muestras = []
    for cat in categorias:
        sub = df[df["categoria_gemini"] == cat]
        if len(sub) < min_para_muestra:
            print(f"  [OMITIDA] {cat}: solo {len(sub)} disponibles (< {min_para_muestra}) — "
                  f"van todas directo a train, sin muestra gold")
            continue
        # Reserva mínima para train: nunca tomar el 100% de una categoría chica
        # para la muestra gold (si no, esa categoría queda con 0 ejemplos para entrenar).
        tope = max(0, len(sub) - min_reserva_train)
        n = min(por_categoria, tope)
        if n < por_categoria:
            print(f"  [AVISO] {cat}: solo {len(sub)} disponibles, muestreando {n} "
                  f"(se reservan {min_reserva_train} para train)")
        if n == 0:
            continue
        muestras.append(sub.sample(n=n, random_state=42))

    if not muestras:
        print("ERROR: ninguna categoría alcanzó el mínimo para muestrear.")
        sys.exit(1)

    muestra = pd.concat(muestras, ignore_index=True)
    muestra["categoria_final"] = ""  # a llenar manualmente en Excel

    cols = ["url", "titulo", "descripcion", "fuente", "fecha_pub",
            "categoria_gemini", "confianza", "categoria_final"]
    muestra = muestra[[c for c in cols if c in muestra.columns]]

    out_path = DATA_DIR / "categorias_revision.csv"
    if out_path.exists():
        previa = pd.read_csv(out_path, encoding="utf-8-sig")
        antes = len(previa)
        muestra = pd.concat([previa, muestra], ignore_index=True)
        muestra = muestra.drop_duplicates(subset="url", keep="first")  # conserva revisiones previas
        print(f"\nFusionado con {out_path.name} existente: {antes} previas -> {len(muestra)} totales")

    muestra = muestra.sort_values("categoria_gemini")
    muestra.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\nMuestra de revisión: {len(muestra)} filas -> {out_path}")
    print("\nAbre este CSV en Excel, revisa 'categoria_gemini' contra el título/descripción")
    print("y llena 'categoria_final' SOLO cuando la sugerencia esté mal (déjala vacía si está bien).")
    print("Categorías válidas (copiar/pegar exacto):")
    for c in CATEGORIAS_TODAS:
        print(f"  - {c}")
    print("\nCuando termines, corre: python scripts/aplicar_revision_categorias.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--por-categoria", type=int, default=30)
    parser.add_argument("--min-para-muestra", type=int, default=15)
    parser.add_argument("--categorias", type=str, default=None,
                         help="Lista de categorías separadas por coma (por defecto: todas)")
    parser.add_argument("--min-reserva-train", type=int, default=5)
    args = parser.parse_args()
    cats = [c.strip() for c in args.categorias.split(",")] if args.categorias else None
    run(args.por_categoria, args.min_para_muestra, cats, args.min_reserva_train)
