"""
mix_productos.py — Mix de productos y oportunidades de cross-sell.
Aceros Planos Negros.
"""

import pandas as pd
import numpy as np
from itertools import combinations


def participacion_por_familia(df_producto: pd.DataFrame, col_prod: str = "PRODUCTO_LIMPIO", col_val: str = "PESO_TON") -> pd.DataFrame:
    if df_producto.empty:
        return pd.DataFrame()

    agg = (
        df_producto.groupby(col_prod, as_index=False)[col_val]
        .sum().sort_values(col_val, ascending=False).reset_index(drop=True)
    )
    total = agg[col_val].sum()
    agg["PCT"]      = (agg[col_val] / total * 100).round(1) if total > 0 else 0.0
    agg["PCT_ACUM"] = agg["PCT"].cumsum().round(1)
    return agg


def n_familias_por_cliente(df_cliente_producto: pd.DataFrame) -> pd.DataFrame:
    if df_cliente_producto.empty:
        return pd.DataFrame()

    return (
        df_cliente_producto.groupby("CLIENTE", as_index=False)
        .agg(N_PRODUCTOS=("PRODUCTO_LIMPIO", "nunique"), PESO_TON=("PESO_TON", "sum"))
        .sort_values("N_PRODUCTOS", ascending=False).reset_index(drop=True)
    )


def tabla_coocurrencia(df_cliente_producto: pd.DataFrame) -> pd.DataFrame:
    """Clientes en común entre cada par de productos (diagonal = clientes del producto).
    Es Bᵀ·B con B = matriz cliente × producto de 0/1 (antes un ciclo de 250 mil pares: ~50 s)."""
    if df_cliente_producto.empty:
        return pd.DataFrame()

    b = (pd.crosstab(df_cliente_producto["CLIENTE"], df_cliente_producto["PRODUCTO_LIMPIO"]) > 0).astype(np.int64)
    b = b.reindex(columns=sorted(b.columns))
    m = b.T.to_numpy() @ b.to_numpy()
    return pd.DataFrame(m, index=b.columns.tolist(), columns=b.columns.tolist())


def combinaciones_frecuentes(df_cliente_producto: pd.DataFrame, min_clientes: int = 2) -> pd.DataFrame:
    if df_cliente_producto.empty:
        return pd.DataFrame()

    clientes_por_prod = df_cliente_producto.groupby("PRODUCTO_LIMPIO")["CLIENTE"].apply(set).to_dict()
    rows = []
    for pa, pb in combinations(sorted(clientes_por_prod.keys()), 2):
        n = len(clientes_por_prod[pa] & clientes_por_prod[pb])
        if n >= min_clientes:
            rows.append({"PRODUCTO_A": pa, "PRODUCTO_B": pb, "N_CLIENTES": n})

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("N_CLIENTES", ascending=False).reset_index(drop=True)


def oportunidades_crosssell(df_cliente_producto: pd.DataFrame, min_soporte: float = 0.1) -> pd.DataFrame:
    if df_cliente_producto.empty:
        return pd.DataFrame()

    total_clientes = df_cliente_producto["CLIENTE"].nunique()
    umbral = max(int(total_clientes * min_soporte), 2)

    popularidad = (
        df_cliente_producto.groupby("PRODUCTO_LIMPIO")["CLIENTE"]
        .nunique().reset_index().rename(columns={"CLIENTE": "N_CLIENTES"})
    )
    populares = popularidad[popularidad["N_CLIENTES"] >= umbral]["PRODUCTO_LIMPIO"].tolist()

    if not populares:
        return pd.DataFrame()

    ya_comprados = df_cliente_producto.groupby("CLIENTE")["PRODUCTO_LIMPIO"].apply(set).to_dict()

    rows = []
    for cliente, comprados in ya_comprados.items():
        for prod in set(populares) - comprados:
            n = popularidad[popularidad["PRODUCTO_LIMPIO"] == prod]["N_CLIENTES"].values[0]
            rows.append({"CLIENTE": cliente, "PRODUCTO_SUGERIDO": prod, "N_CLIENTES_LO_COMPRAN": int(n)})

    if not rows:
        return pd.DataFrame()

    return (
        pd.DataFrame(rows)
        .sort_values(["CLIENTE", "N_CLIENTES_LO_COMPRAN"], ascending=[True, False])
        .reset_index(drop=True)
    )
