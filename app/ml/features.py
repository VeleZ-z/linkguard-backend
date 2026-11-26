"""Featurizador léxico determinista del clasificador lineal (RF-601).

Porta las familias de ``accuracy-lab/scripts/feat2.py`` con ``rules=False``:
TLD, n-gramas del nombre registrable, tokens de subdominio/host/ruta,
extensión, características numéricas normalizadas y marca en lugar
equivocado.  La segmentación del host usa la PSL vendorizada (RF-501), no
``publicsuffix2``.

La función es **pura**: no lee red, no escribe disco y no muta estado
compartido.  Las claves legibles se transforman con
``zlib.crc32(clave.encode()) % 131072``; está prohibido ``hash()`` de Python
por la aleatorización entre procesos (RNF-108).

No se usan expresiones regulares con cuantificadores anidados: todos los
patrones son lineales y no pueden sufrir backtracking catastrófico (RNF-110).
"""

from __future__ import annotations

import ipaddress
import math
import re
import zlib
from collections import Counter
from urllib.parse import unquote, urlsplit

from app.engine.data.brands import BRANDS
from app.normalization.psl import public_suffix, registrable_domain

#: Número de cubos del espacio de hashes (2^17).
N_FEATURES: int = 1 << 17

_VOWELS: frozenset[str] = frozenset("aeiou")

#: Patrones lineales: sin alternancias anidadas ni repeticiones solapadas.
_RE_SUB_TOKEN: re.Pattern[str] = re.compile(r"[-_]")
_RE_WORD: re.Pattern[str] = re.compile(r"[^a-z0-9]+")
_RE_CONSONANT_RUN: re.Pattern[str] = re.compile(r"[^aeiou0-9\-]+")
_RE_EXTENSION: re.Pattern[str] = re.compile(r"\.([a-z0-9]{2,5})$")


def _build_brand_index() -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    """Indexa las marcas por sus primeras tres letras (búsqueda lineal)."""
    grupos: dict[str, list[str]] = {}
    cortas: list[str] = []
    for brand in sorted(BRANDS):
        if len(brand) < 3:
            cortas.append(brand)
        else:
            grupos.setdefault(brand[:3], []).append(brand)
    return {prefix: tuple(items) for prefix, items in grupos.items()}, tuple(cortas)


#: Evita recorrer las ~400 marcas por cada URL (RF-605/RNF-109). El resultado
#: es idéntico al de la búsqueda lineal; solo cambia el coste computacional.
_BRAND_BY_PREFIX, _SHORT_BRANDS = _build_brand_index()


def _brands_present(haystack: str) -> set[str]:
    """Devuelve las marcas contenidas en ``haystack`` usando el índice."""
    presentes: set[str] = {brand for brand in _SHORT_BRANDS if brand in haystack}
    for offset in range(max(0, len(haystack) - 2)):
        for brand in _BRAND_BY_PREFIX.get(haystack[offset : offset + 3], ()):
            if brand in haystack:
                presentes.add(brand)
    return presentes


def hash_feature(key: str) -> int:
    """Devuelve el índice estable de una clave legible de característica."""
    return zlib.crc32(key.encode("utf-8")) % N_FEATURES


def _entropy(value: str) -> float:
    """Entropía de Shannon de ``value`` en bits por símbolo."""
    if not value:
        return 0.0
    counts: Counter[str] = Counter(value)
    total: int = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _split_url(url: str) -> tuple[str, str, str, str, bool]:
    """Parsea ``url`` y devuelve host, esquema, ruta, consulta y flag de puerto.

    Si la entrada no trae esquema se presupone ``http://``, igual que el
    prototipo de laboratorio.  Un URL malformado degrada a campos vacíos de
    forma determinista en vez de lanzar una excepción.
    """
    candidate = url.strip()
    if "://" not in candidate:
        candidate = "http://" + candidate
    try:
        parsed = urlsplit(candidate)
        host = (parsed.hostname or "").lower().rstrip(".")
        try:
            port = parsed.port
        except ValueError:
            port = None
        port_flag = port is not None and port not in (80, 443)
        return host, parsed.scheme, parsed.path or "", parsed.query or "", port_flag
    except ValueError:
        return "", "", "", "", False


def _labelled_features(url: str) -> dict[str, float]:
    """Construye el vector de claves legibles → valor de una URL."""
    host, scheme, raw_path, raw_query, port_flag = _split_url(url)
    features: dict[str, float] = {}

    def add(key: str, value: float = 1.0) -> None:
        features[key] = features.get(key, 0.0) + float(value)

    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False

    registrable = registrable_domain(host) if host else ""
    suffix = public_suffix(host) if host else ""
    if not suffix and host:
        suffix = host.rsplit(".", 1)[-1]
    reg = (
        registrable[: -(len(suffix) + 1)]
        if suffix and registrable.endswith("." + suffix)
        else registrable
    )
    sub = (
        host[: -(len(registrable) + 1)] if registrable and host.endswith("." + registrable) else ""
    )
    labels = [label for label in sub.split(".") if label]

    path = unquote(raw_path)
    query = unquote(raw_query)

    add("tld=" + suffix)
    add("isip", is_ip)

    # N-gramas del nombre registrable, con anclas de inicio y fin.
    anchored = "^" + reg + "$"
    for size in (2, 3, 4):
        for offset in range(len(anchored) - size + 1):
            add(f"r{size}:" + anchored[offset : offset + size])

    # Tokens de subdominio y longitud por etiqueta.
    for label in labels:
        for token in _RE_SUB_TOKEN.split(label):
            if token:
                add("st:" + token[:20])
        add("slen", len(label) / 20)

    # Tokens del nombre registrable + subdominio.
    host_text = (reg + " " + sub).replace(".", " ")
    for token in _RE_WORD.split(host_text):
        if token:
            add("ht:" + token[:20])

    # Tokens de ruta y consulta (≤ 20 caracteres).
    for token in _RE_WORD.split((path + " " + query).lower()):
        if token and len(token) <= 20:
            add("pt:" + token)

    extension = _RE_EXTENSION.search(path.lower())
    if extension:
        add("ext=" + extension.group(1))

    # Características numéricas normalizadas al rango [0, 1] aproximado.
    length = len(reg) or 1
    digits = sum(char.isdigit() for char in reg)
    hyphens = reg.count("-")
    vowels = sum(char in _VOWELS for char in reg)
    consonant_run = max((len(match) for match in _RE_CONSONANT_RUN.findall(reg)), default=0)

    add("n_lenreg", min(length, 40) / 40)
    add("n_dig", digits / length)
    add("n_hy", min(hyphens, 5) / 5)
    add("n_vow", vowels / length)
    add("n_conrun", min(consonant_run, 12) / 12)
    add("n_ent", _entropy(reg) / 5)
    add("n_nsub", min(len(labels), 6) / 6)
    add("n_dots", min(host.count("."), 8) / 8)
    add("n_pathlen", min(len(path), 100) / 100)
    add("n_qlen", min(len(query), 100) / 100)
    add("n_depth", min(path.count("/"), 8) / 8)
    add("n_https", scheme == "https")
    add("n_totlen", min(len(url), 200) / 200)
    add("n_at", "@" in url)
    add("n_port", port_flag)
    add("n_hasq", bool(query))
    add("n_emptypath", path in ("", "/"))

    # Marca conocida en lugar equivocado (RF-601, RF-503).
    brand_path = unquote(raw_path + " " + raw_query).lower()
    if any(brand != reg for brand in _brands_present(reg)):
        add("b_reg")
    if any(brand != reg for brand in _brands_present(sub)):
        add("b_sub")
    if any(brand not in reg for brand in _brands_present(brand_path)):
        add("b_path")

    return features


def extract_labelled(url: str) -> dict[str, float]:
    """Devuelve el vector con claves legibles; útil para depuración y pruebas."""
    return _labelled_features(url)


def extract_features(url: str) -> dict[int, float]:
    """Devuelve el vector hashed de una URL como ``dict[int, float]``."""
    return {hash_feature(key): value for key, value in _labelled_features(url).items()}


def extract_feature_keys(url: str) -> dict[int, str]:
    """Devuelve ``índice → clave legible`` para agrupar contribuciones (RF-604)."""
    return {hash_feature(key): key for key in _labelled_features(url)}


def feature_group(key: str) -> str:
    """Devuelve el ``rule_id`` del grupo al que pertenece una clave legible (§6)."""
    if key.startswith("tld="):
        return "ML_TLD_RISK"
    if key.startswith(("r2:", "r3:", "r4:")) or key in {
        "n_lenreg",
        "n_dig",
        "n_hy",
        "n_vow",
        "n_conrun",
        "n_ent",
    }:
        return "ML_DOMAIN_SHAPE"
    if key.startswith(("st:", "ht:")) or key in {"n_nsub", "n_dots", "slen"}:
        return "ML_HOST_PATTERN"
    if key.startswith(("pt:", "ext=")) or key in {
        "n_pathlen",
        "n_qlen",
        "n_depth",
        "n_emptypath",
    }:
        return "ML_PATH_PATTERN"
    if key.startswith("b_"):
        return "ML_BRAND_MISMATCH"
    return "ML_URL_SHAPE"


__all__ = [
    "N_FEATURES",
    "hash_feature",
    "extract_features",
    "extract_labelled",
    "extract_feature_keys",
    "feature_group",
]
