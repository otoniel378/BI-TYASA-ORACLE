"""
mercado_rutas/fuentes.py — Descarga de las fuentes externas (sin Streamlit; las
usan datos.py y scripts/update_trafico_maritimo.py). Todas gratuitas, sin API key:

  - IMF PortWatch (FMI + Oxford, señales AIS satelitales), CSV publicados en HDX
    (data.humdata.org): tránsitos diarios por paso marítimo y llamadas diarias a
    puertos mexicanos. Se actualiza cada semana con ~10 días de retraso. Cada
    CSV pesa ~10 MB y tarda ~20 s: por eso se guarda en Oracle una vez al día.
    (La API ArcGIS de PortWatch falla de forma intermitente; los CSV no.)
  - NOAA National Hurricane Center: tormentas tropicales activas.
  - Open-Meteo Marine: oleaje máximo pronosticado (7 días) en cada puerto.
"""

import io

import numpy as np
import pandas as pd
import requests

from mercado_rutas.red import PASOS, PUERTOS
from mercado_rutas.riesgo import distancia_km

HDX_PASOS = ("https://data.humdata.org/dataset/91d28bb8-986d-430c-961c-6a24ecbd66ee/resource/"
             "cbd17f06-8ab2-4ba4-a666-f7a4bcc9ea3f/download/daily-chokepoint-transit-calls-and-shipment-volume-estimates.csv")
HDX_PUERTOS_MX = ("https://data.humdata.org/dataset/ecfd24d0-7a9d-4f52-9604-9159ab9d4a5f/resource/"
                  "4e123592-2986-4506-b08d-da8b98599e3d/download/mexico-daily-port-activity-data-and-shipment-estimates.csv")
TIMEOUT = 90
DIAS_HISTORIA = 730


def _csv(url: str, columnas: list[str]) -> pd.DataFrame:
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content), usecols=columnas)
    df["fecha"] = pd.to_datetime(df["date"]).dt.tz_localize(None).dt.normalize()
    return df[df["fecha"] >= df["fecha"].max() - pd.Timedelta(days=DIAS_HISTORIA)]


def descargar_pasos() -> pd.DataFrame:
    """fecha, paso (clave de red.PASOS), transitos (todos los barcos), granel (graneleros)."""
    clave = {p["portwatch"]: k for k, p in PASOS.items()}
    df = _csv(HDX_PASOS, ["date", "portname", "n_total", "n_dry_bulk"])
    df = df[df["portname"].isin(clave)]
    return (df.assign(paso=df["portname"].map(clave))
            .rename(columns={"n_total": "transitos", "n_dry_bulk": "granel"})[["fecha", "paso", "transitos", "granel"]]
            .reset_index(drop=True))


def descargar_puertos() -> pd.DataFrame:
    """fecha, puerto (clave de red.PUERTOS), llamadas (todos los barcos), granel."""
    clave = {p["portwatch"]: k for k, p in PUERTOS.items()}
    df = _csv(HDX_PUERTOS_MX, ["date", "portname", "portcalls", "portcalls_dry_bulk"])
    df = df[df["portname"].isin(clave)]
    return (df.assign(puerto=df["portname"].map(clave))
            .rename(columns={"portcalls": "llamadas", "portcalls_dry_bulk": "granel"})[
                ["fecha", "puerto", "llamadas", "granel"]]
            .reset_index(drop=True))


def tormentas_activas() -> pd.DataFrame:
    """Tormentas tropicales activas (Atlántico y Pacífico este) con su distancia
    a cada puerto de llegada: nombre, tipo, viento_kt, lat, lon, puerto, km."""
    d = requests.get("https://www.nhc.noaa.gov/CurrentStorms.json", timeout=30).json()
    filas = []
    for s in d.get("activeStorms", []):
        lat, lon = s.get("latitudeNumeric"), s.get("longitudeNumeric")
        if lat is None or lon is None:
            continue
        for k, p in PUERTOS.items():
            filas.append({"nombre": s.get("name"), "tipo": s.get("classification"), "viento_kt": s.get("intensity"),
                          "lat": lat, "lon": lon, "puerto": k, "km": round(distancia_km(lat, lon, p["lat"], p["lon"]))})
    return pd.DataFrame(filas, columns=["nombre", "tipo", "viento_kt", "lat", "lon", "puerto", "km"])


def oleaje_puertos() -> pd.DataFrame:
    """Oleaje máximo pronosticado (m) en cada puerto los próximos 7 días: puerto, oleaje_max_m, dia."""
    filas = []
    for k, p in PUERTOS.items():
        try:
            d = requests.get("https://marine-api.open-meteo.com/v1/marine", timeout=30, params={
                "latitude": p["lat"], "longitude": p["lon"], "daily": "wave_height_max",
                "timezone": "America/Mexico_City", "forecast_days": 7,
            }).json()["daily"]
            v = np.array(d["wave_height_max"], dtype=float)
            i = int(np.nanargmax(v))
            filas.append({"puerto": k, "oleaje_max_m": float(v[i]), "dia": d["time"][i]})
        except Exception:
            filas.append({"puerto": k, "oleaje_max_m": None, "dia": None})
    return pd.DataFrame(filas)
