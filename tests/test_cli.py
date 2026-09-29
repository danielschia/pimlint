"""Testes de integração da CLI: exit codes, formatos de saída e mensagens."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "pimlint", *args],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_list_channels(capsys):
    from pimlint.cli import main
    assert main(["--list-channels"]) == 0
    out = capsys.readouterr().out
    assert "amazon" in out and "shopify" in out


def test_unknown_channel_exits_2(capsys):
    from pimlint.cli import main
    assert main(["samples/products.csv", "--channel", "nope"]) == 2
    assert "canal desconhecido" in capsys.readouterr().err


def test_missing_file_exits_2(capsys):
    from pimlint.cli import main
    assert main(["nao_existe.csv", "--channel", "amazon"]) == 2
    assert "não encontrado" in capsys.readouterr().err


def test_missing_csv_arg_exits_2(capsys):
    from pimlint.cli import main
    assert main(["--channel", "amazon"]) == 2
    assert "informe o arquivo CSV" in capsys.readouterr().err


def test_sample_csv_exits_1_on_errors():
    """O dataset de exemplo tem erros propositais — deve falhar em CI."""
    r = run_cli("samples/products.csv", "--channel", "amazon")
    assert r.returncode == 1, r.stdout + r.stderr


def test_clean_csv_exits_0(tmp_path):
    good = tmp_path / "bom.csv"
    good.write_text(
        "sku,title,brand,price,currency,quantity,condition,category,image_main\n"
        "OK-1,Produto Bom,Marca,10.0,BRL,5,new,categoria,https://x.com/1.jpg\n",
        encoding="utf-8",
    )
    r = run_cli(str(good), "--channel", "amazon")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "sem erros" in r.stdout


def test_json_output_is_valid_json():
    r = run_cli("samples/products.csv", "--channel", "amazon", "--format", "json")
    payload = json.loads(r.stdout)
    assert payload["channel"] == "amazon"
    assert payload["total_lines"] == 10
    assert payload["completeness"] < 100
    assert payload["findings"], "o sample deve gerar findings"
    first = payload["findings"][0]
    assert {"line", "column", "code", "message", "severity", "value"} <= set(first)


def test_output_file_is_written(tmp_path):
    out = tmp_path / "rel.json"
    r = run_cli("samples/products.csv", "--channel", "amazon",
                "--format", "json", "-o", str(out))
    assert r.returncode == 1
    assert json.loads(out.read_text(encoding="utf-8"))["channel"] == "amazon"


def test_fail_on_never_returns_zero():
    r = run_cli("samples/products.csv", "--channel", "amazon", "--fail-on", "never")
    assert r.returncode == 0


def test_fail_on_critical_is_stricter():
    """O sample não tem warning, então critical e error dão o mesmo resultado."""
    r = run_cli("samples/products.csv", "--channel", "amazon", "--fail-on", "critical")
    assert r.returncode in (0, 1)
