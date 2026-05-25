"""
auth.py — Autenticación y gestión de roles para TYASA BI.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Usuario:
    id: str
    nombre: str
    cargo: str
    rol: str          # director | gerente | esp_negros | esp_largos | esp_sbq
    iniciales: str
    color: str        # color del avatar
    areas_permitidas: list[str] = field(default_factory=list)  # [] = acceso total


_PASS = "TYA2026"

_USUARIOS: dict[str, Usuario] = {
    "director": Usuario(
        id="director", nombre="Carlos Mendoza",
        cargo="Director General", rol="director",
        iniciales="CM", color="#1D4ED8",
        areas_permitidas=[],
    ),
    "gerente": Usuario(
        id="gerente", nombre="Ana Ramírez",
        cargo="Gerente Comercial", rol="gerente",
        iniciales="AR", color="#059669",
        areas_permitidas=[],
    ),
    "esp.negros": Usuario(
        id="esp.negros", nombre="Jorge Silva",
        cargo="Especialista — Aceros Planos Negros", rol="esp_negros",
        iniciales="JS", color="#7C3AED",
        areas_permitidas=["aceros_planos"],
    ),
    "esp.largos": Usuario(
        id="esp.largos", nombre="María López",
        cargo="Especialista — Aceros Largos", rol="esp_largos",
        iniciales="ML", color="#D97706",
        areas_permitidas=["aceros_largos"],
    ),
    "esp.sbq": Usuario(
        id="esp.sbq", nombre="Roberto Díaz",
        cargo="Especialista — Aceros SBQ", rol="esp_sbq",
        iniciales="RD", color="#DC2626",
        areas_permitidas=["aceros_sbq"],
    ),
}


def autenticar(usuario_id: str, password: str) -> Usuario | None:
    if password != _PASS:
        return None
    return _USUARIOS.get(usuario_id.lower().strip())


def get_usuario() -> Usuario | None:
    import streamlit as st
    uid = st.session_state.get("_auth_uid")
    return _USUARIOS.get(uid) if uid else None


def esta_autenticado() -> bool:
    import streamlit as st
    return bool(st.session_state.get("_auth_ok"))


def iniciar_sesion(usuario: Usuario):
    import streamlit as st
    st.session_state["_auth_ok"]  = True
    st.session_state["_auth_uid"] = usuario.id


def cerrar_sesion():
    import streamlit as st
    for k in ["_auth_ok", "_auth_uid"]:
        st.session_state.pop(k, None)


def puede_ver_seccion(seccion: str) -> bool:
    u = get_usuario()
    if not u:
        return False
    if not u.areas_permitidas:
        return True
    return seccion in u.areas_permitidas


def es_admin() -> bool:
    u = get_usuario()
    return bool(u and u.rol in ("director", "gerente"))


def es_especialista() -> bool:
    u = get_usuario()
    return bool(u and u.rol.startswith("esp_"))
