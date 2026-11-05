"""Catálogo multilingüe de términos de ingeniería social (RF-211).

La colección está organizada por categorías semánticas, es inmutable y vive
en memoria: no se consulta ninguna fuente externa durante el análisis
(RNF-101) ni se persiste en disco (RNF-103).

Todos los términos están normalizados a minúsculas y sin diacríticos. La
normalización de la URL de entrada la aplica la regla F11 antes de comparar,
de modo que ``contraseña``, ``CONTRASEÑA`` y ``contrasena`` producen la misma
coincidencia.

Precisión de la coincidencia
----------------------------
Los términos de tres o cuatro letras que aparecen como subcadena de palabras
legítimas (``pin`` en *shopping*, ``rut`` en *routes*, ``dian`` en *guardian*)
se listan en :data:`EXACT_MATCH_KEYWORDS`: solo coinciden como token completo,
nunca como prefijo, sufijo o subcadena.
"""

from __future__ import annotations

from typing import Final

#: Términos agrupados por la narrativa de suplantación que representan.
SENSITIVE_KEYWORDS_BY_CATEGORY: Final[dict[str, frozenset[str]]] = {
    "inicio_sesion": frozenset(
        {
            "iniciar-sesion",
            "iniciarsesion",
            "acceso",
            "ingresar",
            "login",
            "signin",
            "entrar",
            "autenticacion",
            "log-in",
            "sign-in",
            "portal-acceso",
        }
    ),
    "credenciales": frozenset(
        {
            "contrasena",
            "clave",
            "password",
            "usuario",
            "pin",
            "passcode",
            "credenciales",
            "credencial",
        }
    ),
    "verificacion_identidad": frozenset(
        {
            "verificar",
            "verificacion",
            "validar",
            "confirmar-identidad",
            "confirmacion",
            "verify",
            "verification",
            "identity",
            "confirm",
            "validacion",
        }
    ),
    "seguridad_bloqueo": frozenset(
        {
            "cuenta-bloqueada",
            "cuentabloqueada",
            "actividad-sospechosa",
            "seguridad",
            "secure",
            "security",
            "suspension",
            "suspendida",
            "desactivada",
            "bloqueo",
            "bloqueada",
            "soporte",
            "atencion",
            "cancelacion",
            "alerta",
            "warning",
        }
    ),
    "urgencia_amenaza": frozenset(
        {
            "urgente",
            "inmediatamente",
            "expiracion",
            "expirada",
            "vencimiento",
            "urgent",
            "immediately",
            "expired",
            "plazo-limite",
        }
    ),
    "informacion_personal": frozenset(
        {
            "datos-personales",
            "datospersonales",
            "documento",
            "cedula",
            "dni",
            "rut",
            "passport",
            "pasaporte",
            "informacion-personal",
        }
    ),
    "entidades_financieras": frozenset(
        {
            "banco",
            "bancario",
            "banca",
            "transferencia",
            "pago",
            "factura",
            "saldo",
            "tarjeta",
            "retiro",
            "bank",
            "payment",
            "card",
            "bancolombia",
            "nequi",
            "daviplata",
            "davivienda",
            "pse",
            "falabella",
            "bbva",
            "paypal",
            "mercadopago",
            "transfiya",
            "efecty",
            "claro",
            "tigo",
            "movistar",
            "dian",
        }
    ),
}

#: Catálogo plano (unión de todas las categorías) que consume F11.
SENSITIVE_KEYWORDS: Final[frozenset[str]] = frozenset().union(
    *SENSITIVE_KEYWORDS_BY_CATEGORY.values()
)

#: Términos cortos y ambiguos que solo deben coincidir como token completo.
EXACT_MATCH_KEYWORDS: Final[frozenset[str]] = frozenset(
    {"bbva", "dian", "dni", "pin", "pse", "rut", "tigo"}
)

__all__ = [
    "EXACT_MATCH_KEYWORDS",
    "SENSITIVE_KEYWORDS",
    "SENSITIVE_KEYWORDS_BY_CATEGORY",
]
