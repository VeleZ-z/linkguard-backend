"""Lista estática de servicios de acortamiento de URL conocidos (RF-205).

El conjunto es inmutable y vive en memoria: no se consulta ninguna fuente
externa durante el análisis (RNF-101).
"""

from __future__ import annotations

from typing import Final

#: Dominios registrables de acortadores conocidos; se comparan en minúsculas.
URL_SHORTENERS: Final[frozenset[str]] = frozenset(
    {
        "2.gy",
        "adf.ly",
        "bc.vc",
        "bit.ly",
        "bl.ink",
        "buff.ly",
        "cutt.ly",
        "clck.ru",
        "goo.gl",
        "goo.su",
        "is.gd",
        "lnkd.in",
        "ow.ly",
        "qr.ae",
        "rb.gy",
        "rebrand.ly",
        "s.id",
        "sh.st",
        "short.gy",
        "shorturl.at",
        "soo.gd",
        "t.co",
        "t.ly",
        "tiny.cc",
        "tinyurl.com",
        "tny.im",
        "tr.im",
        "u.to",
        "v.gd",
        "x.co",
    }
)

__all__ = ["URL_SHORTENERS"]
