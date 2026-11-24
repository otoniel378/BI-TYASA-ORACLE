"""
probar_paginas.py — Prueba de humo de toda la app: abre cada página dentro de app.py
(con sesión de director y datos reales de Oracle) y reporta errores y tiempo de carga.

Úsalo antes de subir cambios grandes:
    python scripts/probar_paginas.py              # todas, salvo Competencia e Industria
    python scripts/probar_paginas.py mercado      # solo las de una sección
    python scripts/probar_paginas.py --todas      # incluye Competencia y su búsqueda de noticias
                                                  # e Industria (noticias en internet, ~4 min)

Solo lee (no escribe en Oracle). Sale con código 1 si alguna página truena.
"""

import ast
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(RAIZ)
sys.path.insert(0, RAIZ)
sys.stdout.reconfigure(encoding="utf-8")

from streamlit.testing.v1 import AppTest  # noqa: E402

# Secciones que se saltan siempre: Largos sigue en BigQuery (lo migra su equipo);
# el chat necesita una pregunta para hacer algo.
OMITIR_SECCIONES = {"aceros_largos", "chat_ia"}
EXTERNAS = {"mkt_industria", "mkt_competencia"}   # muchas búsquedas en internet (minutos): solo con --todas


def _diccionario(nombre: str) -> dict:
    arbol = ast.parse(open("app.py", encoding="utf-8-sig").read())
    for n in arbol.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == nombre for t in n.targets):
            return ast.literal_eval(n.value)
    raise KeyError(nombre)


def paginas() -> list[tuple[str, str, str | None, str]]:
    """(sección, subsección, módulo de Planos, nombre) de cada página navegable."""
    subs, pags = _diccionario("SUBSECCIONES"), _diccionario("PAGINAS")
    out = []
    for seccion, mapa in subs.items():
        if seccion in OMITIR_SECCIONES:
            continue
        for sub, etiqueta in mapa.items():
            if seccion == "aceros_planos" and sub == "negros":
                for clave, modulo in pags.items():
                    if isinstance(clave, tuple) and clave[:2] == ("aceros_planos", "negros"):
                        out.append((seccion, sub, clave[2], modulo.split(".")[-1]))
            else:
                out.append((seccion, sub, None, etiqueta))
    return out


def abrir(seccion: str, sub: str, modulo: str | None, timeout: int = 600) -> AppTest:
    at = AppTest.from_file("app.py", default_timeout=timeout)
    at.session_state["_auth_ok"] = True
    at.session_state["_auth_uid"] = "director"
    at.session_state["nav_seccion"] = seccion
    at.session_state["nav_subseccion"] = sub
    if modulo:
        at.session_state["nav_modulo_planos"] = modulo
    at.run()
    return at


def main(args: list[str]) -> int:
    todas = "--todas" in args
    filtro = [a for a in args if not a.startswith("--")]
    fallas = 0
    print(f"{'página':45s} {'seg':>6s}  resultado")
    for seccion, sub, modulo, nombre in paginas():
        if filtro and seccion not in filtro:
            continue
        if not todas and sub in EXTERNAS:
            continue
        t = time.time()
        try:
            at = abrir(seccion, sub, modulo)
            errores = [e.value for e in at.exception] + [
                e.value for e in at.error if str(e.value).startswith("Error cargando")]
        except Exception as e:  # timeout u otro fallo del arnés
            errores = [f"{type(e).__name__}: {e}"]
        seg = time.time() - t
        fallas += bool(errores)
        estado = "OK" if not errores else "FALLA: " + " | ".join(str(x).splitlines()[0][:150] for x in errores)
        print(f"{seccion + '/' + nombre:45s} {seg:6.1f}  {estado}", flush=True)
    print(f"\n{fallas} página(s) con error.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
