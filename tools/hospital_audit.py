"""
Tool 3 - Revenue-assurance audit for Lohit Care Multispeciality Hospital.
Discounts, unbilled consumables, TPA / PMJAY receivables, doctor payouts.
Run: python hospital_audit.py
"""
import pandas as pd
from common import load, Report, FY_END

D = load("03_Hospital")
R = Report("Hospital - Lohit Care - Revenue Assurance Analytics")
print("\n== Hospital : revenue leakage ==")
b = D["IPD_Bills"].copy()
b["Disc_%"] = (b.Discount / b.Gross_Bill * 100).round(1)
R.add("Unauthorised high discount", "Billing", b[(b["Disc_%"] > 10) & (b.Discount_Approved_By != "MS_DR_BORA")], note=">10% without MS approval")
R.add("Cash patient discharged with dues", "Billing", b[(b.Payer == "Cash") & (b.Amount_Received < b.Net_Bill)].assign(
    Dues=lambda x: x.Net_Bill - x.Amount_Received), note="Cash bills not fully collected")

c = D["Consumables_Issue"]
ub = c[c.Billed == "N"]
R.add("Revenue leakage - unbilled consumables", "Consumables", ub.sort_values("Value", ascending=False), note="Issued to patient, not billed")
R.sheet("Unbilled_by_Ward", ub.groupby("Ward").agg(Items=("Issue_No", "count"), Value=("Value", "sum")).reset_index().sort_values("Value", ascending=False))
print(f"     -> unbilled consumables Rs {ub.Value.sum():,.0f}")

t = D["TPA_Claims"].copy()
t["Deduction_%"] = ((1 - t.Approved_Amount / t.Claimed_Amount) * 100).round(1)
by = t[t.Status != "Rejected"].groupby("Payer").agg(Claims=("Claim_No", "count"), Avg_Deduction_pct=("Deduction_%", "mean"),
                                                    Claimed=("Claimed_Amount", "sum"), Approved=("Approved_Amount", "sum")).round(1).reset_index()
R.sheet("Deduction_by_Payer", by)
avg = by.Avg_Deduction_pct.median()
R.add("Systematic short settlement", "TPA / PMJAY", t[t.Payer.isin(by[by.Avg_Deduction_pct > 2 * avg + 5].Payer)], note="Payer deducting far above peers")
t = t.merge(b[["Bill_No", "Discharge_Date"]])
t["Days_to_Submit"] = (t.Submission_Date - t.Discharge_Date).dt.days
R.add("Late claim submission", "TPA / PMJAY", t[t.Days_to_Submit > 30], "Medium", "Submitted > 30 days after discharge")
R.add("Claims pending > 180 days", "TPA / PMJAY", t[(t.Status == "Pending") & ((FY_END - t.Submission_Date).dt.days > 180)], note="Aged claim receivables")

p = D["Doctor_Payouts"].merge(D["Doctor_Master"])
p["Should_Pay"] = (p.Net_Revenue_Attributed * p.Revenue_Share_Pct / 100).round(0)
p["Excess"] = p.Paid_Amount - p.Should_Pay
R.add("Doctor overpaid", "Doctor Payouts", p[p.Excess > 100], note="Paid vs agreed revenue share")
print(f"     -> doctor overpayment Rs {p[p.Excess > 100].Excess.sum():,.0f}")
R.save("Hospital_IA_Exceptions.xlsx")
