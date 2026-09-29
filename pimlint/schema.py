"""Schema de canal: definição declarativa do que cada canal exige dos produtos.

Um schema por canal (YAML) descreve os atributos que o canal aceita ou exige.
O validador compara o CSV de produtos contra esse schema e produz erros
localizados (linha/coluna/motivo) e um completeness score por canal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class Severity(str, Enum):
    """Severidade de um erro, na ordem em que deve ser reportada."""

    CRITICAL = "critical"   # impede envio ao canal
    ERROR = "error"         # rejeita o produto / causa reprocessamento
    WARNING = "warning"     # aceito, mas viola guideline do canal


SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.ERROR: 1, Severity.WARNING: 2}


@dataclass(frozen=True)
class Attribute:
    """Um atributo de produto exigido por um canal."""

    name: str
    type: str = "string"               # string | int | float | bool | date | enum
    required: bool = False
    max_length: int | None = None
    min_length: int | None = None
    values: tuple[str, ...] = ()       # para type=enum
    pattern: str | None = None         # regex
    severity: Severity = Severity.ERROR

    def __post_init__(self) -> None:
        if self.type == "enum" and not self.values:
            raise ValueError(f"atributo enum '{self.name}' precisa de 'values'")
        if self.pattern:
            import re

            try:
                re.compile(self.pattern)
            except re.error as exc:  # pragma: no cover - erro de configuração
                raise ValueError(f"pattern inválido em '{self.name}': {exc}") from exc


@dataclass(frozen=True)
class ChannelSchema:
    """Schema completo de um canal."""

    channel: str
    version: str = "1"
    attributes: tuple[Attribute, ...] = field(default_factory=tuple)

    @property
    def required_attributes(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.attributes if a.required)

    def get(self, name: str) -> Attribute | None:
        for attr in self.attributes:
            if attr.name == name:
                return attr
        return None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChannelSchema":
        raw_attrs = data.get("attributes") or {}
        attributes: list[Attribute] = []
        for name, spec in raw_attrs.items():
            if isinstance(spec, str):              # atalho: "sku: required"
                spec = {"required": spec == "required"}
            spec = dict(spec or {})
            spec.setdefault("name", name)
            if "values" in spec:
                spec["values"] = tuple(spec["values"])
            if "severity" in spec:
                spec["severity"] = Severity(spec["severity"])
            attributes.append(Attribute(**spec))
        return cls(
            channel=data.get("channel", "unknown"),
            version=str(data.get("version", "1")),
            attributes=tuple(attributes),
        )

    @classmethod
    def load(cls, path: str | Path) -> "ChannelSchema":
        path = Path(path)
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        data.setdefault("channel", path.stem)
        return cls.from_dict(data)


def load_schemas(directory: str | Path) -> dict[str, ChannelSchema]:
    """Carrega todos os schemas .yaml/.yml de um diretório, por nome de canal."""
    directory = Path(directory)
    schemas: dict[str, ChannelSchema] = {}
    if not directory.is_dir():
        return schemas
    for file in sorted(directory.glob("*.y*ml")):
        schema = ChannelSchema.load(file)
        schemas[schema.channel] = schema
    return schemas
