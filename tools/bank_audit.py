"""
Tool 2 - Concurrent / internal audit analytics for Luit Valley Urban Co-operative Bank Ltd.
IRAC re-computation, credit sanction controls, KYC/AML red flags, dormant accounts.
Run: python bank_audit.py
"""
import pandas as pd
from common import load, Report, FY_END

D = load("02_CoopBank")
R = Report("Co-op Bank - Luit Valley UCB - Concurrent Audit Analytics")
print("\n== Co-op Bank : loan book & KYC ==")
L, K = D["Loan_Book"].copy(), D["KYC_Register"]

# IRAC recomputation
L["DPD"] = (FY_END - L.Overdue_Since).dt.days.fillna(0).astype(int)
L["Asset_Class_Computed"] = pd.cut(L.DPD, [-1, 90, 455, 10**6], labels=["Standard", "Sub-Standard", "Doubtful"]).astype(str)
mis = L[L.Asset_Class_Computed != L.Asset_Class_Reported].copy()
mis["Extra_Provision"] = (mis.Outstanding_31Mar26 * mis.Asset_Class_Computed.map({"Sub-Standard": .10, "Doubtful": .25}).fillna(0)).round(0)
R.add("NPA not classified (IRAC)", "Asset Classification", mis, note="Computed DPD class vs reported; indicative provision")
print(f"     -> indicative provision shortfall Rs {mis.Extra_Provision.sum():,.0f}")

dp = L.merge(D["Delegation_of_Powers"], left_on="Sanctioned_By", right_on="Officer", how="left")
R.add("Sanction beyond delegated power", "Credit Sanction", dp[dp.Sanction_Limit > dp.Max_Sanction_Power], note="Limit > officer's power")
g = L[L.Scheme == "Gold"].assign(LTV_pct=lambda x: (x.Outstanding_31Mar26 / x.Security_Value * 100).round(1))
R.add("Gold loan LTV > 75%", "Security", g[g.LTV_pct > 75], note="RBI LTV cap")
R.add("Stale security valuation", "Security", L[(L.Security_Type == "Property") & (L.Last_Valuation_Date < FY_END - pd.DateOffset(years=3))],
      "Medium", "Property valued > 3 years ago")
lk = L.merge(K[["Customer_ID", "PAN"]], on="Customer_ID")
R.add("Loan > 5 lakh without PAN", "KYC", lk[(lk.Outstanding_31Mar26 > 500000) & (lk.PAN.isna() | (lk.PAN == ""))], note="Large exposure, PAN missing")
ev = L.merge(D["Closed_Loans"], on="Customer_ID", suffixes=("", "_Old"))
ev["Gap_Days"] = (ev.Closed_On - ev.Sanction_Date).dt.days
R.add("Evergreening", "Credit Monitoring", ev[(ev.Gap_Days.abs() <= 7) & (ev.DPD_at_Closure > 30)],
      note="Overdue old loan closed within 7 days of new sanction")
R.add("Staff loan below scheme rate", "Credit Sanction", L[(L.Scheme == "Staff") & (L.Interest_Rate < 7)], "Medium", "Concession beyond scheme")

# KYC / AML
R.add("Periodic re-KYC overdue", "KYC", K[K.ReKYC_Due_Date < FY_END].sort_values("Risk_Category"), "Medium", "Re-KYC due date passed")
mob = K[K.groupby("Mobile").Customer_ID.transform("count") >= 3].sort_values("Mobile")
R.add("Same mobile across unrelated customers", "AML", mob, note="One mobile, 3+ customers (mule/benami)")
kp = K[K.PAN.notna() & (K.PAN != "")]
R.add("Duplicate PAN, different CIF", "KYC", kp[kp.PAN.duplicated(keep=False)].sort_values("PAN"), note="Exposure splitting")

# Dormant accounts
t = D["Deposit_Txns"].merge(D["Deposit_Accounts"][["Account_No", "Status_1Apr25"]])
R.add("Large withdrawal from inoperative account", "Deposits", t[(t.Status_1Apr25 == "Inoperative") | (t.Entered_By == t.Authorised_By)],
      note="Txn in inoperative a/c or maker = checker")

R.sheet("NPA_by_Branch", L.pivot_table(index="Branch", columns="Asset_Class_Computed", values="Outstanding_31Mar26", aggfunc="sum", fill_value=0).reset_index())
R.save("CoopBank_IA_Exceptions.xlsx")
