"""Motor de validação: compara linhas de produto contra um ChannelSchema.

Cada violação vira um Finding com severidade, localização (linha/coluna) e
motivo — o formato que um time de PIM precisa para triage rápido de feed.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

from .schema import SEVERITY_ORDER, Attribute, ChannelSchema, Severity


@dataclass(frozen=True)
class Finding:
    """Uma violação localizada no arquivo de produtos."""

    line: int          # número da linha no CSV (1 = cabeçalho)
    column: str        # nome do atributo
    code: str          # identificador estável, ex. "missing_required"
    message: str       # explicação legível
    severity: Severity
    value: str = ""    # valor encontrado (truncado)

    def as_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "column": self.column,
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "value": self.value[:80],
        }


@dataclass
class LineReport:
    """Resultado da validação de uma linha de produto."""

    line: int
    findings: list[Finding]
    required_met: int
    required_total: int

    @property
    def is_valid(self) -> bool:
        return not any(f.severity is Severity.WARNING for f in self.findings)

    @property
    def completeness(self) -> float:
        if self.required_total == 0:
            return 100.0
        return 100.0 * self.required_met / self.required_total


@dataclass
class ValidationReport:
    """Resultado da validação de um arquivo contra um schema."""

    channel: str
    total_lines: int
    line_reports: list[LineReport]
    unknown_columns: list[str]

    @property
    def findings(self) -> list[Finding]:
        out: list[Finding] = []
        for report in self.line_reports:
            out.extend(report.findings)
        # mais severidade primeiro, depois linha
        out.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.line))
        return out

    @property
    def completeness(self) -> float:
        """Completeness médio do arquivo: required atendidos / required totais."""
        met = sum(r.required_met for r in self.line_reports)
        total = sum(r.required_total for r in self.line_reports)
        if total == 0:
            return 100.0
        return 100.0 * met / total

    def counts_by_severity(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Severity}
        for f in self.findings:
            counts[f.severity.value] += 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "total_lines": self.total_lines,
            "completeness": round(self.completeness, 2),
            "counts_by_severity": self.counts_by_severity(),
            "unknown_columns": self.unknown_columns,
            "findings": [f.as_dict() for f in self.findings],
        }


def _coerce(value: str, attr: Attribute) -> tuple[bool, str]:
    """Valida o tipo de um valor. Retorna (ok, motivo_se_falhou)."""
    raw = value.strip()
    if not raw:
        return True, ""          # vazio é tratado como ausente, não como erro de tipo

    if attr.type == "int":
        try:
            int(raw)
        except ValueError:
            return False, f"esperado inteiro, encontrado '{raw}'"
    elif attr.type == "float":
        try:
            float(raw)
        except ValueError:
            return False, f"esperado número decimal, encontrado '{raw}'"
    elif attr.type == "bool":
        if raw.lower() not in {"true", "false", "1", "0", "sim", "não", "yes", "no"}:
            return False, f"esperado booleano, encontrado '{raw}'"
    elif attr.type == "date":
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                date.fromisoformat(raw) if fmt == "%Y-%m-%d" else date.strptime(raw, fmt)
                return True, ""
            except ValueError:
                continue
        return False, f"esperado data (YYYY-MM-DD), encontrado '{raw}'"
    elif attr.type == "enum":
        if raw not in attr.values:
            return False, (f"'{raw}' fora dos valores permitidos: "
                           f"{', '.join(attr.values)}")
    return True, ""


def validate_row(
    row: dict[str, str],
    line_number: int,
    schema: ChannelSchema,
) -> LineReport:
    """Valida uma linha de produto contra o schema do canal."""
    findings: list[Finding] = []
    required_met = 0
    required_total = len(schema.required_attributes)

    for attr in schema.attributes:
        raw = row.get(attr.name, "")
        value = raw.strip() if raw else ""

        if not value:
            if attr.required:
                findings.append(Finding(
                    line=line_number,
                    column=attr.name,
                    code="missing_required",
                    message=f"atributo obrigatório ausente: {attr.name}",
                    severity=Severity.CRITICAL,
                ))
            continue

        if attr.required:
            required_met += 1

        if attr.min_length and len(value) < attr.min_length:
            findings.append(Finding(
                line=line_number, column=attr.name,
                code="too_short",
                message=f"mínimo de {attr.min_length} caracteres, tem {len(value)}",
                severity=attr.severity, value=value,
            ))

        if attr.max_length and len(value) > attr.max_length:
            findings.append(Finding(
                line=line_number, column=attr.name,
                code="too_long",
                message=f"máximo de {attr.max_length} caracteres, tem {len(value)}",
                severity=attr.severity, value=value,
            ))

        if attr.pattern and not re.match(attr.pattern, value):
            findings.append(Finding(
                line=line_number, column=attr.name,
                code="pattern_mismatch",
                message=f"não casa com o padrão esperado: {attr.pattern}",
                severity=attr.severity, value=value,
            ))

        ok, reason = _coerce(value, attr)
        if not ok:
            findings.append(Finding(
                line=line_number, column=attr.name,
                code="type_mismatch",
                message=reason, severity=attr.severity, value=value,
            ))

    return LineReport(
        line=line_number,
        findings=findings,
        required_met=required_met,
        required_total=required_total,
    )


def iter_rows(path: str) -> Iterator[tuple[int, dict[str, str]]]:
    """Itera (linha, row) de um CSV, 1-indexado; linha 1 é o cabeçalho."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader, start=2):
            yield i, {k: (v if v is not None else "") for k, v in row.items() if k}


def validate_file(path: str, schema: ChannelSchema) -> ValidationReport:
    """Valida um CSV inteiro contra o schema e devolve o relatório consolidado."""
    reports: list[LineReport] = []
    seen_columns: set[str] = set()

    for line_number, row in iter_rows(path):
        seen_columns.update(row.keys())
        reports.append(validate_row(row, line_number, schema))

    declared = {a.name for a in schema.attributes}
    unknown = sorted(c for c in seen_columns if c not in declared)

    return ValidationReport(
        channel=schema.channel,
        total_lines=len(reports),
        line_reports=reports,
        unknown_columns=unknown,
    )
