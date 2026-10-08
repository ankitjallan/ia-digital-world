"""
Tool 1 - Full-population audit analytics for Brahmaputra Alu Systems Pvt Ltd (aluminium).
Covers O2C, P2P, GST, inventory/yield and journal-entry (audit trail) testing.
Run: python aluminium_audit.py
"""
import numpy as np
import pandas as pd
from common import load, Report, gstin_valid, is_non_working, benford, FY_END

D = load("01_Aluminium")
R = Report("Aluminium - Brahmaputra Alu Systems Pvt Ltd - IA Analytics")
print("\n== Aluminium : 100% population testing ==")

# ---------------- Order to Cash
s = D["Sales_Register"].copy()
s["Base_No"] = s.Invoice_No.str.extract(r"/(\d{4})")[0].astype(int)
full = set(range(s.Base_No.min(), s.Base_No.max() + 1))
R.add("Invoice sequence gap", "Sales", pd.DataFrame({"Missing_Invoice_No": [f"BAS/25-26/{n:04d}" for n in sorted(full - set(s.Base_No))]}),
      note="Breaks in invoice numbering")
k = ["Cust_ID", "Invoice_Date", "Item_Code", "Qty", "Taxable_Value"]
R.add("Duplicate invoice", "Sales", s[s.duplicated(k, keep=False)].sort_values(k), note="Same customer, date, item, qty, value")
R.add("Discount beyond policy (max 5%)", "Sales", s[s.Discount_Pct > 5], note="Trade discount above 5%")
R.add("Sunday invoice", "Sales", s[is_non_working(s.Invoice_Date)], "Medium", "Invoices on Sundays / holidays")
R.add("Revenue cut-off", "Sales", s[(s.Invoice_Date <= FY_END) & (s.Dispatch_Date > FY_END)],
      note="Billed in FY 25-26, dispatched after 31-Mar-26")
R.add("Wrong GST type", "Sales/GST", s[((s.State_Code != 18) & (s.Tax_Type != "IGST")) | ((s.State_Code == 18) & (s.Tax_Type == "IGST"))],
      note="Place of supply vs tax type")

deb = D["Debtors_Ageing"].merge(D["Customer_Master"][["Cust_ID", "Credit_Limit"]])
R.add("Credit limit breach", "Debtors", deb[deb.Outstanding_31Mar26 > deb.Credit_Limit], note="Outstanding > sanctioned limit")
R.add("Old debts without provision", "Debtors", deb[(deb[">365"] > 0) & (deb.Provision_Made == 0)], note=">365 days, no provision")
R.add("Credit balance in debtors", "Debtors", deb[deb.Outstanding_31Mar26 < 0], "Medium", "Negative debtor balances")

# ---------------- Vendor master
v, e = D["Vendor_Master"].copy(), D["Employee_Master"]
dup = pd.concat([v[v.PAN.duplicated(keep=False)], v[v.Bank_Account.duplicated(keep=False)],
                 v[v.GSTIN.notna() & v.GSTIN.duplicated(keep=False)]]).drop_duplicates("Vendor_ID")
R.add("Duplicate vendor", "Vendor Master", dup, note="Same PAN / GSTIN / bank a/c")
emp_link = v.merge(e[["Emp_ID", "Name", "Bank_Account"]], on="Bank_Account")
R.add("Vendor bank = employee bank", "Vendor Master", emp_link, note="Vendor bank a/c matches an employee")
reg = v[v.GSTIN.notna() & (v.GSTIN != "")]
R.add("Invalid GSTIN checksum", "Vendor Master", reg[~reg.GSTIN.map(gstin_valid)], note="GSTIN check digit fails")
pm = v[(v.Vendor_Name.str.contains("Pvt", case=False) & (v.PAN.str[3] != "C"))
       | (reg.GSTIN.str[2:12].reindex(v.index).notna() & (reg.GSTIN.str[2:12].reindex(v.index) != v.PAN))]
R.add("PAN mismatch", "Vendor Master", pm, note="PAN type vs constitution; PAN inside GSTIN")
R.add("Cancelled GSTIN vendor", "Vendor Master", v[~v.GST_Status.isin(["Active", "Unregistered"])], note="GST status not active")

# ---------------- Procure to Pay (3-way match)
pi, po, grn = D["Purchase_Invoices"], D["Purchase_Orders"], D["GRN"]
m = pi.merge(po[["PO_No", "PO_Rate", "PO_Qty"]], on="PO_No", how="left").merge(grn[["GRN_No", "Qty_Received"]], on="GRN_No", how="left")
m["Rate_Diff_%"] = ((m.Rate / m.PO_Rate - 1) * 100).round(2)
R.add("Invoice rate > PO rate", "P2P 3-way match", m[m.Rate > m.PO_Rate * 1.001], note="Billed rate above PO")
R.add("Invoice qty > GRN qty", "P2P 3-way match", m[m.Qty > m.Qty_Received], note="Billed qty above received")
R.add("Invoice without GRN", "P2P 3-way match", m[m.GRN_No.isna() | (m.GRN_No.astype(str).str.strip().isin(["", "nan"]))], note="No goods receipt")
R.add("Duplicate purchase booking", "P2P", pi[pi.duplicated(["Vendor_ID", "Vendor_Invoice_No"], keep=False)].sort_values("Vendor_Invoice_No"),
      note="Same vendor invoice booked twice")
b = D["Billet_Benchmark"]
bil = pi[pi.Category == "Billet"].assign(Month=lambda x: x.Invoice_Date.dt.strftime("%Y-%m")).merge(b, on="Month")
bil["Above_Benchmark_%"] = ((bil.Rate / bil.Billet_Benchmark_Rs_per_Kg - 1) * 100).round(2)
R.add("Price above market benchmark", "P2P Pricing", bil[bil["Above_Benchmark_%"] > 5].sort_values("Above_Benchmark_%", ascending=False),
      note="Billet rate > benchmark + 5%")

# ---------------- GSTR-2B reconciliation
books = pi.drop_duplicates(["Vendor_ID", "Vendor_Invoice_No"]).query("Vendor_GSTIN == Vendor_GSTIN and Vendor_GSTIN != ''")
g = D["GSTR2B"]
rc = books.merge(g, on=["Vendor_GSTIN", "Vendor_Invoice_No"], how="outer", indicator=True)
rc["Diff"] = (rc.ITC_Claimed.fillna(0) - rc.IGST_CGST_SGST_Total.fillna(0)).round(2)
cancelled = v[~v.GST_Status.isin(["Active", "Unregistered"])].Vendor_ID
nb = rc[rc._merge == "left_only"]
R.add("ITC from cancelled GSTIN", "GST Recon", nb[nb.Vendor_ID.isin(cancelled)], note="ITC of vendor with cancelled GSTIN")
R.add("ITC in books not in GSTR-2B", "GST Recon", nb[~nb.Vendor_ID.isin(cancelled)], note="Claimed but not in 2B")
R.add("In 2B, not in books", "GST Recon", rc[rc._merge == "right_only"], "Medium", "Unrecorded purchase")
R.add("Tax amount mismatch", "GST Recon", rc[(rc._merge == "both") & (rc.Diff.abs() > 1)], note="Books ITC vs 2B")
R.sheet("GST_Recon_Full", rc.drop(columns="_merge").assign(Status=rc._merge.map(
    {"both": "Matched", "left_only": "Only in books", "right_only": "Only in 2B"})))

# ---------------- Payments
p = D["Payments"]
day = p.groupby(["Vendor_ID", "Payment_Date"]).agg(n=("Amount", "size"), total=("Amount", "sum"), mx=("Amount", "max")).reset_index()
split = day[(day.n >= 2) & (day.mx <= 200000) & (day.total > 200000)]
R.add("Split payments to avoid approval limit", "Payments", p.merge(split[["Vendor_ID", "Payment_Date"]]),
      note="Multiple <=2L payments same vendor/day totalling >2L")
R.add("Payment to employee-linked vendor / self approval", "Payments",
      p[(p.Prepared_By == p.Approved_By) | p.Vendor_ID.isin(emp_link.Vendor_ID)], note="Maker = checker, or employee-linked vendor")
dupv = dup[dup.duplicated("PAN", keep="first") | dup.duplicated("Bank_Account", keep="first")].Vendor_ID
R.add("Payment to duplicate vendor", "Payments", p[p.Vendor_ID.isin(dupv)], note="Paid to a duplicate vendor code")
pp = p[p.Against_Booking != "On Account"]
R.add("Duplicate payment", "Payments", pp[pp.duplicated("Against_Booking", keep=False)].sort_values("Against_Booking"),
      note="Same booking paid twice")
R.add("Payment on Sunday", "Payments", p[is_non_working(p.Payment_Date)], "Medium", "Bank payments on Sundays / holidays")

# ---------------- Production yield
pr = D["Production_Yield"].copy()
pr["Recovery_%"] = (pr.Good_Output_Kg / pr.Billet_Input_Kg * 100).round(2)
pr["Loss_%"] = (pr.Process_Loss_Kg / pr.Billet_Input_Kg * 100).round(2)
R.add("Abnormal yield loss", "Production", pr[(pr["Recovery_%"] < 82)], note="Recovery below 82% (std 84-88%)")
R.add("Output > input", "Production", pr[pr.Good_Output_Kg > pr.Billet_Input_Kg], note="Impossible yield")
piv = pr.assign(Month=pr.Date.dt.strftime("%Y-%m")).pivot_table(index=["Operator", "Shift"], columns="Month",
                                                                 values="Recovery_%", aggfunc="mean").round(1)
R.sheet("Yield_Heatmap_Operator", piv.reset_index())

# ---------------- Journal entries (audit trail)
j = D["Journal_Entries"].copy()
h = j.Entry_DateTime.dt.hour
R.add("Late-night ADMIN self-approved JE", "Journals", j[((h >= 22) | (h < 6)) | (j.Created_By == j.Approved_By)],
      note="Entered 10pm-6am or maker = checker")
j["Lag_Days"] = (j.Entry_DateTime.dt.normalize() - j.Posting_Date).dt.days
R.add("Back-dated round-sum revenue JE", "Journals", j[(j.Lag_Days > 30) | ((j.Amount % 50000 == 0) & (j.Credit_Account == "Sales - Domestic"))],
      note="Entered >30 days after posting date, or round-sum credits to Sales")
R.add("JE without narration", "Journals", j[j.Narration.isna() | (j.Narration.astype(str).str.strip() == "")], "Medium", "Blank narration")

t, mad, verdict = benford(pd.concat([p.Amount, j.Amount, pi.Invoice_Total]))
R.sheet("Benford_First_Digit", pd.concat([t, pd.DataFrame({"Digit": ["MAD", "Verdict"], "Expected_%": [round(mad, 4), verdict]})]))
print(f"  Benford (payments+JE+purchases): MAD={mad:.4f} -> {verdict}")

R.save("Aluminium_IA_Exceptions.xlsx")
