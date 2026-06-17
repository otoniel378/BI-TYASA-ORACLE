"""
test_connection.py — Verifica que la conexión a Oracle ADW funciona.

Uso:
    python scripts/test_connection.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import oracledb
from dotenv import load_dotenv

load_dotenv()


def test():
    user       = os.environ.get("ORACLE_USER", "")
    password   = os.environ.get("ORACLE_PASSWORD", "")
    dsn        = os.environ.get("ORACLE_DSN", "")
    wallet_dir = os.environ.get("ORACLE_WALLET_DIR", "")
    wallet_pw  = os.environ.get("ORACLE_WALLET_PASSWORD", "")

    if not password or password == "PONER_TU_PASSWORD_AQUI":
        print("ERROR: Pon tu password en el archivo .env  (ORACLE_PASSWORD=...)")
        sys.exit(1)

    params = {"user": user, "password": password, "dsn": dsn}
    if wallet_dir:
        params["config_dir"]      = wallet_dir
        params["wallet_location"] = wallet_dir
        if wallet_pw:
            params["wallet_password"] = wallet_pw

    print(f"Conectando como {user} a Oracle ADW...")
    print(f"Wallet: {wallet_dir or '(sin wallet)'}")
    try:
        conn = oracledb.connect(**params)
        print(f"Conexion exitosa — Oracle {conn.version}")

        cursor = conn.cursor()
        cursor.execute("SELECT SYSDATE FROM DUAL")
        fecha = cursor.fetchone()[0]
        print(f"Fecha en Oracle: {fecha}")

        cursor.close()
        conn.close()
        print("\nTodo listo para crear las tablas.")
    except oracledb.DatabaseError as e:
        print(f"Error de conexion: {e}")
        sys.exit(1)


if __name__ == "__main__":
    test()
