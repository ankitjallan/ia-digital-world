"""Shared helpers for the IA tools - CA. Ankit Jallan | Internal Audit in a Digital World | 10-10-26"""
import warnings
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "datasets"
OUTPUT = ROOT / "outputs"
OUTPUT.mkdir(exist_ok=True)
FY_START, FY_END = pd.Timestamp("2025-04-01"), pd.Timestamp("2026-03-31")
HOLIDAYS = pd.to_datetime(["2025-04-14", "2025-04-15", "2025-08-15", "2025-10-01", "2025-10-02",
                           "2025-10-20", "2026-01-14", "2026-01-26"])
GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def load(workbook):
    """Read every sheet; parse any *Date* column as datetime."""
    path = next(DATA.glob(f"{workbook}*.xlsx"))
    sheets = pd.read_excel(path, sheet_name=None)
    for df in sheets.values():
        for c in df.columns:
            if "Date" in c or c in ("Overdue_Since", "Closed_On", "DL_Valid_Upto", "DOB", "Valid_From", "Valid_To", "Created_On"):
                df[c] = pd.to_datetime(df[c], errors="coerce")
    return sheets


def gstin_valid(g):
    g = str(g).strip().upper()
    if len(g) != 15 or any(ch not in GST_CHARS for ch in g):
        return False
    tot = 0
    for i, ch in enumerate(g[:14]):
        p = GST_CHARS.index(ch) * (2 if i % 2 else 1)
        tot += p // 36 + p % 36
    return GST_CHARS[(36 - tot % 36) % 36] == g[14]


def is_non_working(s):
    s = pd.to_datetime(s)
    return (s.dt.weekday == 6) | s.isin(HOLIDAYS)


def benford(amounts):
    """First-digit Benford test. Returns table and Mean Absolute Deviation (Nigrini)."""
    a = pd.Series(amounts).abs()
    a = a[a >= 10]
    fd = a.astype(str).str.lstrip("0.").str[0].astype(int)
    obs = fd.value_counts(normalize=True).reindex(range(1, 10), fill_value=0)
    exp = pd.Series(np.log10(1 + 1 / np.arange(1, 10)), index=range(1, 10))
    t = pd.DataFrame({"Digit": range(1, 10), "Expected_%": (exp * 100).round(2).values,
                      "Actual_%": (obs * 100).round(2).values, "Count": fd.value_counts().reindex(range(1, 10), fill_value=0).values})
    t["Diff_%"] = (t["Actual_%"] - t["Expected_%"]).round(2)
    mad = float((obs - exp).abs().mean())
    verdict = ("Close conformity" if mad < .006 else "Acceptable" if mad < .012
               else "Marginal" if mad < .015 else "NONCONFORMITY - investigate")
    return t, mad, verdict


class Report:
    """Collects findings test-by-test and writes one Excel report with a Summary sheet."""

    def __init__(self, title):
        self.title, self.tests, self.extra = title, [], {}

    def add(self, test, area, df, risk="High", note=""):
        self.tests.append((test, area, risk, note, df.reset_index(drop=True)))
        flag = "!!" if len(df) else "ok"
        print(f"  [{flag}] {area:<22} {test:<55} {len(df):>5}")

    def sheet(self, name, df):
        self.extra[name] = df

    def save(self, fname):
        summ = pd.DataFrame([{"#": i + 1, "Area": a, "Audit_Test": t, "Risk": r, "Exceptions": len(d), "What_it_checks": n}
                             for i, (t, a, r, n, d) in enumerate(self.tests)])
        path = OUTPUT / fname
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            hdr = pd.DataFrame({self.title: [
                "CA. Ankit Jallan | Internal Audit in a Digital World | 10-10-26",
                f"Generated {dt.datetime.now():%d-%m-%Y %H:%M} on SYNTHETIC data. Tool output = leads, not conclusions: "
                "auditor must verify each exception before reporting."]})
            hdr.to_excel(xw, sheet_name="Summary", index=False)
            summ.to_excel(xw, sheet_name="Summary", index=False, startrow=4)
            for i, (t, a, r, n, d) in enumerate(self.tests):
                d.to_excel(xw, sheet_name=f"T{i + 1:02d}", index=False, startrow=2)
                xw.book[f"T{i + 1:02d}"]["A1"] = f"{t}  ({a}) - {len(d)} exceptions"
            for k, v in self.extra.items():
                v.to_excel(xw, sheet_name=k[:31], index=False)
            for ws in xw.book.worksheets:
                for col in ws.columns:
                    w = max(len(str(c.value)) if c.value is not None else 0 for c in col[2:150]) if len(col) > 2 else 12
                    ws.column_dimensions[col[0].column_letter].width = min(max(11, w + 2), 70)
            xw.book["Summary"].column_dimensions["A"].width = 6
        print(f"\n  Report -> {path.relative_to(ROOT)}  ({sum(len(d) for *_, d in self.tests)} exceptions)\n")
        return summ
