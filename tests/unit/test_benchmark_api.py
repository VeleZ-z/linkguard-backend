"""Pruebas del benchmark de humo de la API (H5-T03).

Cubren la carga estratificada del TSV, el CSV sin URLs en claro, el resumen
recall/FPR, el modo local ASGI con ``PHISHTANK_ENABLED=false`` y el modo
remoto con calentamiento, ``Retry-After`` y reintentos ante HTTP 429.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import httpx
import pytest
import respx
from scripts import benchmark_api


def _write_dataset(path: Path, rows: list[tuple[str, int, str]]) -> Path:
    """Escribe un TSV etiquetado con encabezado ``url/label/source``."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["url", "label", "source"])
        writer.writerows(rows)
    return path


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    """Dataset balanceado de 10 positivos y 10 negativos."""
    rows = [(f"https://phish-{index}.example/login", 1, "jpcert") for index in range(10)]
    rows += [(f"https://legit-{index}.example/news", 0, "top10k") for index in range(10)]
    return _write_dataset(tmp_path / "benchmark.tsv", rows)


class TestLoadUrls:
    """Carga y muestreo del TSV etiquetado."""

    def test_devuelve_url_label_source(self, dataset: Path) -> None:
        samples = benchmark_api.load_urls(dataset, 4, seed=7)

        assert len(samples) == 4
        assert all(len(sample) == 3 for sample in samples)
        assert all(isinstance(sample[1], int) for sample in samples)
        assert {sample[2] for sample in samples} <= {"jpcert", "top10k"}

    def test_sin_limite_devuelve_todas(self, dataset: Path) -> None:
        assert len(benchmark_api.load_urls(dataset, 0, seed=7)) == 20

    def test_estratifica_mitad_y_mitad(self, dataset: Path) -> None:
        samples = benchmark_api.load_urls(dataset, 10, seed=7, stratify=True)

        assert len(samples) == 10
        assert sum(1 for sample in samples if sample[1] == 1) == 5
        assert sum(1 for sample in samples if sample[1] == 0) == 5

    def test_estratifica_sin_limite_equilibra_clases(self, dataset: Path) -> None:
        samples = benchmark_api.load_urls(dataset, 0, seed=7, stratify=True)

        assert len(samples) == 20
        assert sum(1 for sample in samples if sample[1] == 1) == 10
        assert sum(1 for sample in samples if sample[1] == 0) == 10

    def test_sin_columna_url_aborta(self, tmp_path: Path) -> None:
        path = tmp_path / "invalido.tsv"
        path.write_text("dominio\nhttps://example.com\n", encoding="utf-8")

        with pytest.raises(benchmark_api.DatasetFormatError, match="columna 'url'"):
            benchmark_api.load_urls(path, 10, seed=7)

    def test_main_aborta_si_falta_url(self, tmp_path: Path) -> None:
        path = tmp_path / "invalido.tsv"
        path.write_text("dominio\nhttps://example.com\n", encoding="utf-8")

        with pytest.raises(SystemExit) as excinfo:
            benchmark_api.main(["--local", "--input", str(path)])

        assert excinfo.value.code == 2


class TestSalida:
    """CSV y resumen sin exponer URLs."""

    def test_csv_incluye_label_y_source_sin_url(self, tmp_path: Path) -> None:
        sample = ("https://secreto.example/ruta", 1, "jpcert")
        row = benchmark_api._row_from_response(
            sample,
            200,
            {"score": 10, "risk_level": "Bajo", "phishtank_status": "available"},
        )
        output = tmp_path / "salida.csv"

        benchmark_api.write_csv([row], output)
        text = output.read_text(encoding="utf-8")

        assert text.splitlines()[0] == "url_hash,label,source,score,nivel,phishtank_status"
        assert "secreto.example" not in text
        assert hashlib.sha256(sample[0].encode("utf-8")).hexdigest() in text
        assert ",1,jpcert," in text

    def test_summary_calcula_recall_y_fpr(self) -> None:
        rows = [
            {"label": 1, "nivel": "Medio"},
            {"label": 1, "nivel": "Bajo"},
            {"label": 0, "nivel": "Alto"},
            {"label": 0, "nivel": "Bajo"},
            {"label": 0, "nivel": "Bajo"},
            {"label": 0, "nivel": "Bajo"},
        ]

        summary = benchmark_api.summarize(rows)

        assert summary["positivos"] == 2
        assert summary["negativos"] == 4
        assert summary["recall"] == 0.5
        assert summary["fpr"] == 0.25

    def test_summary_sin_clases_no_divide_por_cero(self) -> None:
        summary = benchmark_api.summarize([{"label": 1, "nivel": "Bajo"}])

        assert summary["recall"] == 0.0
        assert summary["fpr"] is None

    def test_display_path_fuera_del_repositorio(self, tmp_path: Path) -> None:
        assert benchmark_api._display_path(tmp_path / "x.csv") == str(
            (tmp_path / "x.csv").resolve()
        )


class TestModoLocal:
    """Ejecución ASGI en proceso con la reputación deshabilitada."""

    def test_run_local_desactiva_phishtank(self) -> None:
        from app.core.config import get_settings

        samples = [
            ("https://example.com/login", 1, "jpcert"),
            ("https://example.org/news", 0, "top10k"),
        ]

        rows = benchmark_api.run_local(samples)

        assert len(rows) == 2
        assert [row["label"] for row in rows] == [1, 0]
        assert [row["source"] for row in rows] == ["jpcert", "top10k"]
        assert all(row["phishtank_status"] == "unavailable" for row in rows)
        assert get_settings().PHISHTANK_ENABLED is True

    def test_main_local_sin_limite_y_summary(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        input_path = _write_dataset(
            tmp_path / "entrada.tsv",
            [
                ("https://example.com/login", 1, "jpcert"),
                ("https://example.org/news", 0, "top10k"),
            ],
        )
        output = tmp_path / "salida.csv"

        code = benchmark_api.main(
            [
                "--local",
                "--input",
                str(input_path),
                "--output",
                str(output),
                "--max-urls",
                "0",
                "--summary",
            ]
        )

        captured = capsys.readouterr()
        assert code == 0
        assert output.exists()
        assert output.read_text(encoding="utf-8").count("\n") == 3
        assert "Resumen (--summary):" in captured.out
        assert "Recall (Medio+Alto)" in captured.out
        assert "FPR (Medio+Alto)" in captured.out
        assert "example.com" not in captured.out
        assert "example.org" not in captured.out


class TestModoRemoto:
    """Calentamiento, rate limit y reintentos con ``respx``."""

    @respx.mock
    def test_calentamiento_y_reintento_429(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        health = respx.get("http://api.test/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )
        analyze = respx.post("http://api.test/api/v1/analyze").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(
                    200,
                    json={
                        "score": 40,
                        "risk_level": "Medio",
                        "phishtank_status": "available",
                    },
                ),
            ]
        )
        sleeps: list[float] = []
        monkeypatch.setattr(benchmark_api, "_sleep", sleeps.append)

        rows = benchmark_api.run_remote(
            [("https://example.com/login", 1, "jpcert")],
            "http://api.test",
            rate=25.0,
        )

        assert health.called
        assert analyze.call_count == 2
        assert sleeps == [0.0]
        assert rows[0]["score"] == 40
        assert rows[0]["nivel"] == "Medio"
        assert rows[0]["label"] == 1
        assert rows[0]["source"] == "jpcert"

    @respx.mock
    def test_agota_reintentos_y_marca_http_429(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        respx.get("http://api.test/health").mock(
            return_value=httpx.Response(200, json={"status": "healthy"})
        )
        analyze = respx.post("http://api.test/api/v1/analyze").mock(
            return_value=httpx.Response(429, headers={"Retry-After": "1"})
        )
        sleeps: list[float] = []
        monkeypatch.setattr(benchmark_api, "_sleep", sleeps.append)

        rows = benchmark_api.run_remote(
            [("https://example.com/login", 1, "jpcert")],
            "http://api.test",
            rate=25.0,
        )

        assert analyze.call_count == benchmark_api.MAX_RETRIES + 1
        assert sleeps == [1.0] * benchmark_api.MAX_RETRIES
        assert rows[0]["nivel"] == "error"
        assert rows[0]["phishtank_status"] == "http_429"

    @respx.mock
    def test_error_de_red_no_aborta(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        respx.get("http://api.test/health").mock(side_effect=httpx.ConnectError("sin red"))
        respx.post("http://api.test/api/v1/analyze").mock(side_effect=httpx.ConnectError("sin red"))
        monkeypatch.setattr(benchmark_api, "_sleep", lambda _delay: None)

        rows = benchmark_api.run_remote(
            [("https://example.com/login", 0, "top10k")],
            "http://api.test",
            rate=25.0,
        )

        assert rows[0]["nivel"] == "error"
        assert rows[0]["phishtank_status"] == "network_error"
        assert rows[0]["label"] == 0
        assert rows[0]["source"] == "top10k"
