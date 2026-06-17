"""
db_connector.py — Conexión a Oracle Autonomous Database (ADW).
Todas las consultas van al schema ADMIN del ADW de TYASA.

Autenticación (se intenta en este orden):
  1. secrets.toml [oracle] — user, password, dsn, wallet_dir, wallet_password
  2. Variables de entorno ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN
"""

import os
import oracledb
import pandas as pd
import streamlit as st

SCHEMA = "ADMIN"


def _get_oracle_params() -> dict:
    try:
        cfg = st.secrets["oracle"]
        params = {
            "user":     cfg["user"],
            "password": cfg["password"],
            "dsn":      cfg["dsn"],
        }
        wallet_dir = cfg.get("wallet_dir", "")
        if wallet_dir:
            params["config_dir"]      = wallet_dir
            params["wallet_location"] = wallet_dir
            wallet_pw = cfg.get("wallet_password", "")
            if wallet_pw:
                params["wallet_password"] = wallet_pw
        return params
    except Exception:
        return {
            "user":     os.environ.get("ORACLE_USER", "ADMIN"),
            "password": os.environ.get("ORACLE_PASSWORD", ""),
            "dsn":      os.environ.get("ORACLE_DSN", ""),
        }


@st.cache_resource(show_spinner=False)
def get_oracle_pool() -> oracledb.ConnectionPool:
    """Pool de conexiones Oracle singleton por sesión de Streamlit."""
    params = _get_oracle_params()
    return oracledb.create_pool(min=1, max=5, increment=1, **params)


def run_query(sql: str) -> pd.DataFrame:
    """Ejecuta SQL en Oracle ADW y devuelve un DataFrame."""
    pool = get_oracle_pool()
    with pool.acquire() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            cols = [d[0] for d in cursor.description]
            rows = cursor.fetchall()
            return pd.DataFrame(rows, columns=cols)
        except Exception as e:
            raise RuntimeError(f"Error Oracle:\n{sql}\n\nDetalle: {e}") from e
        finally:
            cursor.close()


def list_tables() -> list[str]:
    """Devuelve la lista de tablas disponibles en el schema ADMIN."""
    pool = get_oracle_pool()
    with pool.acquire() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT TABLE_NAME FROM ALL_TABLES WHERE OWNER = '{SCHEMA}'"
            )
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            cursor.close()


def table_ref(table_name: str) -> str:
    """Devuelve la referencia completa de una tabla Oracle: ADMIN.NOMBRE_TABLA."""
    return f"{SCHEMA}.{table_name.upper()}"
