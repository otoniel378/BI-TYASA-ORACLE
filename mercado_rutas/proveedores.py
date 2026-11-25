"""
mercado_rutas/proveedores.py — Proveedores reales por material (pestaña
Proveedores de Rutas y puertos).

Se guardan en Oracle (GOLD_PROVEEDORES_MATERIALES, scripts/setup_proveedores_oracle.py).
Si la tabla todavía no existe, se guardan solo en la sesión y la página lo avisa.
Un proveedor suma su país a los orígenes del material (junto a los de
referencia de red.MATERIALES) y puede marcar su ruta principal.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from core.db_connector import run_query, run_write, table_ref

TABLA = "GOLD_PROVEEDORES_MATERIALES"
COLUMNAS = ["id", "material", "proveedor", "pais_iso", "ruta_id", "volumen_ton_anio", "notas", "creado_por",
            "creado_en"]
_SESION = "_rp_proveedores_sesion"


@st.cache_data(ttl=300, show_spinner=False)
def _de_oracle() -> pd.DataFrame | None:
    """None si la tabla no existe (o no hay conexión)."""
    try:
        df = run_query(f"SELECT ID, MATERIAL, PROVEEDOR, PAIS_ISO, RUTA_ID, VOLUMEN_TON_ANIO, NOTAS, CREADO_POR, "
                       f"CREADO_EN FROM {table_ref(TABLA)} WHERE ACTIVO = 1 ORDER BY MATERIAL, PROVEEDOR")
    except Exception:
        return None
    df.columns = [c.lower() for c in df.columns]
    return df


def cargar() -> tuple[pd.DataFrame, bool]:
    """(proveedores activos, se guardan en Oracle)."""
    df = _de_oracle()
    if df is not None:
        return df, True
    return pd.DataFrame(st.session_state.get(_SESION, []), columns=COLUMNAS), False


def agregar(material: str, proveedor: str, iso: str, ruta_id: str | None, volumen: float | None, notas: str,
            usuario: str, en_oracle: bool) -> None:
    if en_oracle:
        run_write(f"INSERT INTO {table_ref(TABLA)} (MATERIAL, PROVEEDOR, PAIS_ISO, RUTA_ID, VOLUMEN_TON_ANIO, NOTAS, "
                  f"CREADO_POR) VALUES (:1, :2, :3, :4, :5, :6, :7)",
                  [material, proveedor.strip()[:200], iso, ruta_id, volumen, (notas or "").strip()[:1000], usuario])
        _de_oracle.clear()
    else:
        filas = st.session_state.setdefault(_SESION, [])
        filas.append({"id": len(filas) + 1, "material": material, "proveedor": proveedor.strip(), "pais_iso": iso,
                      "ruta_id": ruta_id, "volumen_ton_anio": volumen, "notas": notas, "creado_por": usuario,
                      "creado_en": datetime.now()})


def quitar(pid: int, en_oracle: bool) -> None:
    """Baja lógica (ACTIVO = 0): el historial se conserva."""
    if en_oracle:
        run_write(f"UPDATE {table_ref(TABLA)} SET ACTIVO = 0 WHERE ID = :1", [int(pid)])
        _de_oracle.clear()
    else:
        st.session_state[_SESION] = [f for f in st.session_state.get(_SESION, []) if f["id"] != pid]


def origenes(material: str, referencia: list[str], prov: pd.DataFrame) -> list[str]:
    """Países de origen del material: primero los de proveedores reales, luego los de referencia."""
    reales = prov.loc[prov["material"] == material, "pais_iso"].tolist() if not prov.empty else []
    return list(dict.fromkeys(reales + referencia))


def ruta_principal(material: str, iso: str, prov: pd.DataFrame) -> tuple[str | None, str | None]:
    """(ruta_id, proveedor) marcada como principal para ese material y país, si hay."""
    if prov.empty:
        return None, None
    g = prov[(prov["material"] == material) & (prov["pais_iso"] == iso) & prov["ruta_id"].notna()]
    return (g["ruta_id"].iloc[0], g["proveedor"].iloc[0]) if not g.empty else (None, None)
