"""
Tool 5 - DPDP-safe pseudonymiser. Run this LOCALLY before any file goes to an online LLM.

  python dpdp_mask.py mask   <workbook.xlsx>          -> outputs/<name>_MASKED.xlsx + local key file
  python dpdp_mask.py unmask <findings.xlsx> <key.csv> -> re-identifies tokens in LLM output, locally

Why (DPDP Act 2023 / DPDP Rules 2025):
  * Data minimisation & purpose limitation (s.4-6): send the LLM only what the audit test needs.
  * Reasonable security safeguards (s.8(5)): identifiers never leave your machine.
  * Tokens are consistent (same person -> same token) so joins / duplicate tests still work.
  * The key file stays on your machine - without it the masked file is not personal data in your hands of the vendor.
"""
import sys
import hmac
import hashlib
import secrets
from pathlib import Path

import pandas as pd

from common import OUTPUT

# column name -> treatment
PSEUDO = ["Name", "Patient_Name", "Borrower_Name", "Customer_Name", "Retailer_Name", "Doctor_Name", "UHID", "Customer_ID"]
PARTIAL = {"Mobile": (0, 4), "PAN": (0, 4), "Bank_Account": (0, 4), "Aadhaar_Masked": (0, 4), "Drug_Licence_No": (0, 3)}
GENERALISE = {"DOB": "year_band", "Age": "age_band"}
DROP = ["Address", "Email"]


def token(val, key, prefix):
    return f"{prefix}-{hmac.new(key, str(val).encode(), hashlib.sha256).hexdigest()[:8].upper()}"


def mask(path):
    path = Path(path)
    keyf = OUTPUT / f"{path.stem}_KEY_DO_NOT_SHARE.csv"
    key = secrets.token_bytes(32)
    mapping, log, out = [], [], {}
    for sh, df in pd.read_excel(path, sheet_name=None).items():
        df = df.copy()
        for c in df.columns:
            if c in PSEUDO:
                pre = "ID" if c.endswith(("ID", "UHID")) else "P"
                new = df[c].map(lambda v: token(v, key, pre) if pd.notna(v) and v != "" else v)
                mapping += [{"Token": t, "Original": o, "Column": c} for o, t in zip(df[c], new) if pd.notna(o)]
                df[c] = new
                log.append((sh, c, "Pseudonymised (HMAC-SHA256 token)"))
            elif c in PARTIAL:
                _, keep = PARTIAL[c]
                df[c] = df[c].map(lambda v: ("X" * (len(str(v)) - keep) + str(v)[-keep:]) if pd.notna(v) and v != "" else v)
                log.append((sh, c, f"Masked - last {keep} chars kept"))
            elif c in GENERALISE:
                if GENERALISE[c] == "year_band":
                    yr = pd.to_datetime(df[c]).dt.year
                    df[c] = (yr // 10 * 10).astype("Int64").astype(str) + "s"
                else:
                    df[c] = pd.cut(df[c], [0, 18, 40, 60, 200], labels=["0-17", "18-39", "40-59", "60+"]).astype(str)
                log.append((sh, c, "Generalised"))
            elif c in DROP:
                df = df.drop(columns=c)
                log.append((sh, c, "Dropped - not needed for audit test"))
        out[sh] = df
    dst = OUTPUT / f"{path.stem}_MASKED.xlsx"
    with pd.ExcelWriter(dst, engine="openpyxl") as xw:
        pd.DataFrame(log, columns=["Sheet", "Column", "Treatment"]).to_excel(xw, sheet_name="DPDP_Masking_Log", index=False)
        for sh, df in out.items():
            df.to_excel(xw, sheet_name=sh, index=False)
    pd.DataFrame(mapping).drop_duplicates("Token").to_csv(keyf, index=False)
    print(f"Masked file  -> {dst}\nKey (LOCAL ONLY, never upload) -> {keyf}\nColumns treated: {len(log)}")


def unmask(path, keyf):
    m = dict(pd.read_csv(keyf)[["Token", "Original"]].values)
    path = Path(path)
    sheets = pd.read_excel(path, sheet_name=None) if path.suffix == ".xlsx" else None
    if sheets is None:
        txt = path.read_text(encoding="utf8")
        for t, o in m.items():
            txt = txt.replace(t, str(o))
        dst = path.with_name(path.stem + "_REIDENTIFIED" + path.suffix)
        dst.write_text(txt, encoding="utf8")
    else:
        dst = path.with_name(path.stem + "_REIDENTIFIED.xlsx")
        with pd.ExcelWriter(dst, engine="openpyxl") as xw:
            for sh, df in sheets.items():
                df.replace(m).to_excel(xw, sheet_name=sh, index=False)
    print(f"Re-identified locally -> {dst}")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("mask", "unmask"):
        print(__doc__)
    elif sys.argv[1] == "mask":
        mask(sys.argv[2])
    else:
        unmask(sys.argv[2], sys.argv[3])
