"""
config.py — Configuracion global de TYASA BI.
Centraliza proyecto GCP, paleta de colores y parametros analiticos.
Arquitectura multi-area: Aceros Planos | Aceros Largos | Aceros SBQ
"""

import os

# ---------------------------------------------------------------------------
# Google Cloud / BigQuery
# ---------------------------------------------------------------------------
GCP_PROJECT_ID = "project-d0cf2519-d089-47d3-930"
BQ_DATASET     = "tyasa_bi"

# ---------------------------------------------------------------------------
# Areas del proyecto
# ---------------------------------------------------------------------------
AREAS = {
    "aceros_planos": {
        "nombre": "Aceros Planos",
        "responsable": "Otoniel",
        "subsecciones": {
            "negros":       {"nombre": "Aceros Negros",      "status": "activo"},
            "galvanizados": {"nombre": "Aceros Galvanizados", "status": "en_desarrollo"},
            "formados":     {"nombre": "Aceros Formados",    "status": "en_desarrollo"},
        },
    },
    "aceros_largos": {
        "nombre": "Aceros Largos",
        "responsable": "Equipo BI Externo",
        "subsecciones": {
            "dashboard":    {"nombre": "Dashboard Ejecutivo",     "status": "activo"},
            "macro":        {"nombre": "Macroeconomía",          "status": "activo"},
            "mercado":      {"nombre": "Mercado y Costos",       "status": "activo"},
            "sectores":     {"nombre": "Sectores Productivos",   "status": "activo"},
            "comercio":     {"nombre": "Comercio Exterior",      "status": "activo"},
        },
    },
    "aceros_sbq": {
        "nombre": "Aceros SBQ",
        "responsable": "Por definir",
        "subsecciones": {},
    },
}

# ---------------------------------------------------------------------------
# Rutas locales
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
ASSETS_DIR  = os.path.join(BASE_DIR, "assets")

# ---------------------------------------------------------------------------
# Metadata de la app
# ---------------------------------------------------------------------------
APP_NAME     = "TYASA BI"
APP_SUBTITLE = "Plataforma de Inteligencia Comercial"
APP_ICON     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "img", "tyasa_logo.webp")

# ---------------------------------------------------------------------------
# Paleta de colores corporativa TYASA
# ---------------------------------------------------------------------------
COLORS = {
    "primary":    "#1B3A5C",
    "secondary":  "#4A7BA7",
    "accent":     "#8BA7BF",
    "neutral":    "#6B7280",
    "background": "#F4F6F9",
    "surface":    "#FFFFFF",
    "text":       "#1F2937",
    "text_light": "#6B7280",
    "success":    "#2E7D32",
    "warning":    "#F57C00",
    "danger":     "#C62828",
}

COLOR_SEQUENCE = [
    "#1B3A5C", "#E05C2D", "#2D8A5C", "#9B59B6",
    "#D4A017", "#00838F", "#C0392B", "#2980B9",
    "#27AE60", "#D35400", "#8E44AD", "#16A085",
    "#F39C12", "#1ABC9C", "#6C3483",
]

HEATMAP_COLORSCALE = [
    [0.0,  "#F8FAFC"],
    [0.15, "#D6E8F5"],
    [0.40, "#7BAFD4"],
    [0.70, "#2E6FA3"],
    [1.0,  "#0D2137"],
]

# ---------------------------------------------------------------------------
# Parametros analiticos
# ---------------------------------------------------------------------------
FORECAST_HORIZON_DEFAULT = 6
FORECAST_HORIZON_MAX     = 24
MIN_PERIODS_FORECAST     = 12
PARETO_THRESHOLD_A       = 0.80
PARETO_THRESHOLD_B       = 0.95
