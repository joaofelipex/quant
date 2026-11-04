import pandas as pd
import pytest

from quant.data.loaders import check_bars, drop_illiquid_days, load_bars, save_bars

CSV_PROFIT = (
    "Data;Abertura;Máxima;Mínima;Fechamento\n"
    "02/03/2026 09:10;5.099,00;5.101,50;5.098,50;5.100,00\n"
    "02/03/2026 09:05;5097,50;5100,00;5096,00;5099,00\n"
    "02/03/2026 09:10;5099,00;5101,50;5098,50;5100,50\n"  # duplicata do 09:10 -> vence a ultima
)


def test_csv_profit_virgula_decimal_ordem_e_duplicata(tmp_path):
    p = tmp_path / "wdo.csv"
    p.write_text(CSV_PROFIT, encoding="utf-8-sig")
    df = load_bars(p)
    assert list(df.columns) == ["datetime", "open", "high", "low", "close"]
    assert len(df) == 2 and df.datetime.is_monotonic_increasing
    assert df.iloc[0].open == 5097.5
    assert df.iloc[1].close == 5100.5  # ultima ocorrencia


def test_csv_cp1252(tmp_path):
    p = tmp_path / "win.csv"
    p.write_bytes(CSV_PROFIT.encode("cp1252"))
    assert len(load_bars(p)) == 2


def test_xlsx_com_serial_do_excel(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Data", "Abertura", "Máxima", "Mínima", "Fechamento"])
    ws.append([46311.5, 209510, 209550, 209250, 209370])  # 2026-10-16 12:00
    ws.append([46311.496527777781, 209055, 209680, 209035, 209515])  # 11:55
    p = tmp_path / "win.xlsx"
    wb.save(p)
    df = load_bars(p)
    assert df.datetime.tolist() == [pd.Timestamp("2026-10-16 11:55"), pd.Timestamp("2026-10-16 12:00")]
    assert df.close.tolist() == [209515, 209370]


def test_formato_canonico_ida_e_volta(tmp_path):
    p = tmp_path / "wdo.csv"
    p.write_text(CSV_PROFIT, encoding="utf-8-sig")
    df = load_bars(p)
    save_bars(df, tmp_path / "c.csv")
    pd.testing.assert_frame_equal(df, load_bars(tmp_path / "c.csv"))


def test_filtro_de_liquidez():
    dias = [pd.Timestamp("2026-03-02 09:00") + pd.Timedelta(minutes=5 * i) for i in range(100)]
    esparso = [pd.Timestamp("2026-03-03 10:00"), pd.Timestamp("2026-03-03 15:00")]
    df = pd.DataFrame({"datetime": dias + esparso, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})
    out = drop_illiquid_days(df, 60)
    assert len(out) == 100 and len(set(out.datetime.dt.date)) == 1


def test_check_bars_pega_ohlc_invalido_e_saltos():
    df = pd.DataFrame({
        "datetime": pd.date_range("2026-03-02 09:00", periods=3, freq="5min"),
        "open": [100.0, 100.0, 100.0], "high": [101.0, 99.0, 121.0],  # high < open na barra 1
        "low": [99.0, 98.0, 99.0], "close": [100.0, 100.0, 120.0],  # salto de 20%
    })
    r = check_bars(df)
    assert r["invalid_ohlc"] == 1 and r["n_jumps_gt_2pct"] == 1
