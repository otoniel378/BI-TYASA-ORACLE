"""
Ruta anterior del motor de pronóstico. El módulo vive ahora en core/forecasting.py
porque lo usan Aceros Planos y Mercado Global. Esta ruta se conserva para no romper
código de otros equipos: apunta al mismo módulo (no es una copia).
"""
import sys

from core import forecasting as _forecasting

sys.modules[__name__] = _forecasting
