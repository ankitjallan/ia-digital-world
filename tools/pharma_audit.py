"""
Tool 4 - Distributor audit for Siang Distributors LLP (FMCG & Pharma stockist).
Expiry, Drug Licence compliance, scheme leakage, collections (teeming & lading), credit notes.
Run: python pharma_audit.py
"""
import pandas as pd
from common import load, Report, FY_END

D = load("04_FMCG_Pharma")
R = Report("FMCG-Pharma - Siang Distributors - IA Analytics")
print("\n== FMCG / Pharma distributor ==")
s, st, rt, pr = D["Sales_Invoices"], D["Batch_Stock"], D["Retailer_Master"], D["Product_Master"]

x = s.merge(st[["Batch", "Expiry_Date"]], on="Batch")
R.add("Sale of expired batch", "Sales", x[x.Invoice_Date > x.Expiry_Date], note="Invoice date after batch expiry")
y = s.merge(pr[["SKU", "Schedule"]]).merge(rt[["Retailer_ID", "Type", "DL_Valid_Upto"]])
R.add("Sch H drugs sold to expired Drug Licence", "Regulatory", y[(y.Schedule == "Sch H") & (y.Invoice_Date > y.DL_Valid_Upto)],
      note="D&C Act - DL validity at invoice date")

sch = D["Scheme_Master"]
z = s.merge(sch.rename(columns={"Free_Qty": "Sch_Free"}), on="SKU", how="left")
z = z[(z.Invoice_Date >= z.Valid_From) & (z.Invoice_Date <= z.Valid_To)]
z["Eligible_Free"] = (z.Qty // z.Buy_Qty * z.Sch_Free).astype(int)
R.add("Free goods beyond scheme", "Schemes", z[z.Free_Qty > z.Eligible_Free], note="Free qty > scheme entitlement")
R.add("Free goods not passed to retailer", "Schemes", z[z.Free_Qty < z.Eligible_Free], "Medium", "Retailer short-changed / diverted")
act = s[s.Free_Qty > 0].assign(Month=s.Invoice_Date.dt.strftime("%Y-%m")).groupby(["SKU", "Month"]).Free_Qty.sum().reset_index()
cl = D["Scheme_Claims"].merge(act, on=["SKU", "Month"], how="left").fillna({"Free_Qty": 0})
R.add("Scheme over-claim on principal", "Schemes", cl[cl.Free_Qty_Claimed > cl.Free_Qty * 1.02], note="Claimed > actually passed on")

c = D["Collections"].copy()
c["Deposit_Lag"] = (c.Bank_Deposit_Date - c.Receipt_Date).dt.days
R.add("Delayed cash deposit - teeming & lading", "Collections", c[c.Deposit_Lag > 2].sort_values("Deposit_Lag", ascending=False),
      note="Cash deposited > 2 days after receipt")
R.sheet("Deposit_Lag_by_Salesman", c[c.Mode == "Cash"].groupby("Salesman").Deposit_Lag.agg(["count", "mean", "max"]).round(1).reset_index())
n = c.Receipt_No.str[3:].astype(int)
R.add("Missing receipt number", "Collections", pd.DataFrame({"Missing_Receipt": [f"MR/{k:05d}" for k in sorted(set(range(n.min(), n.max() + 1)) - set(n))]}),
      note="Gaps in money-receipt series")
r = D["Sales_Returns"]
R.add("Credit note without physical return", "Returns", r[r.Godown_GRN_No.isna() | (r.Godown_GRN_No.astype(str).str.strip() == "")], note="CN with no godown GRN")

st = st.assign(Days_to_Expiry=(st.Expiry_Date - FY_END).dt.days)
R.add("Expired stock in saleable inventory", "Inventory", st[(st.Days_to_Expiry < 0) & (st.Closing_Qty > 0)], note="Expired, still valued at PTR")
R.add("Near-expiry stock", "Inventory", st[st.Days_to_Expiry.between(0, 90) & (st.Closing_Qty > 0)], "Medium", "Expiring within 90 days")
R.save("Pharma_IA_Exceptions.xlsx")
