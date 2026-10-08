# IA Tools – Internal Audit in a Digital World
**CA. Ankit Jallan | Guwahati | 10-10-26** · All data synthetic · Python 3.10+ with `pandas`, `openpyxl`, `numpy`

| # | Tool | Run | Output (in `outputs/`) |
|---|------|-----|------------------------|
| 1 | Aluminium: O2C, P2P 3-way match, vendor master, GSTR-2B recon, payments, yield, JEs, Benford | `python aluminium_audit.py` | `Aluminium_IA_Exceptions.xlsx` |
| 2 | Co-op bank: IRAC re-computation, sanction powers, LTV, evergreening, KYC/AML, dormant accounts | `python bank_audit.py` | `CoopBank_IA_Exceptions.xlsx` |
| 3 | Hospital: discounts, unbilled consumables, TPA deductions/ageing, doctor payouts | `python hospital_audit.py` | `Hospital_IA_Exceptions.xlsx` |
| 4 | FMCG/Pharma distributor: expiry, drug licence, scheme leakage, teeming & lading, CNs | `python pharma_audit.py` | `Pharma_IA_Exceptions.xlsx` |
| 5 | **DPDP masker**: pseudonymise before any LLM upload; re-identify the LLM output locally | `python dpdp_mask.py mask <file.xlsx>` / `unmask <result> <key.csv>` | `*_MASKED.xlsx` + `*_KEY_DO_NOT_SHARE.csv` |

Each report has a **Summary** sheet (test, risk, count), one sheet per test (T01, T02…), and analysis sheets (Benford, yield heat-map, NPA by branch, deductions by payer, deposit lag by salesman).

**Safe DPDP workflow:** mask locally → send only the masked file to Claude → get findings → unmask locally. The key file never leaves your machine.

> Tool output gives you leads, not conclusions. Verify each exception before reporting. For example, some "split payment" hits are ordinary invoices that happened to be paid on the same day.
