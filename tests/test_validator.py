import pytest

from pimlint.schema import ChannelSchema, Severity
from pimlint.validator import validate_file, validate_row


@pytest.fixture
def schema():
    return ChannelSchema.from_dict({
        "channel": "test",
        "attributes": {
            "sku": {"type": "string", "required": True, "max_length": 10},
            "title": {"type": "string", "required": True, "min_length": 3},
            "price": {"type": "float", "required": True},
            "qty": {"type": "int", "required": True},
            "currency": {"type": "enum", "required": True, "values": ["BRL", "USD"]},
            "url": {"type": "string", "required": False, "pattern": "^https?://"},
        },
    })


def codes(findings):
    return sorted(f.code for f in findings)


def test_clean_row_has_no_findings(schema):
    row = {"sku": "AB-1", "title": "Valid", "price": "10.5",
           "qty": "3", "currency": "BRL", "url": "https://x.com/i.jpg"}
    report = validate_row(row, 2, schema)
    assert report.findings == []
    assert report.completeness == 100.0


def test_missing_required_is_critical(schema):
    report = validate_row({"sku": "", "title": "Ok", "price": "1",
                           "qty": "1", "currency": "BRL"}, 7, schema)
    missing = [f for f in report.findings if f.code == "missing_required"]
    assert len(missing) == 1
    assert missing[0].column == "sku"
    assert missing[0].severity is Severity.CRITICAL
    assert missing[0].line == 7
    assert report.completeness == pytest.approx(80.0)


def test_type_mismatch_float(schema):
    report = validate_row({"sku": "AB-1", "title": "Ok", "price": "abc",
                           "qty": "1", "currency": "BRL"}, 3, schema)
    assert "type_mismatch" in codes(report.findings)


def test_type_mismatch_int(schema):
    report = validate_row({"sku": "AB-1", "title": "Ok", "price": "1",
                           "qty": "3.7", "currency": "BRL"}, 3, schema)
    assert "type_mismatch" in codes(report.findings)


def test_enum_rejects_unknown_value(schema):
    report = validate_row({"sku": "AB-1", "title": "Ok", "price": "1",
                           "qty": "1", "currency": "XYZ"}, 4, schema)
    enum_findings = [f for f in report.findings if f.code == "type_mismatch"]
    assert enum_findings
    assert "BRL" in enum_findings[0].message


def test_max_length_and_min_length(schema):
    long_row = validate_row({"sku": "X" * 20, "title": "Ok", "price": "1",
                             "qty": "1", "currency": "BRL"}, 2, schema)
    assert "too_long" in codes(long_row.findings)

    short_row = validate_row({"sku": "AB-1", "title": "ab", "price": "1",
                              "qty": "1", "currency": "BRL"}, 2, schema)
    assert "too_short" in codes(short_row.findings)


def test_pattern_mismatch(schema):
    report = validate_row({"sku": "AB-1", "title": "Ok", "price": "1",
                           "qty": "1", "currency": "BRL", "url": "ftp://x.com"},
                          2, schema)
    assert "pattern_mismatch" in codes(report.findings)


def test_optional_absent_is_not_an_error(schema):
    report = validate_row({"sku": "AB-1", "title": "Ok", "price": "1",
                           "qty": "1", "currency": "BRL"}, 2, schema)
    assert not any(f.column == "url" for f in report.findings)


def test_empty_value_is_absent_not_type_error(schema):
    """Vazio não deve virar erro de tipo — é ausência."""
    report = validate_row({"sku": "AB-1", "title": "Ok", "price": "",
                           "qty": "1", "currency": "BRL"}, 2, schema)
    types = [f for f in report.findings if f.code == "type_mismatch"]
    assert types == []


def test_findings_sorted_by_severity_then_line(tmp_path, schema):
    csv = tmp_path / "p.csv"
    csv.write_text(
        "sku,title,price,qty,currency,url\n"
        ",Ok,1,1,BRL,\n"
        "AB-1,Ok,abc,1,BRL,https://x.com\n",
        encoding="utf-8",
    )
    report = validate_file(str(csv), schema)
    severities = [f.severity for f in report.findings]
    order = {Severity.CRITICAL: 0, Severity.ERROR: 1, Severity.WARNING: 2}
    ranks = [order[s] for s in severities]
    assert ranks == sorted(ranks), "findings devem vir por severidade"


def test_unknown_columns_detected(tmp_path, schema):
    csv = tmp_path / "p.csv"
    csv.write_text(
        "sku,title,price,qty,currency,coluna_zeta\n"
        "AB-1,Ok,1,1,BRL,x\n",
        encoding="utf-8",
    )
    report = validate_file(str(csv), schema)
    assert report.unknown_columns == ["coluna_zeta"]


def test_file_report_totals(tmp_path, schema):
    csv = tmp_path / "p.csv"
    csv.write_text(
        "sku,title,price,qty,currency\n"
        "AB-1,Ok,1,1,BRL\n"
        ",Ok,1,1,BRL\n"
        "AB-2,Ok,1,1,BRL\n",
        encoding="utf-8",
    )
    report = validate_file(str(csv), schema)
    assert report.total_lines == 3
    # 4 de 5 required em duas linhas, 5 de 5 na outra
    assert report.completeness == pytest.approx((5 + 4 + 5) / 15 * 100)
    assert report.counts_by_severity()["critical"] == 1


def test_utf8_bom_and_crlf_are_handled(tmp_path, schema):
    csv = tmp_path / "p.csv"
    csv.write_bytes(
        "sku,title,price,qty,currency\r\nAB-1,Produto Ok,1,1,BRL\r\n".encode("utf-8-sig")
    )
    report = validate_file(str(csv), schema)
    assert report.total_lines == 1
    assert report.findings == []


def test_as_dict_is_json_serialisable(tmp_path, schema):
    import json
    csv = tmp_path / "p.csv"
    csv.write_text("sku,title,price,qty,currency\n,Ok,1,1,BRL\n", encoding="utf-8")
    payload = validate_file(str(csv), schema).as_dict()
    assert json.loads(json.dumps(payload))["channel"] == "test"
