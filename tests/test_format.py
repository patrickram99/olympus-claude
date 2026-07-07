"""
Unit tests for lib/format.py — CSV / JSON / table output.
"""
import csv
import json

from lib.format import fmt_money, fmt_pct, output


def test_output_csv_writes_headers_and_rows(tmp_path):
    """`--fmt csv -o file.csv` must produce a well-formed CSV with our headers."""
    rows = [
        {"Id": 1, "Nombre": "Ana", "TC": 0.123},
        {"Id": 2, "Nombre": "Bob", "TC": 0.456},
    ]
    out = tmp_path / "out.csv"
    output(rows, fmt="csv", out_path=str(out))

    assert out.exists()
    with open(out, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["Id", "Nombre", "TC"]
        data = list(reader)
        assert len(data) == 2
        assert data[0]["Nombre"] == "Ana"
        assert data[1]["Id"] == "2"


def test_output_csv_respects_explicit_headers(tmp_path):
    """When `headers=` is passed, output restricts and orders columns."""
    rows = [{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}]
    out = tmp_path / "out.csv"
    output(rows, fmt="csv", out_path=str(out), headers=["c", "a"])

    with open(out, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["c", "a"]
        row = next(reader)
        assert row["c"] == "3"
        assert row["a"] == "1"


def test_output_json_writes_array(tmp_path):
    rows = [{"k": 1}, {"k": 2}]
    out = tmp_path / "out.json"
    output(rows, fmt="json", out_path=str(out))
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [{"k": 1}, {"k": 2}]


def test_fmt_money_currency_prefix():
    assert fmt_money(1234.5, "PEN") == "PEN 1,234.50"
    assert fmt_money(None) == "—"


def test_fmt_pct_default_precision():
    assert fmt_pct(0.1234) == "12.34%"
    assert fmt_pct(None) == "—"
