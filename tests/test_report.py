"""Testes do relatório HTML.

Verificam que o documento gerado é autocontido, que o HTML é válido o bastante
para abrir em qualquer navegador, e que os números do relatório batem com o
ValidationReport de origem.
"""

import json
import re
from datetime import datetime
from html.parser import HTMLParser

import pytest

from pimlint.report import COMPLETENESS_TARGET, render_report
from pimlint.schema import ChannelSchema
from pimlint.validator import validate_file


@pytest.fixture
def schema():
    return ChannelSchema.from_dict({
        "channel": "amazon",
        "attributes": {
            "sku": {"type": "string", "required": True},
            "title": {"type": "string", "required": True, "min_length": 3},
            "price": {"type": "float", "required": True},
            "currency": {"type": "enum", "required": True, "values": ["BRL", "USD"]},
        },
    })


def _write(tmp_path, body, schema):
    csv = tmp_path / "p.csv"
    csv.write_text(body, encoding="utf-8")
    return validate_file(str(csv), schema)


class TagBalance(HTMLParser):
    """Detecta tags do HTML que abrem e não fecham."""

    VOID = {"meta", "br", "hr", "img", "input", "link", "source"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack:
            self.problems.append(f"closing </{tag}> with empty stack")
        elif self.stack[-1] != tag:
            self.problems.append(f"expected </{self.stack[-1]}>, got </{tag}>")
            self.stack.pop()
        else:
            self.stack.pop()


def test_is_a_whole_html_document(tmp_path, schema):
    report = _write(tmp_path, "sku,title,price,currency\nAB-1,Produto,1,BRL\n", schema)
    out = render_report(report, source_name="p.csv")
    assert out.startswith("<!DOCTYPE html>")
    assert out.rstrip().endswith("</html>")
    assert "<html lang=\"pt-BR\">" in out


def test_tags_are_balanced(tmp_path, schema):
    report = _write(tmp_path,
        "sku,title,price,currency\n,Ok,1,BRL\nAB-1,Ok,abc,BRL\n", schema)
    out = render_report(report, source_name="p.csv")
    parser = TagBalance()
    parser.feed(out)
    assert parser.problems == [], parser.problems
    assert parser.stack == [], f"unclosed: {parser.stack}"


def test_is_self_contained_no_external_refs(tmp_path, schema):
    report = _write(tmp_path, "sku,title,price,currency\nAB-1,Produto,1,BRL\n", schema)
    out = render_report(report, source_name="p.csv")
    # nenhum recurso externo: sem script src, sem stylesheet link, sem src/href http
    assert "<script src" not in out
    assert 'rel="stylesheet"' not in out
    assert not re.search(r'(src|href)="https?://', out)


def test_numbers_match_the_report(tmp_path, schema):
    # "Ok" tem 2 caracteres e viola min_length:3 — por isso as DUAS linhas reprovam.
    report = _write(tmp_path,
        "sku,title,price,currency\n"
        ",Produto,1,BRL\n"        # linha 2: falta sku -> reprova
        "AB-1,Ok,1,BRL\n",          # linha 3: title curto demais -> reprova
        schema)
    out = render_report(report, source_name="p.csv")
    assert f"{report.completeness:.2f}%" in out
    assert f"{COMPLETENESS_TARGET:.0f}%" in out

    def kpi(label: str) -> str:
        m = re.search(
            r'<div class="label">' + re.escape(label) + r'</div>'
            r'<div class="value">([^<]*)</div>',
            out,
        )
        assert m, f"KPI '{label}' não encontrado"
        return m.group(1)

    assert kpi("Completeness") == f"{report.completeness:.2f}%"
    assert kpi("Produtos reprovados") == "2"
    assert kpi("Produtos aprovados") == "0"
    assert kpi("Violações") == str(len(report.findings))


def test_clean_row_is_counted_as_approved(tmp_path, schema):
    report = _write(tmp_path,
        "sku,title,price,currency\n"
        "AB-1,Produto,1,BRL\n", schema)
    out = render_report(report, source_name="p.csv")
    assert '<div class="value">0</div>' in out          # 0 reprovados
    assert f'<div class="value">{report.total_lines}</div>' in out  # 1 aprovado


def test_clean_file_shows_no_violations(tmp_path, schema):
    report = _write(tmp_path, "sku,title,price,currency\nAB-1,Produto,1,BRL\n", schema)
    out = render_report(report, source_name="p.csv")
    assert "Nenhuma violação" in out
    assert 'class="empty"' in out


def test_html_is_escaped(tmp_path, schema):
    """Valor com HTML/XML deve sair escapado, não injetado."""
    report = _write(tmp_path, "sku,title,price,currency\nAB-1,Produto,1,<script>alert(1)</script>\n", schema)
    out = render_report(report, source_name="p.csv")
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_filter_controls_present_when_findings(tmp_path, schema):
    report = _write(tmp_path, "sku,title,price,currency\n,Ok,1,BRL\n", schema)
    out = render_report(report, source_name="p.csv")
    assert 'id="q"' in out
    assert 'id="sev"' in out
    assert 'id="errs"' in out
    assert "data-severity=" in out


def test_worst_attributes_table_ranks_by_count(tmp_path, schema):
    report = _write(tmp_path,
        "sku,title,price,currency\n"
        ",Ok,1,BRL\n"
        ",Ok,1,BRL\n"
        "AB-1,Ok,1,BRL\n", schema)
    out = render_report(report, source_name="p.csv")
    assert "Atributos que mais reprovam" in out
    i = out.find("Atributos que mais reprovam")
    seg = out[i:i + 1500]
    assert "sku" in seg
    # sku aparece duas vezes -> contagem 2
    assert re.search(r"sku.*?2", seg, re.S | re.I)


def test_timestamp_is_injectable(tmp_path, schema):
    report = _write(tmp_path, "sku,title,price,currency\nAB-1,Produto,1,BRL\n", schema)
    stamp = datetime(2026, 9, 30, 14, 30)
    out = render_report(report, source_name="p.csv", generated_at=stamp)
    assert "2026-09-30 14:30" in out


def test_unknown_columns_section(tmp_path, schema):
    report = _write(tmp_path, "sku,title,price,currency,extra\nAB-1,Produto,1,BRL,x\n", schema)
    out = render_report(report, source_name="p.csv")
    assert "Colunas fora do schema" in out
    assert "extra" in out


def test_large_report_stays_valid(tmp_path, schema):
    body = "sku,title,price,currency\n" + "".join(
        f",Produto,abc,XYZ\n" for _ in range(300)
    )
    report = _write(tmp_path, body, schema)
    out = render_report(report, source_name="big.csv")
    parser = TagBalance()
    parser.feed(out)
    assert parser.stack == []
    assert out.count("<tr") > 300
