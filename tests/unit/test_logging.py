"""Pruebas del logging estructurado y la anonimización (H1-T10).

Verifican que el JSON emitido contiene los campos del evento y que la URL y la
IP crudas nunca aparecen: solo sus hashes SHA-256.
"""

from __future__ import annotations

import json
import logging
import sys

from app.core.logging import (
    JsonFormatter,
    configure_logging,
    get_logger,
    hash_sensitive,
    log_analyze_event,
)


class _ListHandler(logging.Handler):
    """Captura los ``LogRecord`` emitidos sin escribir a stdout."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _make_record(**extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="linkguard",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="ANALYZE_EVENT",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestHashSensitive:
    """SHA-256 determinista sobre datos sensibles."""

    def test_hash_conocido(self) -> None:
        assert (
            hash_sensitive("abc")
            == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_longitud_hexadecimal(self) -> None:
        assert len(hash_sensitive("http://example.com")) == 64

    def test_determinista(self) -> None:
        assert hash_sensitive("dato") == hash_sensitive("dato")

    def test_valores_distintos_producen_hashes_distintos(self) -> None:
        assert hash_sensitive("http://a.example") != hash_sensitive("http://b.example")

    def test_cadena_vacia(self) -> None:
        assert len(hash_sensitive("")) == 64


class TestJsonFormatter:
    """El formateador produce una línea JSON válida."""

    def test_campos_basicos(self) -> None:
        payload = json.loads(JsonFormatter().format(_make_record()))
        assert payload["level"] == "INFO"
        assert payload["logger"] == "linkguard"
        assert payload["message"] == "ANALYZE_EVENT"
        assert "timestamp" in payload

    def test_incluye_campos_extra(self) -> None:
        record = _make_record(event_type="ANALYZE_EVENT", score=0)
        payload = json.loads(JsonFormatter().format(record))
        assert payload["event_type"] == "ANALYZE_EVENT"
        assert payload["score"] == 0

    def test_incluye_excepcion(self) -> None:
        try:
            raise ValueError("fallo controlado")
        except ValueError:
            record = _make_record()
            record.exc_info = sys.exc_info()

        payload = json.loads(JsonFormatter().format(record))
        assert "exception" in payload
        assert "ValueError" in payload["exception"]

    def test_serializa_valores_no_json(self) -> None:
        record = _make_record(objeto=object())
        payload = json.loads(JsonFormatter().format(record))
        assert "object" in payload["objeto"]


class TestConfigureLogging:
    """Configuración idempotente del logger del servicio."""

    def test_configura_handler_json(self) -> None:
        logger = configure_logging()
        assert logger.name == "linkguard"
        assert logger.propagate is False
        assert any(isinstance(handler.formatter, JsonFormatter) for handler in logger.handlers)

    def test_es_idempotente(self) -> None:
        logger = configure_logging()
        handlers_before = len(logger.handlers)
        configure_logging()
        assert len(logger.handlers) == handlers_before

    def test_get_logger_devuelve_el_mismo_logger(self) -> None:
        assert get_logger() is get_logger()

    def test_get_logger_configura_si_no_hay_handlers(self) -> None:
        logger = logging.getLogger("linkguard")
        saved = list(logger.handlers)
        try:
            for handler in saved:
                logger.removeHandler(handler)
            assert get_logger().handlers
        finally:
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
            for handler in saved:
                logger.addHandler(handler)


class TestLogAnalyzeEvent:
    """Evento ANALYZE_EVENT anonimizado."""

    def test_evento_anonimizado(self) -> None:
        url = "http://example.com/login"
        client_ip = "203.0.113.9"
        logger = get_logger()
        handler = _ListHandler()
        logger.addHandler(handler)
        try:
            event = log_analyze_event(
                url=url,
                client_ip=client_ip,
                score=0,
                risk_level="Bajo",
                phishtank_status="unavailable",
                rules_activated_count=0,
                execution_time_ms=12.3456,
            )
        finally:
            logger.removeHandler(handler)

        assert event["event_type"] == "ANALYZE_EVENT"
        assert event["url_hash_sha256"] == hash_sensitive(url)
        assert event["client_ip_hash"] == hash_sensitive(client_ip)
        assert event["score"] == 0
        assert event["risk_level"] == "Bajo"
        assert event["phishtank_status"] == "unavailable"
        assert event["rules_activated_count"] == 0
        assert event["execution_time_ms"] == 12.35

        serializado = json.dumps(event, ensure_ascii=False)
        assert url not in serializado
        assert client_ip not in serializado

        assert len(handler.records) == 1
        record = handler.records[0]
        assert record.event_type == "ANALYZE_EVENT"
        assert record.url_hash_sha256 == hash_sensitive(url)
        assert record.client_ip_hash == hash_sensitive(client_ip)

    def test_ip_ausente_se_hashea_como_cadena_vacia(self) -> None:
        event = log_analyze_event(
            url="http://example.com",
            client_ip=None,
            score=0,
            risk_level="Bajo",
            phishtank_status="unavailable",
            rules_activated_count=0,
            execution_time_ms=1.0,
        )
        assert event["client_ip_hash"] == hash_sensitive("")
