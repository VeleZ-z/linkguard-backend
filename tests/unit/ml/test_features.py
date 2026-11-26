"""Pruebas unitarias del featurizador léxico determinista (H5-T08, RF-601).

Cubre ``TC-RF-601-01`` (20 vectores congelados), el hashing estable con
``zlib.crc32`` (RNF-108), la pureza sin red, las familias de características,
los seis grupos de evidencia del adendo §6 y la ausencia de ReDoS (RNF-110).
"""

from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import time
import tokenize
import zlib
from pathlib import Path
from typing import Any, Final

import pytest
from app.ml.features import (
    N_FEATURES,
    extract_feature_keys,
    extract_features,
    extract_labelled,
    feature_group,
    hash_feature,
)

#: Raíz del repositorio y ruta robusta del corpus congelado (independiente del cwd).
ROOT: Final[Path] = Path(__file__).resolve().parents[3]
GOLDEN_PATH: Final[Path] = Path(__file__).resolve().parents[2] / "data" / "golden_vectors.json"
FEATURES_PATH: Final[Path] = ROOT / "app" / "ml" / "features.py"

_GOLDEN: Final[dict[str, Any]] = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
_VECTORES: Final[list[dict[str, Any]]] = _GOLDEN["vectors"]

_URL_MARCA: Final[str] = "https://paypal-verify.evil.cn/login"
_URL_RUTA: Final[str] = "https://example.com/a/b/file.php?q=1"

#: Programa independiente para comprobar la estabilidad entre procesos.
_CHILD_CODE: Final[str] = (
    "import json, sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "from app.ml.features import extract_features;"
    "print(json.dumps(extract_features('https://paypal-verify.evil.cn/login'), sort_keys=True))"
)


def _codigo_sin_comentarios_ni_cadenas(ruta: Path) -> str:
    """Devuelve el código fuente enmascarando docstrings y comentarios.

    El módulo menciona ``hash()`` en su docstring para prohibirlo; por eso la
    comprobación debe inspeccionar solo el código ejecutable, no la prosa.
    """
    lineas: list[str] = ruta.read_text(encoding="utf-8").splitlines(keepends=True)
    texto = "".join(lineas)
    for token in tokenize.generate_tokens(io.StringIO(texto).readline):
        if token.type not in (tokenize.STRING, tokenize.COMMENT):
            continue
        (fila_ini, col_ini), (fila_fin, col_fin) = token.start, token.end
        for fila in range(fila_ini, fila_fin + 1):
            linea = lineas[fila - 1]
            inicio = col_ini if fila == fila_ini else 0
            fin = col_fin if fila == fila_fin else len(linea.rstrip("\r\n"))
            lineas[fila - 1] = linea[:inicio] + (" " * (fin - inicio)) + linea[fin:]
    return "".join(lineas)


class TestVectoresCongeladosRF601:
    """TC-RF-601-01: paridad exacta con los vectores generados tras H5-T04."""

    def test_manifiesto_del_corpus_congelado(self) -> None:
        assert len(_VECTORES) == 20
        assert _GOLDEN["n_features"] == N_FEATURES == 131072

    @pytest.mark.parametrize(
        "vector",
        _VECTORES,
        ids=[vector["url"] for vector in _VECTORES],
    )
    def test_tc_rf_601_01_paridad_exacta(self, vector: dict[str, Any]) -> None:
        esperado: dict[int, float] = {
            int(indice): float(valor) for indice, valor in vector["features"].items()
        }

        obtenido = extract_features(vector["url"])

        assert obtenido == esperado


class TestHashEstable:
    """El índice debe ser CRC-32 estable, nunca ``hash()`` de Python."""

    @pytest.mark.parametrize(
        "clave",
        ["tld=com", "r2:^e", "r4:evil", "st:paypal", "pt:login", "n_totlen", "b_sub"],
    )
    def test_hash_feature_usa_crc32_mod_2_17(self, clave: str) -> None:
        esperado = zlib.crc32(clave.encode()) % (1 << 17)

        assert hash_feature(clave) == esperado
        assert 0 <= hash_feature(clave) < N_FEATURES

    def test_valor_observado_de_tld_com(self) -> None:
        assert hash_feature("tld=com") == 68194

    def test_no_us_hash_de_python_en_el_codigo(self) -> None:
        codigo = _codigo_sin_comentarios_ni_cadenas(FEATURES_PATH)

        # "hash_feature(" contiene "hash_", así que el patrón exacto es "hash(".
        assert "hash(" not in codigo


class TestPurezaYRedis:
    """El featurizador es puro: determinista y sin acceso a red (RNF-101)."""

    def test_misma_url_dos_llamadas_da_el_mismo_vector(self) -> None:
        url = "https://paypal.com.evil.cn/signin?q=verify"

        primera = extract_features(url)
        segunda = extract_features(url)

        assert primera == segunda
        assert json.dumps(primera, sort_keys=True) == json.dumps(segunda, sort_keys=True)

    def test_misma_url_en_dos_procesos_con_semilla_aleatoria(self) -> None:
        entorno = {**os.environ, "PYTHONHASHSEED": "random"}

        def ejecutar() -> str:
            completado = subprocess.run(  # noqa: S603 - exe absoluto y argumentos constantes
                [sys.executable, "-c", _CHILD_CODE, str(ROOT)],
                cwd=ROOT,
                env=entorno,
                capture_output=True,
                text=True,
                check=True,
            )
            return completado.stdout.strip()

        primero = ejecutar()
        segundo = ejecutar()
        local = json.dumps(extract_features(_URL_MARCA), sort_keys=True)

        assert primero == segundo == local

    def test_no_intenta_red_aunque_socket_connect_este_parcheado(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def sin_red(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("El featurizador no debe abrir conexiones de red")

        monkeypatch.setattr(socket.socket, "connect", sin_red)

        for url in (_URL_MARCA, _URL_RUTA, "http://128.14.135.237/sb/"):
            vector = extract_features(url)
            assert isinstance(vector, dict)
            assert vector


class TestFamiliasDeCaracteristicas:
    """Todas las familias léxicas del adendo RF-601 deben estar presentes."""

    @pytest.mark.parametrize(
        ("prefijo", "url"),
        [
            ("tld=", _URL_MARCA),
            ("r2:", _URL_RUTA),
            ("r3:", _URL_RUTA),
            ("r4:", _URL_RUTA),
            ("st:", _URL_MARCA),
            ("ht:", _URL_MARCA),
            ("pt:", _URL_MARCA),
            ("ext=", _URL_RUTA),
            ("n_", _URL_MARCA),
            ("b_", _URL_MARCA),
        ],
    )
    def test_existe_clave_legible_con_cada_prefijo(self, prefijo: str, url: str) -> None:
        claves = extract_feature_keys(url).values()

        assert any(clave.startswith(prefijo) for clave in claves)

    def test_marca_en_subdominio_ajeno_genera_b_sub(self) -> None:
        assert "b_sub" in extract_labelled(_URL_MARCA)
        assert extract_labelled(_URL_MARCA)["b_sub"] == 1.0

    def test_valores_son_float_e_indices_estan_en_rango(self) -> None:
        urls = [vector["url"] for vector in _VECTORES] + [_URL_MARCA, _URL_RUTA]

        for url in urls:
            vector = extract_features(url)
            assert all(isinstance(valor, float) for valor in vector.values())
            assert all(0 <= indice < N_FEATURES for indice in vector)


class TestAgrupacionDeEvidencias:
    """Los seis ``rule_id`` del adendo §6 agrupan las claves legibles."""

    @pytest.mark.parametrize(
        ("clave", "grupo"),
        [
            ("tld=cn", "ML_TLD_RISK"),
            ("r3:ple", "ML_DOMAIN_SHAPE"),
            ("n_lenreg", "ML_DOMAIN_SHAPE"),
            ("st:paypal", "ML_HOST_PATTERN"),
            ("ext=php", "ML_PATH_PATTERN"),
            ("b_sub", "ML_BRAND_MISMATCH"),
            ("n_https", "ML_URL_SHAPE"),
        ],
    )
    def test_feature_group_clasifica_los_representantes(self, clave: str, grupo: str) -> None:
        assert feature_group(clave) == grupo

    def test_los_seis_grupos_estan_cubiertos(self) -> None:
        representantes = {
            "tld=com": "ML_TLD_RISK",
            "r2:^e": "ML_DOMAIN_SHAPE",
            "ht:evil": "ML_HOST_PATTERN",
            "pt:login": "ML_PATH_PATTERN",
            "b_path": "ML_BRAND_MISMATCH",
            "n_at": "ML_URL_SHAPE",
        }

        assert {feature_group(clave) for clave in representantes} == set(representantes.values())
        assert all(feature_group(clave) == grupo for clave, grupo in representantes.items())


class TestCasosBorde:
    """Esquema ausente, URL malformada, puerto no estándar y esquema https."""

    def test_url_sin_esquema_equivale_a_http_salvo_n_totlen(self) -> None:
        sin_esquema = extract_labelled("example.com/signin")
        con_esquema = extract_labelled("http://example.com/signin")

        # n_totlen se calcula sobre la cadena original y es la única diferencia
        # entre ambas representaciones; el resto del vector debe ser idéntico.
        sin_longitud = {clave: valor for clave, valor in sin_esquema.items() if clave != "n_totlen"}
        con_longitud = {clave: valor for clave, valor in con_esquema.items() if clave != "n_totlen"}
        assert sin_longitud == con_longitud
        assert sin_esquema["n_https"] == con_esquema["n_https"] == 0.0
        assert set(sin_esquema) ^ set(con_esquema) == set()

    def test_url_malformada_no_lanza_y_devuelve_diccionario(self) -> None:
        vector = extract_features("http://[bad")

        assert isinstance(vector, dict)
        assert vector
        assert all(isinstance(valor, float) for valor in vector.values())

    @pytest.mark.parametrize(
        ("url", "activado"),
        [
            ("https://example.com:8443/x", 1.0),
            ("https://example.com:443/x", 0.0),
            ("http://example.com:80/x", 0.0),
        ],
    )
    def test_puerto_no_estandar_activa_n_port(self, url: str, activado: float) -> None:
        assert extract_labelled(url)["n_port"] == activado

    @pytest.mark.parametrize(
        ("url", "activado"),
        [
            ("https://", 1.0),
            ("http://example.com", 0.0),
        ],
    )
    def test_esquema_https_activa_n_https(self, url: str, activado: float) -> None:
        assert extract_labelled(url)["n_https"] == activado


class TestResilienciaReDoS:
    """Patrones lineales: entradas largas no deben disparar backtracking."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/" + "a" * (4000 - len("https://example.com/")),
            "https://example.com/" + "-a" * 1900,
        ],
        ids=["url_4000_caracteres", "ruta_con_repeticion_de_guiones"],
    )
    def test_extraccion_termina_rapido(self, url: str) -> None:
        inicio = time.perf_counter()

        vector = extract_features(url)

        transcurrido = time.perf_counter() - inicio
        assert transcurrido < 2.0
        assert vector
