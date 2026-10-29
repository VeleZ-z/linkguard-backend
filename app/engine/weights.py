"""Matriz estática de pesos de penalización del motor de reglas (RF-301).

Cada entrada asigna los puntos ``w_i`` que aporta una regla activada al
puntaje total de riesgo, acotado a un máximo de 100 (``min(100, sum)``).

La matriz debe coincidir exactamente con la tabla del §3 de la especificación
de requisitos:

| Regla | Peso | Nombre |
| :--- | :---: | :--- |
| MATCH_PHISHTANK | 50 | Coincidencia en lista negra de PhishTank |
| F02 | 25 | Dirección IP directa |
| F06 | 20 | Símbolo '@' en la URL |
| F08 | 20 | Desvío de esquema en path/query |
| F11 | 15 | Palabras clave de ingeniería social |
| F05 | 15 | Acortador de URL |
| F04 | 15 | Entropía de Shannon alta |
| F09 | 10 | Puerto no estándar |
| F03 | 10 | Múltiples subdominios |
| F01 | 10 | Longitud excesiva de URL |
| F07 | 8 | Guiones en nombre de dominio |
| F10 | 7 | Ratio de caracteres especiales > 15 % |
"""

from __future__ import annotations

from typing import Final

WEIGHTS: Final[dict[str, int]] = {
    "MATCH_PHISHTANK": 50,
    "F02": 25,
    "F06": 20,
    "F08": 20,
    "F11": 15,
    "F05": 15,
    "F04": 15,
    "F09": 10,
    "F03": 10,
    "F01": 10,
    "F07": 8,
    "F10": 7,
}

# Suma teórica de todos los pesos (útil para validar el tope de 100 en scoring).
MAX_WEIGHT_SUM: Final[int] = sum(WEIGHTS.values())

__all__ = ["WEIGHTS", "MAX_WEIGHT_SUM"]
