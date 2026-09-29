"""Relatório HTML autocontido: um arquivo, sem servidor, sem CDN.

Gera a partir de um ValidationReport o que um stakeholder de e-commerce precisa
ler antes de decidir: o score, quantos produtos reprovam, e quais atributos
causam mais reprovação. Os erros continuam disponíveis em tabela filtrável.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any

from .schema import Severity
from .validator import ValidationReport

# Referência de mercado usada apenas como linha de comparação no relatório.
COMPLETENESS_TARGET = 95.0

_CSS = """
*,*::before,*::after{box-sizing:border-box}
body{margin:0;padding:32px 28px 64px;background:#fff;color:#14181f;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
 font-size:14px;line-height:1.5}
.wrap{max-width:1080px;margin:0 auto}
header.doc{border-bottom:2px solid #14181f;padding-bottom:18px;margin-bottom:22px}
header.doc h1{margin:0 0 6px;font-size:25px;letter-spacing:-.2px}
header.doc .sub{color:#5b6472;font-size:13px}
header.doc .meta{color:#7b8494;font-size:12px;margin-top:8px}
section{margin-bottom:34px}
h2{font-size:16px;margin:0 0 12px;padding-bottom:6px;border-bottom:1px solid #dfe4ea}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.kpi{background:#f7f9fb;border:1px solid #e3e8ee;border-radius:8px;padding:14px 16px}
.kpi .label{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:#5b6472;font-weight:700}
.kpi .value{font-size:27px;font-weight:700;margin:6px 0 2px;font-variant-numeric:tabular-nums}
.kpi .foot{font-size:12px;color:#5b6472}
.kpi.pass .value{color:#1a7f47}
.kpi.fail .value{color:#c0362c}
.kpi.warn .value{color:#b5730d}
.bar{height:7px;background:#e6eaef;border-radius:4px;margin-top:9px;overflow:hidden}
.bar>span{display:block;height:100%;background:#1a7f47;border-radius:4px}
.bar.warn>span{background:#b5730d}
.bar.fail>span{background:#c0362c}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #e8ecf1;vertical-align:top}
th{background:#f4f6f9;font-size:11px;text-transform:uppercase;letter-spacing:.5px;
 color:#46505e;font-weight:700}
tbody tr:hover{background:#fafbfc}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
td.code{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:12px;color:#5b6472}
td.val{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:12px;
 color:#8a5a00;background:#fdf6e8;border-radius:3px;padding:1px 5px;max-width:230px;
 overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sev{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700}
.sev.critical{background:#fbe9e7;color:#c0362c}
.sev.error{background:#fdf2e0;color:#b5730d}
.sev.warning{background:#e9eef6;color:#2b4c7e}
.filters{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:12px;font-size:13px}
.filters label{display:flex;gap:6px;align-items:center;color:#46505e}
.filters input,.filters select{font:inherit;font-size:13px;padding:5px 8px;
 border:1px solid #ccd3dc;border-radius:5px;background:#fff}
.filters input{width:200px}
.notes{font-size:12px;color:#5b6472;margin:10px 0 0}
.notes code{background:#f2f4f7;padding:1px 5px;border-radius:3px;font-size:11px}
.pill{display:inline-block;background:#eef2f7;color:#2b4c7e;padding:2px 9px;
 border-radius:10px;font-size:11px;font-weight:600}
.empty{padding:22px;background:#f7f9fb;border:1px dashed #ccd3dc;border-radius:8px;
 color:#5b6472;text-align:center}
footer.doc{border-top:1px solid #dfe4ea;padding-top:14px;color:#7b8494;font-size:12px}
@media(max-width:720px){body{padding:20px 16px 48px}
 .kpis{grid-template-columns:repeat(2,1fr)}}
@media print{.filters{display:none}section{break-inside:avoid}}
"""

_JS = """
(function(){
 function apply(){
  var q=(document.getElementById('q')||{}).value||'';
  var sev=(document.getElementById('sev')||{}).value||'all';
  var rows=[].slice.call(document.querySelectorAll('#errs tbody tr'));
  var shown=0;
  rows.forEach(function(tr){
   var text=(tr.getAttribute('data-search')||'').toLowerCase();
   var s=tr.getAttribute('data-severity')||'';
   var okText=!q||text.indexOf(q.toLowerCase())>=0;
   var okSev=sev==='all'||s===sev;
   var show=okText&&okSev;
   tr.style.display=show?'':'none';
   if(show)shown++;
  });
  var c=document.getElementById('shown');
  if(c)c.textContent=String(shown);
 }
 document.addEventListener('input',apply);
 document.addEventListener('change',apply);
})();
"""


def _e(value: Any) -> str:
    """Escapa texto que vai para o HTML."""
    return html.escape(str(value), quote=True)


def _band(score: float) -> str:
    """Classe CSS conforme o score contra a referência de mercado."""
    if score >= COMPLETENESS_TARGET:
        return "pass"
    if score >= COMPLETENESS_TARGET - 10:
        return "warn"
    return "fail"


def _kpi(label: str, value: str, foot: str, band: str = "", bar: float | None = None) -> str:
    parts = [f'<div class="kpi {band}">', f'<div class="label">{_e(label)}</div>',
             f'<div class="value">{_e(value)}</div>', f'<div class="foot">{_e(foot)}</div>']
    if bar is not None:
        width = max(0.0, min(100.0, bar))
        parts.append(f'<div class="bar {_e(band)}"><span style="width:{width:.2f}%"></span></div>')
    parts.append("</div>")
    return "".join(parts)


def _severity_counts(report: ValidationReport) -> dict[str, int]:
    return report.counts_by_severity()


def _failing_lines(report: ValidationReport) -> int:
    """Produtos com ao menos um finding crítico ou de erro."""
    return sum(
        1
        for line in report.line_reports
        if any(f.severity in (Severity.CRITICAL, Severity.ERROR) for f in line.findings)
    )


def _worst_attributes(report: ValidationReport, limit: int = 8) -> list[tuple[str, int, int, str]]:
    """Atributos que mais reprovam: (coluna, contagem, share, severidade mais grave).

    É a pergunta que um time de PIM realmente faz: não 'a linha 47 está errada',
    mas 'que campo está quebrando o feed'.
    """
    counts: dict[str, int] = {}
    worst: dict[str, Severity] = {}
    for finding in report.findings:
        counts[finding.column] = counts.get(finding.column, 0) + 1
        current = worst.get(finding.column)
        if current is None or _sev_rank(finding.severity) < _sev_rank(current):
            worst[finding.column] = finding.severity

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    total = report.total_lines or 1
    out = []
    for column, count in ranked[:limit]:
        out.append((column, count, 100.0 * count / total, worst[column].value))
    return out


def _sev_rank(sev: Severity) -> int:
    return {Severity.CRITICAL: 0, Severity.ERROR: 1, Severity.WARNING: 2}[sev]


def render_report(
    report: ValidationReport,
    source_name: str = "",
    generated_at: datetime | None = None,
) -> str:
    """Renderiza o relatório como um documento HTML autocontido."""
    stamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    score = report.completeness
    band = _band(score)
    counts = _severity_counts(report)
    findings = report.findings
    failing = _failing_lines(report)
    clean = report.total_lines - failing
    total_findings = len(findings)

    # ---- KPIs ----
    kpis = [
        _kpi("Completeness", f"{score:.2f}%",
             f"referência de mercado: {COMPLETENESS_TARGET:.0f}%",
             band=band, bar=score),
        _kpi("Produtos reprovados", f"{failing}", f"de {report.total_lines} no arquivo",
             band="fail" if failing else "pass"),
        _kpi("Violações", f"{total_findings}",
             " ".join(f"{counts[s.value]} {s.value}" for s in Severity),
             band="warn" if total_findings else "pass"),
        _kpi("Produtos aprovados", f"{clean}",
             f"{100.0 * clean / (report.total_lines or 1):.0f}% do arquivo",
             band="pass" if clean == report.total_lines else ""),
    ]

    # ---- piores atributos ----
    worst = _worst_attributes(report)
    if worst:
        rows = []
        for column, count, share, sev in worst:
            rows.append(
                f"<tr><td><strong>{_e(column)}</strong></td>"
                f'<td class="num">{count}</td>'
                f'<td class="num">{share:.1f}%</td>'
                f'<td><span class="sev {_e(sev)}">{_e(sev)}</span></td></tr>'
            )
        worst_table = (
            '<table><thead><tr><th>Atributo</th><th class="num">Ocorrências</th>'
            '<th class="num">% dos produtos</th><th>Severidade</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    else:
        worst_table = '<div class="empty">Nenhuma violação — o arquivo atende ao schema.</div>'

    # ---- tabela de erros ----
    if findings:
        rows = []
        for f in findings:
            search = f"{f.line} {f.column} {f.code} {f.message} {f.value}"
            value_cell = (f'<td class="val">{_e(f.value)}</td>' if f.value
                          else '<td class="val">—</td>')
            rows.append(
                f'<tr data-severity="{_e(f.severity.value)}" '
                f'data-search="{_e(search)}">'
                f'<td class="num">{f.line}</td>'
                f'<td><strong>{_e(f.column)}</strong></td>'
                f'<td><span class="sev {_e(f.severity.value)}">{_e(f.severity.value)}</span></td>'
                f'<td class="code">{_e(f.code)}</td>'
                f"<td>{_e(f.message)}</td>{value_cell}</tr>"
            )
        errors_table = (
            '<div class="filters">'
            '<label>Filtrar <input id="q" type="search" placeholder="coluna, motivo, valor…"></label>'
            '<label>Severidade <select id="sev">'
            '<option value="all">todas</option>'
            f'<option value="critical">critical ({counts["critical"]})</option>'
            f'<option value="error">error ({counts["error"]})</option>'
            f'<option value="warning">warning ({counts["warning"]})</option>'
            "</select></label>"
            f'<span class="pill"><span id="shown">{len(findings)}</span> de {len(findings)}</span>'
            "</div>"
            '<table id="errs"><thead><tr><th class="num">Linha</th><th>Atributo</th>'
            "<th>Severidade</th><th>Código</th><th>Motivo</th><th>Valor</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    else:
        errors_table = '<div class="empty">Nenhuma violação encontrada.</div>'

    # ---- colunas fora do schema ----
    if report.unknown_columns:
        pills = "".join(f'<span class="pill">{_e(c)}</span> ' for c in report.unknown_columns)
        unknown = (f"<p>{pills}</p><p class=\"notes\">Estas colunas existem no CSV mas "
                   f"não são declaradas no schema do canal. Nenhum canal as exigiu, "
                   f"mas se deveriam ser mapeadas, o schema precisa ser atualizado.</p>")
    else:
        unknown = '<div class="empty">Todas as colunas do CSV estão declaradas no schema.</div>'

    product_rows = "".join(
        f'<tr><td class="num">{lr.line}</td>'
        f'<td class="num">{lr.required_met}</td>'
        f'<td class="num">{lr.required_total}</td>'
        f'<td class="num">{lr.completeness:.0f}%</td>'
        f'<td><span class="sev {"error" if lr.completeness < 100 else "warning"}">'
        f'{"reprova" if lr.completeness < 100 else "ok"}</span></td></tr>'
        for lr in report.line_reports
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Feed health report — {_e(report.channel)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">

<header class="doc">
  <h1>Relatório de saúde do feed</h1>
  <div class="sub">Canal <strong>{_e(report.channel)}</strong>
    {'· arquivo <code>' + _e(source_name) + '</code>' if source_name else ''}</div>
  <div class="meta">Gerado em {stamp} por pimlint</div>
</header>

<section>
  <h2>Indicadores</h2>
  <div class="kpis">{''.join(kpis)}</div>
  <p class="notes">Completeness = atributos obrigatórios preenchidos ÷ atributos
  obrigatórios declarados no schema, sobre todos os produtos do arquivo.
  A linha de referência não é um resultado prometido: é a meta de mercado
  usada para marcar o quanto falta.</p>
</section>

<section>
  <h2>Atributos que mais reprovam</h2>
  {worst_table}
  <p class="notes">Ordenado por número de ocorrências. É a ordem de ataque:
  corrigir o primeiro item desta lista destrava mais linhas do que os
  dez seguintes juntos.</p>
</section>

<section>
  <h2>Reprovação por produto</h2>
  <table><thead><tr><th class="num">Linha</th><th class="num">Obrigatórios
  preenchidos</th><th class="num">De</th><th class="num">Completeness</th>
  <th>Situação</th></tr></thead><tbody>{product_rows}</tbody></table>
</section>

<section>
  <h2>Violações ({len(findings)})</h2>
  {errors_table}
</section>

<section>
  <h2>Colunas fora do schema</h2>
  {unknown}
</section>

<footer class="doc">
  pimlint — validador de feeds de produto por canal.
  Gerado a partir de um schema YAML versionado; as regras vivem no schema,
  não neste relatório.
</footer>

</div>
<script>{_JS}</script>
</body>
</html>
"""
