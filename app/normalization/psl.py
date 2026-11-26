"""Módulo de Public Suffix List (PSL) vendorizada (RF-501).

Provee funciones para obtener el sufijo público y el dominio registrable
de un host, usando la lista vendorizada en
``app/engine/data/public_suffix_list.dat``.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path

#: Ruta a la lista vendorizada (ICANN + PRIVATE).
PSL_PATH: Path = (
    Path(__file__).resolve().parents[2] / "app" / "engine" / "data" / "public_suffix_list.dat"
)


def _is_ip(host: str) -> bool:
    """Indica si ``host`` es una dirección IP literal."""
    try:
        ipaddress.ip_address(host)
        return True
    except Exception:
        return False


class PSL:
    """Carga y consulta la Public Suffix List vendorizada."""

    _lines: list[str] = []
    # Sufijos ordenados una sola vez al cargar: ordenar 14 693 entradas por
    # consulta hacía inviable el featurizador masivo (RF-605/RNF-109).
    _sorted_lines: tuple[str, ...] = ()
    # Índice por última etiqueta: evita recorrer los 14 693 sufijos en cada URL.
    _by_last_label: dict[str, tuple[str, ...]] = {}

    @classmethod
    def load(cls) -> None:
        """Carga la lista de sufijos públicos desde el archivo vendorizado."""
        if cls._lines:
            return
        with PSL_PATH.open("r", encoding="utf-8") as handle:
            cls._lines = [
                line.strip() for line in handle if line.strip() and not line.startswith("#")
            ]
        cls._sorted_lines = tuple(
            sorted(cls._lines, key=lambda suffix: len(suffix.split(".")), reverse=True)
        )
        groups: dict[str, list[str]] = {}
        for suffix in cls._sorted_lines:
            groups.setdefault(suffix.split(".")[-1], []).append(suffix)
        cls._by_last_label = {label: tuple(items) for label, items in groups.items()}

    @classmethod
    def _match_suffix(cls, host_labels: list[str], suffix_labels: list[str]) -> bool:
        """Indica si ``host_labels`` termina con ``suffix_labels``.

        Los comodines ``*`` en ``suffix_labels`` coinciden con una etiqueta.
        Se compara desde la derecha (TLD → izquierda).
        """
        if len(suffix_labels) > len(host_labels):
            return False
        for i in range(1, len(suffix_labels) + 1):
            h = host_labels[-i]
            s = suffix_labels[-i]
            if s == "*":
                continue
            if h.lower() != s.lower():
                return False
        return True

    @classmethod
    def public_suffix(cls, host: str) -> str:
        """Devuelve el sufijo público más largo que coincide con ``host``.

        Ejemplos:
            ``example.com`` → ``com``
            ``sub.example.co.uk`` → ``co.uk``
            ``a.b.vercel.app`` → ``vercel.app``
        """
        if _is_ip(host):
            return host
        host_labels = host.lower().split(".")
        for suffix in cls._by_last_label.get(host_labels[-1], ()):
            suffix_clean = suffix.lstrip(".")
            suffix_labels = suffix_clean.split(".")
            if cls._match_suffix(host_labels, suffix_labels):
                return suffix_clean
        return host

    @classmethod
    def registrable_domain(cls, host: str) -> str:
        """Devuelve el dominio registrable (eTLD+1) de ``host``.

        Ejemplos:
            ``sub.example.com`` → ``example.com``
            ``a.b.vercel.app`` → ``vercel.app``
            ``example.co.uk`` → ``example.co.uk``
        """
        if _is_ip(host):
            return host
        suffix = cls.public_suffix(host)
        if "*" in suffix:
            # Sufijo comodín: el dominio registrable es el sufijo sin '*'.
            return suffix.replace("*", "").lstrip(".")
        suffix_labels = suffix.split(".")
        host_labels = host.lower().split(".")
        if len(host_labels) <= len(suffix_labels):
            return host
        domain_labels = host_labels[: -len(suffix_labels)]
        return f"{domain_labels[-1]}.{suffix}"


# Carga la lista al importar el módulo.
PSL.load()


def public_suffix(host: str) -> str:
    """Devuelve el sufijo público de ``host`` (ver :meth:`PSL.public_suffix`)."""
    return PSL.public_suffix(host)


def registrable_domain(host: str) -> str:
    """Devuelve el dominio registrable de ``host`` (ver :meth:`PSL.registrable_domain`)."""
    return PSL.registrable_domain(host)


__all__ = ["PSL", "public_suffix", "registrable_domain"]
