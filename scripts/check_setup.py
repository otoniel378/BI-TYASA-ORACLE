"""
check_setup.py — Verifica que la configuracion de TYASA BI sea correcta.
Ejecutar desde la raiz del proyecto:  python scripts/check_setup.py
"""
import os
import sys

# Agregar raiz al path
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

OK   = "\033[92mOK\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93m!\033[0m"

errors = 0


def check(label: str, ok: bool, hint: str = ""):
    global errors
    if ok:
        print(f"  {OK} {label}")
    else:
        print(f"  {FAIL} {label}")
        if hint:
            print(f"      -> {hint}")
        errors += 1


# ── 1. Archivo secrets.toml ───────────────────────────────────────────────────
print("\n[1/4] Archivo de configuración")
secrets_path = os.path.join(_root, ".streamlit", "secrets.toml")
has_secrets = os.path.isfile(secrets_path)
check(
    "secrets.toml encontrado",
    has_secrets,
    "Crea .streamlit/secrets.toml copiando la plantilla:\n"
    "      cp .streamlit/secrets.toml.example .streamlit/secrets.toml",
)

# ── 2. Contenido de secrets.toml ─────────────────────────────────────────────
print("\n[2/4] Claves en secrets.toml")
if has_secrets:
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            tomllib = None

    secrets = {}
    if tomllib:
        with open(secrets_path, "rb") as f:
            secrets = tomllib.load(f)
    else:
        # Parseo básico sin librería
        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#") and not line.startswith("["):
                    k, _, v = line.partition("=")
                    secrets[k.strip()] = v.strip().strip('"').strip("'")

    check(
        "GEMINI_API_KEY presente",
        bool(secrets.get("GEMINI_API_KEY", "")),
        "Agrega GEMINI_API_KEY = \"AIzaSy...\" en secrets.toml",
    )
    has_sa = "gcp_service_account" in secrets
    has_cred_path = bool(secrets.get("GOOGLE_APPLICATION_CREDENTIALS", ""))
    has_env = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""))
    check(
        "Credenciales GCP configuradas",
        has_sa or has_cred_path or has_env,
        "Agrega la sección [gcp_service_account] o GOOGLE_APPLICATION_CREDENTIALS en secrets.toml\n"
        "      (ver CONFIGURACION.md paso 3)",
    )
else:
    print(f"  {WARN} Saltando verificación de claves (secrets.toml no existe)")

# ── 3. Conexión a BigQuery ────────────────────────────────────────────────────
print("\n[3/4] Conexión a BigQuery")
try:
    # Simular carga de secrets via env var para el test
    if has_secrets and not os.environ.get("STREAMLIT_SECRETS_FILE"):
        os.environ["STREAMLIT_SECRETS_FILE"] = secrets_path

    from core.db_connector import get_bq_client, PROJECT_ID
    client = get_bq_client()
    # Consulta mínima para validar acceso
    list(client.list_datasets(max_results=1))
    check(f"Conexión a BigQuery exitosa — proyecto: {PROJECT_ID}", True)
except Exception as e:
    msg = str(e)
    hint = "Verifica que las credenciales en secrets.toml sean válidas."
    if "403" in msg or "Permission" in msg:
        hint = "Acceso denegado. Pide a otoniel378 que te asigne el rol BigQuery Data Viewer."
    elif "DefaultCredentialsError" in msg or "credentials" in msg.lower():
        hint = "No se encontraron credenciales. Revisa la sección [gcp_service_account] en secrets.toml."
    check(f"Conexión a BigQuery — {msg[:80]}", False, hint)

# ── 4. Paquetes requeridos ────────────────────────────────────────────────────
print("\n[4/4] Paquetes Python")
required = [
    ("streamlit",       "streamlit"),
    ("google.cloud.bigquery", "google-cloud-bigquery"),
    ("google.genai",    "google-genai"),
    ("plotly",          "plotly"),
    ("pandas",          "pandas"),
    ("trafilatura",     "trafilatura"),
    ("feedparser",      "feedparser"),
]
for module, pkg in required:
    try:
        __import__(module)
        check(f"{pkg} instalado", True)
    except ImportError:
        check(f"{pkg} instalado", False, f"pip install {pkg}")

# ── Resultado final ───────────────────────────────────────────────────────────
print()
if errors == 0:
    print(f"  {OK} Todo listo. Puedes correr:  streamlit run app.py\n")
else:
    print(f"  {FAIL} {errors} problema(s) encontrado(s). Revisa los mensajes anteriores.")
    print("       Consulta CONFIGURACION.md para instrucciones detalladas.\n")
    sys.exit(1)
