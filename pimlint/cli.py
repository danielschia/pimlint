"""CLI do pimlint.

    python -m pimlint produtos.csv --channel amazon
    python -m pimlint produtos.csv --channel shopify --format json --output relatorio.json
    python -m pimlint --list-channels
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .schema import load_schemas
from .validator import Severity, validate_file

DEFAULT_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def _fail(message: str, code: int = 2) -> int:
    print(f"erro: {message}", file=sys.stderr)
    return code


def _render_text(report, show_all: bool) -> str:
    lines: list[str] = []
    counts = report.counts_by_severity()

    lines.append(f"canal: {report.channel}")
    lines.append(f"linhas: {report.total_lines}")
    lines.append(f"completeness: {report.completeness:.2f}%")
    lines.append(
        "erros: "
        + ", ".join(f"{counts[s.value]} {s.value}" for s in Severity)
    )

    if report.unknown_columns:
        lines.append(f"colunas fora do schema: {', '.join(report.unknown_columns)}")

    findings = report.findings
    if not show_all:
        critical_error = [f for f in findings
                          if f.severity in (Severity.CRITICAL, Severity.ERROR)]
        shown = critical_error[:20]
        if len(critical_error) > 20:
            lines.append(f"\n(mostrando 20 de {len(critical_error)} erros "
                         f"críticos/error — use --all para ver todos)")
    else:
        shown = findings

    if shown:
        lines.append("")
        for f in shown:
            lines.append(
                f"  linha {f.line:>5}  {f.severity.value.upper():<8}  "
                f"{f.column}: {f.message}"
            )
    else:
        lines.append("\nsem erros — o arquivo atende ao schema do canal")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pimlint",
        description="Valida um CSV de produtos contra o schema de um canal.",
    )
    parser.add_argument("csv_file", nargs="?", help="CSV de produtos a validar")
    parser.add_argument("--channel", "-c", help="nome do canal (ex.: amazon)")
    parser.add_argument("--schemas", default=str(DEFAULT_SCHEMA_DIR),
                        help="diretório com os schemas YAML")
    parser.add_argument("--format", "-f", default="text",
                        choices=("text", "json"), help="formato da saída")
    parser.add_argument("--output", "-o", help="escreve a saída em arquivo")
    parser.add_argument("--all", action="store_true",
                        help="mostra todas as ocorrências, não só as 20 primeiras")
    parser.add_argument("--fail-on", default="error",
                        choices=("critical", "error", "warning", "never"),
                        help="nível que faz o comando sair com código 1 (padrão: error)")
    parser.add_argument("--list-channels", action="store_true",
                        help="lista os canais disponíveis e sai")
    args = parser.parse_args(argv)

    schemas = load_schemas(args.schemas)
    if not schemas:
        return _fail(f"nenhum schema encontrado em {args.schemas}")

    if args.list_channels:
        for name in sorted(schemas):
            schema = schemas[name]
            req = len(schema.required_attributes)
            print(f"{name}  (v{schema.version}, {req} obrigatórios, "
                  f"{len(schema.attributes)} atributos)")
        return 0

    if not args.csv_file:
        return _fail("informe o arquivo CSV (ou use --list-channels)")
    if not args.channel:
        return _fail("informe --channel (use --list-channels para ver as opções)")

    csv_path = Path(args.csv_file)
    if not csv_path.is_file():
        return _fail(f"arquivo não encontrado: {csv_path}")

    schema = schemas.get(args.channel)
    if schema is None:
        return _fail(
            f"canal desconhecido: {args.channel}. "
            f"Disponíveis: {', '.join(sorted(schemas))}"
        )

    report = validate_file(str(csv_path), schema)

    if args.format == "json":
        output = json.dumps(report.as_dict(), ensure_ascii=False, indent=2)
    else:
        output = _render_text(report, show_all=args.all)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"relatório escrito em {args.output}", file=sys.stderr)
    else:
        print(output)

    if args.fail_on == "never":
        return 0
    threshold = Severity(args.fail_on)
    order = [Severity.CRITICAL, Severity.ERROR, Severity.WARNING]
    limit = order.index(threshold)
    for finding in report.findings:
        if order.index(finding.severity) <= limit:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
