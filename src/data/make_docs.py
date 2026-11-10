"""Builds the long-form test inputs: five synthetic PDFs (rendered from HTML with headless Chrome so
Indic scripts shape correctly) and four long call transcripts, then registers nine prompt entries in
prompts.json that point at them via `source_file`. All names, numbers and accounts are made up.
Run once:  python data/make_docs.py      (re-running overwrites the same files and entries)."""
import json, os, random, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS, CALLS = os.path.join(HERE, "docs"), os.path.join(HERE, "calls")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CSS = """<style>body{font-family:Helvetica,'Devanagari MT','Kohinoor Devanagari',sans-serif;font-size:11px;margin:36px}
table{border-collapse:collapse;width:100%}th,td{border:1px solid #444;padding:3px 5px;text-align:left}
th{background:#eee}.r{text-align:right}h1,h2{margin:4px 0}.small{font-size:9px;color:#333}.pb{page-break-before:always}</style>"""


def inr(x):
    s = f"{x:,.2f}"
    # Indian grouping (12,34,567.00)
    whole, dec = s.split(".")
    whole = whole.replace(",", "")
    if len(whole) > 3:
        whole = whole[:-3][::-1]
        whole = ",".join(whole[i:i + 2] for i in range(0, len(whole), 2))[::-1] + "," + s.split(".")[0].replace(",", "")[-3:]
    return f"{whole}.{dec}"


def pdf(name, html):
    src = os.path.join(DOCS, name + ".html")
    out = os.path.join(DOCS, name + ".pdf")
    with open(src, "w", encoding="utf-8") as f:
        f.write("<html><head><meta charset='utf-8'>" + CSS + "</head><body>" + html + "</body></html>")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={out}", src], check=True, capture_output=True)
    os.remove(src)
    return out


entries = []

# ---------------------------------------------------------------- 1. GST invoice, 2 pages, mixed rates, one arithmetic error
items = [("Cotton yarn 40s combed", "5205", 120, "kg", 285.00, 5), ("Polyester blended yarn 30s", "5509", 80, "kg", 198.00, 5),
         ("Reactive dye - Navy RX", "3204", 25, "kg", 640.00, 18), ("Soda ash (sodium carbonate)", "2836", 200, "kg", 38.00, 18),
         ("Industrial sewing thread 40/2", "5401", 300, "cone", 42.00, 12), ("Fusible interlining 90 cm", "5903", 450, "m", 36.50, 18),
         ("Nylon zipper 18 cm", "9607", 2000, "pc", 6.20, 18), ("Plastic buttons 18L", "9606", 10000, "pc", 0.85, 18),
         ("Woven care labels", "5807", 5000, "pc", 1.40, 18), ("Corrugated cartons 24x18x12", "4819", 400, "pc", 48.00, 18),
         ("Machine oil ISO VG 22, 20 L", "2710", 6, "can", 1850.00, 18), ("Needles DBx1 #14 (10/pack)", "8452", 50, "pack", 165.00, 18)]
rows, sub, tax = [], 0.0, {5: 0.0, 12: 0.0, 18: 0.0}
for i, (d, hsn, q, u, r, g) in enumerate(items, 1):
    t = q * r
    if i == 10:
        t = 19600.00  # deliberate error: 400 x 48 = 19,200 but the line prints 19,600 (totals follow the printed line)
    sub += t
    tax[g] += t
    rows.append(f"<tr><td>{i}</td><td>{d}</td><td>{hsn}</td><td class=r>{q}</td><td>{u}</td><td class=r>{inr(r)}</td><td class=r>{g}%</td><td class=r>{inr(t)}</td></tr>")
disc = round(sub * 0.02, 2)
freight = 2400.00
taxable = {g: round(v - v * 0.02, 2) for g, v in tax.items()}
taxable[18] = round(taxable[18] + freight, 2)
cg = {g: round(v * g / 200, 2) for g, v in taxable.items()}
tot_taxable = round(sum(taxable.values()), 2)
tot_cg = round(sum(cg.values()), 2)
grand_raw = tot_taxable + 2 * tot_cg
grand = round(grand_raw)
roundoff = round(grand - grand_raw, 2)
inv_html = f"""<h1>TAX INVOICE</h1><div class=small>Original for recipient · Invoice under Section 31 of CGST Act 2017</div>
<table><tr><td><b>Sharma Industrial Supplies Pvt Ltd</b><br>Plot 41, MIDC Bhosari, Pune 411026, Maharashtra<br>GSTIN: 27AAECS4471K1ZP · PAN: AAECS4471K<br>State code: 27</td>
<td><b>Invoice No:</b> SIS/2026-27/01187<br><b>Invoice date:</b> 27-Sep-2026<br><b>Due date:</b> 27-Oct-2026 (Net 30)<br><b>PO ref:</b> VT-PO-5520 dated 19-Sep-2026<br><b>Transport:</b> Bluedart Surface, LR 884120933</td></tr>
<tr><td><b>Bill to:</b> Ventura Textiles Ltd<br>Gat 212, Kurkumbh Industrial Area, Daund, Pune 413802<br>GSTIN: 27AABCV2290M1Z4 · State code: 27</td>
<td><b>Ship to:</b> Ventura Textiles Ltd, Unit 2<br>Plot 9, Ranjangaon MIDC, Pune 412220<br>Place of supply: Maharashtra (27)</td></tr></table><br>
<table><tr><th>#</th><th>Description</th><th>HSN</th><th>Qty</th><th>Unit</th><th>Rate (₹)</th><th>GST</th><th>Amount (₹)</th></tr>{''.join(rows[:7])}</table>
<div class=small>Page 1 of 2 · continued</div>
<div class=pb></div><h2>TAX INVOICE SIS/2026-27/01187 (contd.)</h2>
<table><tr><th>#</th><th>Description</th><th>HSN</th><th>Qty</th><th>Unit</th><th>Rate (₹)</th><th>GST</th><th>Amount (₹)</th></tr>{''.join(rows[7:])}
<tr><td colspan=7 class=r>Sub-total</td><td class=r>{inr(sub)}</td></tr>
<tr><td colspan=7 class=r>Less: trade discount 2%</td><td class=r>-{inr(disc)}</td></tr>
<tr><td colspan=7 class=r>Add: freight & packing (taxable @18%)</td><td class=r>{inr(freight)}</td></tr></table><br>
<b>Tax summary</b><table><tr><th>GST rate</th><th>Taxable value (₹)</th><th>CGST (₹)</th><th>SGST (₹)</th></tr>
{''.join(f'<tr><td>{g}%</td><td class=r>{inr(taxable[g])}</td><td class=r>{inr(cg[g])}</td><td class=r>{inr(cg[g])}</td></tr>' for g in (5,12,18))}
<tr><th>Total</th><th class=r>{inr(tot_taxable)}</th><th class=r>{inr(tot_cg)}</th><th class=r>{inr(tot_cg)}</th></tr></table><br>
<table><tr><td class=r>Round off</td><td class=r>{roundoff:+.2f}</td></tr><tr><td class=r><b>Grand total</b></td><td class=r><b>₹ {inr(grand)}</b></td></tr></table>
<p>Amount in words: Rupees {grand:,} only.</p>
<p class=small>Bank: Kotak Mahindra Bank, A/c 4412009876, IFSC KKBK0001758. Interest @18% p.a. on overdue invoices. Goods once sold will not be taken back. Subject to Pune jurisdiction. E&OE.</p>
<p>For Sharma Industrial Supplies Pvt Ltd<br><br>Authorised signatory</p>"""
pdf("invoice_sis_01187", inv_html)
entries.append({"id": "de_09", "domain": "document_extraction", "priority": "accuracy", "hidden_difficulty": "hard",
    "prompt": "Below is the text of a 2-page GST tax invoice. Return JSON with: invoice_number, invoice_date, seller_gstin, buyer_gstin, total_taxable_value, total_cgst, total_sgst, grand_total, and line_items (array of {sno, description, hsn, qty, rate, gst_rate, amount}). Then add a field arithmetic_issues listing any line where qty x rate does not equal the printed amount (say which line and the correct amount), or an empty list if all lines are consistent.",
    "source_file": "docs/invoice_sis_01187.pdf",
    "reference_or_rubric": f"invoice_number SIS/2026-27/01187; invoice_date 27-Sep-2026; seller_gstin 27AAECS4471K1ZP; buyer_gstin 27AABCV2290M1Z4; total_taxable_value {tot_taxable}; total_cgst {tot_cg}; total_sgst {tot_cg}; grand_total {grand}. Twelve line items with correct HSN codes and GST rates (5%, 5%, 18%, 18%, 12%, 18%, 18%, 18%, 18%, 18%, 18%, 18%). arithmetic_issues MUST flag line 10 (corrugated cartons): 400 x 48 = 19200 but printed 19600. Full marks need all header totals right, 12 items, and the line-10 flag. Missing the flag caps the score at 6."})

# ---------------------------------------------------------------- 2. Bank statement, ~45 transactions
random.seed(7)
narr_d = ["UPI/DR/Swiggy/{n}", "UPI/DR/Zepto/{n}", "ATM WDL/Koramangala/{n}", "NEFT/DR/ICICI HOME LOAN EMI/{n}", "POS/Reliance Smart/{n}",
          "UPI/DR/Uber India/{n}", "ACH/DR/Bajaj Finserv EMI/{n}", "NEFT/DR/Pinnacle Property Mgmt RENT/{n}", "IMPS/DR/Rohit Sharma/{n}",
          "POS/Amazon Pay/{n}", "UPI/DR/Apollo Pharmacy/{n}", "NEFT/DR/LIC PREMIUM/{n}", "BIL/BPAY/BESCOM/{n}", "UPI/DR/Airtel/{n}",
          "NEFT/DR/Trident Furniture/{n}", "POS/Croma Indiranagar/{n}", "IMPS/DR/Meera Nair/{n}", "UPI/DR/IRCTC/{n}", "SI/DR/Mutual Fund SIP Axis/{n}"]
narr_c = ["NEFT/CR/TECHNOVA SYSTEMS PVT LTD SALARY/{n}", "UPI/CR/Ankit Verma/{n}", "IMPS/CR/Freelance Upwork/{n}", "INT.PD:01-09-2026 TO 30-09-2026", "UPI/CR/Refund Amazon/{n}"]
bal = 184320.55
txns, day = [], 1
big_debits, big_total = [], 0.0
for i in range(46):
    day = min(30, day + random.choice([0, 0, 1, 1, 1, 2]))
    if i in (0, 24):
        amt, n = 142500.00, narr_c[0].format(n=random.randint(10**9, 10**10))
        cr = True
    elif random.random() < 0.18:
        amt, n = round(random.choice([2500, 4999, 1200, 850, 18000]) + random.random() * 100, 2), random.choice(narr_c[1:]).format(n=random.randint(10**9, 10**10))
        cr = True
    else:
        n = random.choice(narr_d).format(n=random.randint(10**9, 10**10))
        amt = round({"EMI": random.choice([27850.00, 14230.00]), "RENT": 32000.00, "SIP": 15000.00, "LIC": 11240.00, "Trident": 46800.00,
                     "Croma": 23499.00, "ATM": random.choice([5000, 10000, 20000])}.get(next((k for k in ("EMI", "RENT", "SIP", "LIC", "Trident", "Croma", "ATM") if k in n), ""), random.random() * 3000 + 120), 2)
        cr = False
    bal = round(bal + amt if cr else bal - amt, 2)
    date = f"{day:02d}-09-2026"
    txns.append((date, n, "" if cr else inr(amt), inr(amt) if cr else "", inr(bal)))
    if not cr and amt > 10000:
        big_debits.append((date, n, amt)); big_total += amt
closing = bal
stmt_rows = "".join(f"<tr><td>{d}</td><td>{n}</td><td class=r>{dr}</td><td class=r>{cr}</td><td class=r>{b}</td></tr>" for d, n, dr, cr, b in txns)
stmt_html = f"""<h1>Vikram Bank Ltd</h1><div class=small>Indiranagar Branch, 100 Ft Road, Bengaluru 560038 · IFSC VKBK0000412</div>
<h2>Statement of Account</h2><table><tr><td><b>Account holder:</b> MR ADITYA RAMACHANDRAN<br><b>Address:</b> 14, 3rd Cross, Domlur Layout, Bengaluru 560071<br><b>Customer ID:</b> 88214907</td>
<td><b>Account no:</b> 41200100238876<br><b>Type:</b> Savings · <b>Currency:</b> INR<br><b>Period:</b> 01-09-2026 to 30-09-2026<br><b>Opening balance:</b> {inr(184320.55)}</td></tr></table><br>
<table><tr><th>Date</th><th>Narration</th><th>Withdrawal (₹)</th><th>Deposit (₹)</th><th>Balance (₹)</th></tr>{stmt_rows}</table>
<p><b>Closing balance as on 30-09-2026: ₹ {inr(closing)}</b></p>
<p class=small>This is a computer generated statement and does not require a signature. Please report discrepancies within 30 days.</p>"""
pdf("bank_statement_sep2026", stmt_html)
bd = "; ".join(f"{d} {n.split('/')[2] if '/' in n else n} {amt:,.2f}" for d, n, amt in big_debits)
entries.append({"id": "de_10", "domain": "document_extraction", "priority": "accuracy", "hidden_difficulty": "hard",
    "prompt": "Below is a one-month bank statement. (1) List every withdrawal strictly greater than ₹10,000 with its date, narration and amount. (2) Give the sum of those withdrawals. (3) State the opening and closing balance. (4) How many salary credits are there and what is the total credited as salary? Answer as JSON.",
    "source_file": "docs/bank_statement_sep2026.pdf",
    "reference_or_rubric": f"Withdrawals > 10,000 ({len(big_debits)} of them): {bd}. Sum = {big_total:,.2f}. Opening 1,84,320.55; closing {inr(closing)}. Salary credits: 2 (TECHNOVA SYSTEMS), total 2,85,000.00. Full marks need the exact count, every item, the correct sum (±1 rupee) and both balances. Wrong count or sum caps at 5."})

# ---------------------------------------------------------------- 3. Bilingual motor policy schedule
pol_html = """<h1>भारत सुरक्षा जनरल इंश्योरेंस कंपनी लिमिटेड / Bharat Suraksha General Insurance Co. Ltd</h1>
<div class=small>IRDAI Reg. No. 158 · पंजीकृत कार्यालय: 7वीं मंज़िल, नरीमन पॉइंट, मुंबई 400021</div>
<h2>निजी कार पैकेज पॉलिसी - अनुसूची / Private Car Package Policy - Schedule</h2>
<table><tr><th>पॉलिसी संख्या / Policy No.</th><td>BSG/MTR/2026/0088213</td><th>पूर्व पॉलिसी / Previous policy</th><td>BSG/MTR/2025/0071904</td></tr>
<tr><th>बीमाधारक का नाम / Name of insured</th><td>श्रीमती प्रियंका कुलकर्णी / Mrs Priyanka Kulkarni</td><th>मोबाइल / Mobile</th><td>98XXXXXX41</td></tr>
<tr><th>पता / Address</th><td colspan=3>फ्लैट 302, सह्याद्री रेसिडेंसी, कोथरुड, पुणे 411038, महाराष्ट्र</td></tr>
<tr><th>बीमा अवधि / Period of insurance</th><td colspan=3>From 00:00 hrs on 14-Oct-2026 to midnight of 13-Oct-2027 (Own damage); Third party: 14-Oct-2026 to 13-Oct-2027</td></tr></table><br>
<h2>वाहन विवरण / Vehicle details</h2>
<table><tr><th>पंजीकरण संख्या / Registration No.</th><td>MH 12 RT 4471</td><th>पंजीकरण तिथि / Date of registration</th><td>22-Mar-2022</td></tr>
<tr><th>निर्माता एवं मॉडल / Make & model</th><td>Hyundai Creta SX 1.5 Diesel</td><th>ईंधन / Fuel</th><td>Diesel</td></tr>
<tr><th>इंजन संख्या / Engine No.</th><td>D4FAMN821734</td><th>चेसिस संख्या / Chassis No.</th><td>MALC381CLNM409112</td></tr>
<tr><th>घन क्षमता / Cubic capacity</th><td>1493 cc</td><th>बैठने की क्षमता / Seating capacity</th><td>5</td></tr>
<tr><th>बीमित घोषित मूल्य / Insured Declared Value (IDV)</th><td colspan=3><b>₹ 9,85,000</b> (vehicle ₹ 9,40,000 + non-electrical accessories ₹ 25,000 + CNG/LPG kit नहीं / nil + electrical accessories ₹ 20,000)</td></tr></table><br>
<h2>प्रीमियम विवरण / Premium computation</h2>
<table><tr><th>विवरण / Particulars</th><th class=r>राशि / Amount (₹)</th></tr>
<tr><td>स्वयं क्षति मूल प्रीमियम / Basic own damage premium</td><td class=r>21,670</td></tr>
<tr><td>घटाएँ: नो क्लेम बोनस 35% / Less: No Claim Bonus 35%</td><td class=r>-7,585</td></tr>
<tr><td>जोड़ें: शून्य मूल्यह्रास कवर / Add: Zero depreciation cover</td><td class=r>4,120</td></tr>
<tr><td>जोड़ें: इंजन सुरक्षा / Add: Engine protect</td><td class=r>1,350</td></tr>
<tr><td>जोड़ें: सड़क किनारे सहायता / Add: Roadside assistance</td><td class=r>299</td></tr>
<tr><td><b>कुल स्वयं क्षति प्रीमियम / Total own damage premium (A)</b></td><td class=r><b>19,854</b></td></tr>
<tr><td>तृतीय पक्ष दायित्व प्रीमियम / Third party liability premium</td><td class=r>3,416</td></tr>
<tr><td>चालक का व्यक्तिगत दुर्घटना कवर / PA cover for owner-driver (₹15 lakh)</td><td class=r>375</td></tr>
<tr><td><b>कुल दायित्व प्रीमियम / Total liability premium (B)</b></td><td class=r><b>3,791</b></td></tr>
<tr><td>शुद्ध प्रीमियम / Net premium (A+B)</td><td class=r>23,645</td></tr>
<tr><td>जीएसटी 18% / GST @18%</td><td class=r>4,256</td></tr>
<tr><td><b>कुल देय प्रीमियम / Total premium payable</b></td><td class=r><b>27,901</b></td></tr></table><br>
<table><tr><th>अनिवार्य कटौती / Compulsory deductible</th><td>₹ 1,000</td><th>स्वैच्छिक कटौती / Voluntary deductible</th><td>शून्य / Nil</td></tr>
<tr><th>नामांकित व्यक्ति / Nominee</th><td>श्री रोहन कुलकर्णी (पति / Husband), आयु 39</td><th>हाइपोथिकेशन / Hypothecated to</th><td>HDFC Bank Ltd, Kothrud branch</td></tr>
<tr><th>ग्राहक भुगतान / Payment</th><td colspan=3>UPI ref 627714099812 dated 09-Oct-2026 · रसीद संख्या / Receipt No. R-2026-55120</td></tr></table>
<p class=small>यह अनुसूची पॉलिसी शब्दावली के साथ पढ़ी जाए। This schedule is to be read with the policy wording. Claims helpline 1800-209-7788. शिकायत के लिए grievance@bharatsuraksha.example पर लिखें।</p>"""
pdf("motor_policy_schedule_bsg", pol_html)
entries.append({"id": "de_11", "domain": "document_extraction", "priority": "accuracy", "hidden_difficulty": "medium",
    "prompt": "Below is a bilingual (Hindi/English) motor insurance policy schedule. Extract as JSON: policy_number, insured_name, registration_number, make_model, idv, period_from, period_to, ncb_percent, total_od_premium, total_liability_premium, gst, total_premium_payable, nominee_name, nominee_relation, hypothecated_to. Use English values.",
    "source_file": "docs/motor_policy_schedule_bsg.pdf",
    "reference_or_rubric": "policy_number BSG/MTR/2026/0088213; insured_name Priyanka Kulkarni; registration_number MH 12 RT 4471; make_model Hyundai Creta SX 1.5 Diesel; idv 985000; period_from 14-Oct-2026; period_to 13-Oct-2027; ncb_percent 35; total_od_premium 19854; total_liability_premium 3791; gst 4256; total_premium_payable 27901; nominee_name Rohan Kulkarni; nominee_relation husband; hypothecated_to HDFC Bank (Kothrud). All 15 fields right = 10; each wrong/missing field -1; IDV must be the total 9,85,000 not the vehicle-only 9,40,000."})

# ---------------------------------------------------------------- 4. Loan sanction letter with penalty clauses
loan_html = """<h1>Meridian Housing Finance Ltd</h1><div class=small>CIN U65922MH2009PLC191210 · Regd office: Tower B, Peninsula Corporate Park, Lower Parel, Mumbai 400013</div>
<p>Ref: MHFL/HL/PUN/2026/44817 · Date: 01-Oct-2026</p>
<p>To,<br>Mr Suresh Babu Nallamothu and Mrs Lakshmi Nallamothu (co-applicant)<br>Flat 7B, Prestige Lakeside, Hinjewadi Phase 2, Pune 411057</p>
<h2>Subject: Sanction of Home Loan - Application No. HL-PUN-220944</h2>
<p>Dear Sir / Madam,<br>With reference to your application, we are pleased to sanction a home loan on the following terms and conditions. This sanction is valid for 90 days from the date of this letter.</p>
<table><tr><th>Loan amount sanctioned</th><td>₹ 68,50,000 (Rupees sixty-eight lakh fifty thousand only)</td></tr>
<tr><th>Purpose</th><td>Purchase of ready-to-move residential flat No. 1104, Tower 3, Kolte Aurora, Wakad, Pune, from M/s Kolte Developers LLP</td></tr>
<tr><th>Rate of interest</th><td>8.65% p.a. floating, linked to MHFL Prime Lending Rate (currently 16.40%) minus spread of 7.75%. Rate is reset on the first working day of each calendar quarter.</td></tr>
<tr><th>Tenure</th><td>240 months</td></tr>
<tr><th>EMI</th><td>₹ 60,062 per month, payable on the 5th of every month by NACH mandate from Vikram Bank A/c ending 8876</td></tr>
<tr><th>Processing fee</th><td>0.50% of loan amount plus GST, i.e. ₹ 34,250 + ₹ 6,165 GST = ₹ 40,415, non-refundable, deducted from first disbursement</td></tr>
<tr><th>Loan-to-value</th><td>Agreement value ₹ 86,00,000; LTV 79.65%</td></tr>
<tr><th>Security</th><td>Equitable mortgage of the flat; original sale deed, share certificate and NOC from the society to be deposited</td></tr>
<tr><th>Insurance</th><td>Property insurance and a loan-linked term cover (premium ₹ 1,12,400, single, may be funded into the loan) are mandatory before disbursement</td></tr></table>
<h2>Other terms and conditions</h2>
<ol>
<li><b>Pre-payment:</b> Nil pre-payment charges for individual borrowers on floating rate, provided the funds are from own sources. If the loan is refinanced by another lender (balance transfer), a charge of 2% of the outstanding principal plus GST applies.</li>
<li><b>Delayed payment:</b> Overdue EMI attracts penal interest of 24% p.a. on the overdue amount from the due date till realisation, plus bounce charges of ₹ 590 per failed NACH presentation.</li>
<li><b>Conversion fee:</b> The borrower may request switching to the prevailing lower spread on payment of 0.25% of outstanding principal plus GST (minimum ₹ 5,000).</li>
<li><b>Disbursement:</b> In a single tranche directly to the seller on execution and registration of the sale deed and creation of mortgage. Pre-EMI interest applies for the broken period from disbursement to the first EMI date.</li>
<li><b>Cross default:</b> Any default by the borrower on any other facility with MHFL or its group companies shall be treated as a default under this loan and entitles MHFL to recall the entire outstanding.</li>
<li><b>Recall:</b> MHFL may recall the loan on 15 days' notice if the borrower's net monthly income falls below ₹ 1,50,000, if the property is let out without written consent, or if any information in the application is found false.</li>
<li><b>Valuation and legal:</b> Fees of ₹ 3,500 (valuation) and ₹ 4,500 (legal) are payable by the borrower irrespective of whether the loan is availed.</li>
<li><b>Tenure extension:</b> If the floating rate increases, MHFL will first extend the tenure up to a maximum of 300 months before increasing the EMI, unless the borrower opts otherwise in writing.</li>
<li><b>Statement:</b> One annual statement is free; additional statements or interest certificates cost ₹ 250 each. Document retrieval after closure costs ₹ 1,000.</li>
<li>This sanction may be withdrawn at MHFL's sole discretion at any time before disbursement without assigning reasons.</li>
</ol>
<p>Please sign and return the duplicate copy of this letter as a token of acceptance within 15 days.</p>
<p>Yours faithfully,<br>For Meridian Housing Finance Ltd<br><br>Kavita Deshpande<br>Branch Credit Manager, Pune Hinjewadi</p>
<p class=small>Accepted the above terms: ______________________ (Borrower) ______________________ (Co-applicant) Date: __________</p>"""
pdf("loan_sanction_letter_mhfl", loan_html)
entries.append({"id": "de_12", "domain": "document_extraction", "priority": "accuracy", "hidden_difficulty": "hard",
    "prompt": "Below is a home loan sanction letter. First, give a table of the key commercial terms (loan amount, interest rate and how it resets, tenure, EMI, processing fee incl. GST, LTV, mandatory insurance premium). Second, list every clause that imposes a charge, penalty or risk on the borrower, each in one line, and say which THREE a borrower should negotiate first and why. Third, state the total up-front cash the borrower must pay before or at disbursement, showing your working.",
    "source_file": "docs/loan_sanction_letter_mhfl.pdf",
    "reference_or_rubric": "Key terms: 68,50,000; 8.65% floating = PLR 16.40% minus 7.75% spread, quarterly reset; 240 months; EMI 60,062; processing fee 40,415 (34,250 + 6,165 GST); LTV 79.65%; term cover premium 1,12,400. Borrower-adverse clauses that must appear: 2% balance-transfer charge; 24% penal interest + 590 bounce charge; 0.25% conversion fee (min 5,000); cross-default to group companies; recall on income < 1,50,000 / letting out / false info; valuation 3,500 + legal 4,500 payable even if not availed; tenure auto-extends to 300 months on rate rise; statement/retrieval charges; sanction withdrawable at discretion. Up-front cash: processing fee 40,415 + valuation 3,500 + legal 4,500 = 48,415 (plus 1,12,400 insurance if not funded into the loan, i.e. 1,60,815 if paid upfront); accept either figure if the assumption is stated. Negotiation picks must be reasoned. Missing cross-default or the recall clause caps at 6."})

# ---------------------------------------------------------------- 5. Hindi complaint letter (Devanagari)
comp_html = """<p style="text-align:right">दिनांक: 06 अक्टूबर 2026</p>
<p>सेवा में,<br>शाखा प्रबंधक,<br>विक्रम बैंक लिमिटेड, कोथरुड शाखा,<br>पुणे 411038</p>
<p><b>विषय: खाता संख्या 41200100556712 से बिना अनुमति ₹24,990 की कटौती एवं धनवापसी हेतु अनुरोध</b></p>
<p>महोदय,</p>
<p>मैं, सुनीता रमेश जाधव, आपके बैंक की कोथरुड शाखा में पिछले ग्यारह वर्षों से बचत खाता (खाता संख्या 41200100556712, ग्राहक आईडी 77310562) धारण करती हूँ। मैं यह पत्र एक गंभीर समस्या की ओर आपका ध्यान आकर्षित करने के लिए लिख रही हूँ।</p>
<p>दिनांक 28 सितंबर 2026 को रात्रि लगभग 11:40 बजे मेरे पंजीकृत मोबाइल नंबर पर एक संदेश आया कि मेरे खाते से ₹24,990 की राशि "POS/FLIPKART INTERNET/0928" के नाम से डेबिट हुई है। मैंने उस समय कोई खरीदारी नहीं की थी और न ही मेरा डेबिट कार्ड (अंतिम चार अंक 3391) किसी और के पास था। मैंने तुरंत ग्राहक सेवा नंबर 1800-209-4455 पर फ़ोन करके कार्ड ब्लॉक करवाया, जिसकी शिकायत संख्या CC2026092811207 है।</p>
<p>इसके बाद 29 सितंबर को मैंने शाखा में आकर लिखित विवाद प्रपत्र (dispute form) भी जमा किया, जिसकी पावती मेरे पास है। आज आठ दिन बीत जाने के बाद भी न तो राशि वापस हुई है और न ही कोई लिखित उत्तर मिला है। 3 अक्टूबर को जब मैंने फ़ोन किया तो मुझे बताया गया कि "जाँच चल रही है" और 90 दिन तक लग सकते हैं।</p>
<p>मैं आपका ध्यान भारतीय रिज़र्व बैंक के दिनांक 6 जुलाई 2017 के परिपत्र की ओर दिलाना चाहती हूँ, जिसके अनुसार यदि ग्राहक अनधिकृत लेन-देन की सूचना तीन कार्य दिवसों के भीतर दे देता है तो ग्राहक की देयता शून्य होती है और बैंक को दस कार्य दिवसों के भीतर राशि ग्राहक के खाते में वापस (shadow credit) करनी होती है। मैंने एक घंटे के भीतर सूचना दी थी।</p>
<p>अतः आपसे अनुरोध है कि:</p>
<ol><li>₹24,990 की पूरी राशि तुरंत मेरे खाते में वापस की जाए;</li>
<li>28 सितंबर से धनवापसी की तिथि तक बचत खाते की दर से ब्याज दिया जाए;</li>
<li>विवाद की स्थिति की लिखित जानकारी मुझे ईमेल sunita.jadhav.example@gmail.com पर दी जाए।</li></ol>
<p>यदि सात दिनों के भीतर समाधान नहीं होता है तो मैं बैंकिंग लोकपाल (Banking Ombudsman) के समक्ष शिकायत दर्ज करने के लिए बाध्य होऊँगी।</p>
<p>संलग्न: डेबिट एसएमएस की प्रति, कार्ड ब्लॉक करने की शिकायत संख्या, विवाद प्रपत्र की पावती।</p>
<p>भवदीया,<br><br>सुनीता रमेश जाधव<br>मोबाइल: 98XXXXXX27<br>पता: 12, गणेश नगर, कोथरुड, पुणे 411038</p>"""
pdf("complaint_letter_hindi", comp_html)
entries.append({"id": "de_13", "domain": "document_extraction", "priority": "accuracy", "hidden_difficulty": "medium",
    "prompt": "Below is a customer complaint letter in Hindi. Extract as JSON in English: complainant_name, account_number, customer_id, disputed_amount, transaction_date, merchant_narration, card_last4, phone_complaint_ref, date_dispute_form_submitted, regulation_cited, remedies_requested (list), escalation_threat, deadline_given_days.",
    "source_file": "docs/complaint_letter_hindi.pdf",
    "reference_or_rubric": "complainant_name Sunita Ramesh Jadhav; account_number 41200100556712; customer_id 77310562; disputed_amount 24990; transaction_date 28 Sep 2026 (~11:40 pm); merchant_narration POS/FLIPKART INTERNET/0928; card_last4 3391; phone_complaint_ref CC2026092811207; date_dispute_form_submitted 29 Sep 2026; regulation_cited RBI circular of 6 July 2017 on limited liability for unauthorised electronic transactions (zero liability if reported within 3 working days, shadow credit within 10 working days); remedies_requested = full refund of 24,990, savings-rate interest from 28 Sep until refund, written status by email; escalation_threat Banking Ombudsman; deadline_given_days 7. Each wrong or missing field -1."})

# ---------------------------------------------------------------- long call transcripts
calls = {}
calls["call_collections_hinglish.txt"] = """[Call ID 7731-2026-1003 | Duration 09:42 | Auto-transcribed, speaker labels: AGENT / CUST]
AGENT: Hello, good afternoon, main Rakesh bol raha hoon Finova Capital se, kya meri baat Mr Imran Shaikh se ho rahi hai?
CUST: Haan haan bol raha hoon, kaun... Finova? Haan boliye.
AGENT: Sir aapka personal loan account hai hamare saath, account number ending 4482, uska September ka EMI ₹11,350 abhi tak receive nahi hua hai. Due date 5 September thi, aaj 3 October ho gaya. Main bas samajhna chahta tha ki kya problem hai.
CUST: Haan dekho bhai, matlab... mujhe pata hai. Actually mera, umm, mera business hai na garments ka, Dharavi mein, toh is baar payment nahi aaya client se. Do lakh ka payment atka hua hai.
AGENT: Okay sir, samajh sakta hoon. Toh aap approximately kab tak expect kar rahe ho ki payment aa jaayega?
CUST: Woh bol rahe hain 10 tareekh tak, 10 October. Par pichhli baar bhi bola tha 20 September, nahi aaya.
AGENT: Theek hai. Sir, ek cheez batana zaroori hai, abhi aapke account pe late payment charge ₹590 lag chuka hai aur agar 60 days cross ho gaye toh bureau mein report ho jaayega, matlab CIBIL pe asar padega.
CUST: Haan yeh toh... dekho yeh dhamki mat do mujhe, main pehle bhi time pe deta aaya hoon, ek baar bhi miss nahi kiya tha do saal mein.
AGENT: Nahi sir, dhamki nahi hai, main bas information de raha hoon, aapka record actually bahut accha hai, 24 EMI on time. Isliye hi main call kar raha hoon, warna system automatically process karta hai.
CUST: Haan theek hai... toh mujhe kya karna chahiye?
AGENT: Sir, kya aap ek partial amount abhi de sakte hain? Jaise ₹5,000, taaki account mein activity dikhe, aur baaki 10 ke baad?
CUST: Abhi 5,000... hmm, abhi toh mere paas, matlab, dekho 3,000 de sakta hoon aaj, Google Pay se. Baaki jab client ka aayega.
AGENT: 3,000 aaj, theek hai sir. Aur remaining ₹8,350 plus late charge, toh total ₹8,940, woh aap kab tak de denge?
CUST: 12 tareekh. 12 October tak pakka. Agar 10 ko client ka aa gaya toh 10 ko hi kar dunga.
AGENT: Toh main note kar leta hoon, promise to pay: ₹3,000 today 3 October, aur ₹8,940 by 12 October. Sahi hai?
CUST: Haan sahi hai. Par ek baat, yeh jo late charge hai 590, yeh hata sakte ho? Pehli baar hua hai.
AGENT: Sir main request daal deta hoon waiver ke liye, final decision branch manager ka hoga, main aapko 2 din mein batata hoon. Guarantee nahi de sakta par aapka record dekh ke chance accha hai.
CUST: Theek hai. Aur ek cheez, yeh October ka EMI bhi 5 ko aa jaayega na? Woh bhi same time pe?
AGENT: Haan sir, October ka EMI 5 October ko NACH se try hoga. Agar account mein balance nahi hoga toh woh bhi bounce hoga aur ₹590 aur lagega. Toh agar possible ho toh 5 tak minimum 11,350 rakh lijiye account mein, ya phir mujhe bata dijiye toh main NACH presentation hold karwa sakta hoon 12 tak.
CUST: Hold karwa do yaar, 12 tak. Dono ek saath de dunga, September ka aur October ka.
AGENT: Toh 12 October ko total hoga ₹8,940 plus ₹11,350, matlab ₹20,290. Aap sure ho sir? Kyunki agar 12 ko miss hua toh phir main kuch nahi kar paunga.
CUST: Haan... haan sure hoon. Client ka 2 lakh aa raha hai, usme se ho jaayega.
AGENT: Theek hai sir. Ek aur baat, aapne pichhle call mein bola tha ki subah 8 baje se pehle call mat karna, maine note kiya hua hai. Yeh call 2:15 pm pe hai.
CUST: Haan haan, woh theek hai, aaj time theek hai. Subah bachche school jaate hain toh busy hota hoon.
AGENT: Samajh gaya. Toh summary: aaj ₹3,000 Google Pay se, 12 October tak ₹20,290 dono EMI ka, NACH hold 12 tak, late fee waiver request submit. Main aapko SMS bhej deta hoon yeh sab likh ke.
CUST: Haan bhej do. Aur agar waiver nahi hua toh bhi batana.
AGENT: Zaroor sir. Payment link bhi SMS mein hoga, ya aap app se bhi kar sakte hain. Thank you sir, aapka din accha ho.
CUST: Theek hai, bye.
[End of call]"""
entries.append({"id": "cc_09", "domain": "call_centre_summary", "priority": "latency", "hidden_difficulty": "hard",
    "prompt": "Below is the auto-transcript of a loan collections call in Hinglish. Write the call summary in English for the collections CRM with these sections: Issue, Customer's reason, Promise to pay (every amount with its date), Agent commitments, Risks/flags for the supervisor. Be precise with numbers.",
    "source_file": "calls/call_collections_hinglish.txt",
    "reference_or_rubric": "Issue: Sept EMI 11,350 (due 5 Sep) unpaid on PL a/c ending 4482; late charge 590 applied. Reason: garment business, client payment of 2 lakh delayed (promised 10 Oct, already slipped once). PTP: 3,000 today (3 Oct) via Google Pay; 20,290 by 12 Oct = remaining 8,940 (8,350 + 590) + October EMI 11,350. Agent commitments: NACH presentation hold till 12 Oct, late-fee waiver request (manager decides, reply in 2 days, no guarantee), SMS confirmation with payment link. Flags: customer objected to the 'threat' about CIBIL; second slip risk on client payment; no-calls-before-8am preference; 60-day bureau reporting risk. Full marks need both PTP amounts with dates and the 20,290 total; a summary that gives only 8,940 or omits the NACH hold caps at 6."})

calls["call_broadband_english.txt"] = """[Call ID BB-55120-20261002 | Duration 14:08 | Auto-transcribed]
AGENT: Thank you for calling Skyfibre Broadband, this is Deepa, how may I help you today?
CUST: Hi Deepa, yeah, so I've got, like, three different things, I've been putting this off. Account is under Meera Krishnan, the customer ID is... hang on... 20077 3451.
AGENT: Thank you Ms Krishnan, I have your account open. Plan is Fibre 300, 300 Mbps, at 999 per month, address is 8th Main, HSR Layout. Go ahead.
CUST: Okay. First thing. The speed. I'm paying for 300 and I did the test this morning, I'm getting 40, 45 on a good day. On wifi and on cable both. This has been for about two weeks now.
AGENT: I'm sorry to hear that. Let me run a line diagnostic from my side... one moment... Okay, I can see the ONT is showing an optical power of minus 27 dBm, which is below the acceptable range, it should be better than minus 25. That usually means a bent fibre or a dirty connector somewhere between the pole and your house.
CUST: So it's a physical thing, not a plan thing.
AGENT: Correct, it's not a plan issue. I'll need to book a technician. The earliest slot I have is tomorrow, 3rd October, between 10 and 1. Will someone be home?
CUST: Tomorrow 10 to 1... yes, my husband will be there. Can you make it, um, can you note that there's a dog so they should call before coming up?
AGENT: Noted, technician to call before arrival, there is a dog. Ticket number is SF-TK-883120. You'll get an SMS.
CUST: Okay. Second thing, and this one I'm actually annoyed about. September's bill. I was charged twice. 999 on the 2nd September and again 999 on the 4th. Both from my credit card. I only pay once.
AGENT: Let me check the payment ledger... I can see it. There is a payment on 2nd September, reference PG77120, and another on 4th September, PG77905, both 999, both successful. The second one appears to be from the auto-pay mandate, and the first one you made manually through the app.
CUST: Right, because the app showed the bill as due so I paid it, and then the auto-pay went anyway.
AGENT: Yes, that's what happened. The auto-pay runs on the 4th regardless. So you have an excess of 999 sitting as credit on the account right now.
CUST: I don't want credit, I want a refund to my card.
AGENT: I understand. I can raise a refund request. Refund to the original card takes 7 to 10 working days. Alternatively I can adjust it against October's bill which means you pay nothing in October. Which do you prefer?
CUST: Hmm... honestly, the adjustment is fine, that's simpler. But then please make sure the auto-pay doesn't charge me again in October.
AGENT: I'll apply the credit to October and I'll put a note so the auto-pay for October is suppressed since the balance will be zero. The system should do that automatically but I'll add a manual flag as well. Reference for the adjustment is ADJ-2026-10-4471.
CUST: Okay, good. And is there a way to stop this happening, like, should I just cancel auto-pay?
AGENT: If you prefer to pay manually, yes, you can cancel the mandate from the app under Payments, Manage auto-pay. Or keep auto-pay and just don't pay manually. The bill will always show as due until the 4th.
CUST: I'll keep auto-pay then and stop paying manually. Third thing. We're moving. End of this month, 28th or 29th, to Whitefield, it's Prestige Shantiniketan. Can I take the connection with me?
AGENT: Let me check feasibility for Prestige Shantiniketan... Yes, that's a serviceable building, we have fibre there. Shifting is free once a year on your plan, and the usual turnaround is 3 working days after the request. Do you want me to schedule it now?
CUST: Not yet, because the exact date isn't fixed. Can I call later?
AGENT: Yes. Just call us at least 5 days before the move date with the flat number so we can schedule the disconnection and the new installation together. I'll put a note on the account that a shift is expected around 28th October to Prestige Shantiniketan, Whitefield.
CUST: Perfect. Oh, one more, sorry. The router. It's the old one, the white one. Will the new place need a new router?
AGENT: The same router will work. If it's older than 3 years you're eligible for a free upgrade to the dual-band one, let me check... your router was issued in June 2022, so not yet, that would be June next year. If you want it earlier it's 1,500.
CUST: No, I'll wait. Okay I think that's everything.
AGENT: To summarise: technician visit tomorrow 10 to 1 for low optical power, ticket SF-TK-883120, they'll call before coming up. Double payment of 999 adjusted against October's bill, reference ADJ-2026-10-4471, auto-pay suppressed for October. Shift to Whitefield noted, you'll call 5 days before. Anything else?
CUST: No that's it. Thanks Deepa, you've been very helpful.
AGENT: You're welcome, have a good day.
[End of call]"""
entries.append({"id": "cc_10", "domain": "call_centre_summary", "priority": "latency", "hidden_difficulty": "medium",
    "prompt": "Summarise this broadband support call for the CRM. Give: (a) a two-line overview, (b) a table of action items with columns Issue, Action, Owner (agent/customer/technician), Reference or date, (c) anything the customer asked that was deferred.",
    "source_file": "calls/call_broadband_english.txt",
    "reference_or_rubric": "Three issues: (1) slow speed ~40-45 Mbps on a 300 Mbps plan, cause low optical power -27 dBm, technician booked 3 Oct 10-1, ticket SF-TK-883120, must call before arriving (dog); (2) double payment of 999 on 2 Sep (manual, PG77120) and 4 Sep (auto-pay, PG77905), resolved by adjusting the credit against October's bill, ref ADJ-2026-10-4471, October auto-pay suppressed, customer will stop paying manually; (3) relocation to Prestige Shantiniketan, Whitefield around 28-29 Oct, serviceable, free once a year, customer to call 5 days before with flat number. Deferred: shift scheduling; router upgrade not eligible until June 2027 (or 1,500 now). Full marks need all three issues with references and the customer-owned action (call 5 days before). Missing the double-payment resolution or the ticket number caps at 6."})

calls["call_upi_hindi.txt"] = """[कॉल आईडी UPI-20260930-2219 | अवधि 07:55 | स्वचालित प्रतिलेख | एजेंट / ग्राहक]
एजेंट: नमस्ते, पेफ़ास्ट ग्राहक सेवा में आपका स्वागत है, मैं अंजलि बात कर रही हूँ, बताइए मैं आपकी क्या मदद कर सकती हूँ?
ग्राहक: हाँ नमस्ते, देखिए मेरा एक पेमेंट अटक गया है। मैंने कल रात किराने वाले को पैसे भेजे, पैसे मेरे अकाउंट से कट गए लेकिन उसको मिले नहीं।
एजेंट: जी, मैं समझ गई। क्या आप अपना रजिस्टर्ड मोबाइल नंबर बता सकते हैं?
ग्राहक: नौ आठ दो... 98230 44517.
एजेंट: धन्यवाद, श्री विनोद पाटिल, सही है?
ग्राहक: हाँ जी।
एजेंट: ठीक है। मुझे ट्रांज़ैक्शन दिख रहा है, कल 29 सितंबर, रात 9:12 बजे, ₹2,350, जिसे आपने "Patil Kirana Store" को भेजा, UPI रेफ़रेंस नंबर 627 299 114 508। स्टेटस "pending" दिखा रहा है, फेल नहीं हुआ है।
ग्राहक: पेंडिंग मतलब? पैसे तो कट गए, मैसेज आया बैंक का।
एजेंट: जी, बैंक ने आपके खाते से राशि डेबिट कर दी है लेकिन दुकानदार के बैंक से कन्फ़र्मेशन नहीं आया। ऐसे मामलों में NPCI के नियम के अनुसार या तो राशि दुकानदार को पहुँच जाती है या फिर एक कार्यदिवस में... मतलब एक वर्किंग डे में आपके खाते में वापस आ जाती है।
ग्राहक: अरे लेकिन मैंने उसको फिर से 2,350 कैश दे दिए, क्योंकि वो बोल रहा था नहीं आए। अब अगर उसको भी मिल गए तो मेरे दो बार चले गए।
एजेंट: समझ गई। अगर राशि दुकानदार को पहुँच जाती है तो वो आपको लौटा सकते हैं, लेकिन वो हमारे नियंत्रण में नहीं है। लेकिन अगर आज रात 12 बजे तक, यानी 30 सितंबर तक, ट्रांज़ैक्शन सेटल नहीं होता तो यह अपने आप रिवर्स हो जाएगा और राशि आपके खाते में, जो कि सारस्वत बैंक का खाता है, वापस आ जाएगी।
ग्राहक: और अगर नहीं आई तो?
एजेंट: तो आप हमें कल सुबह फिर कॉल करें या ऐप में "Transaction history" में जाकर उस ट्रांज़ैक्शन पर "Raise a dispute" दबाएँ। मैं अभी आपकी तरफ़ से एक शिकायत दर्ज कर रही हूँ, शिकायत संख्या है PF-CMP-20260930-10882। इसको आप कहीं लिख लीजिए।
ग्राहक: एक मिनट... PF-CMP... 20260930... 10882. ठीक है।
एजेंट: और एक बात, आपका ऐप पुराना वर्ज़न दिखा रहा है, 4.2। कृपया प्ले स्टोर से अपडेट कर लीजिए, नए वर्ज़न में ऐसे पेंडिंग ट्रांज़ैक्शन का स्टेटस अपने आप दिखता है।
ग्राहक: हाँ ठीक है, कर लूँगा। एक और बात पूछनी थी, मेरी बेटी का कॉलेज फ़ीस का पेमेंट है 15 तारीख़ को, 48,000 का। इस ऐप से एक दिन में इतना जा सकता है क्या?
एजेंट: जी, आपके बैंक की UPI लिमिट एक लाख प्रतिदिन है, और एक ट्रांज़ैक्शन में भी एक लाख तक। लेकिन शिक्षा संस्थानों के लिए लिमिट पाँच लाख है। तो 48,000 कोई समस्या नहीं होगी। बस कॉलेज का UPI आईडी या QR सही से जाँच लीजिए।
ग्राहक: अच्छा। और यह जो अभी अटका है, इसकी वजह से कोई ब्लॉक तो नहीं लगेगा?
एजेंट: नहीं, कोई ब्लॉक नहीं। यह सिर्फ़ एक पेंडिंग सेटलमेंट है, बाकी सब सामान्य चलेगा।
ग्राहक: ठीक है। तो कल तक इंतज़ार करता हूँ।
एजेंट: जी। संक्षेप में: ₹2,350 का ट्रांज़ैक्शन पेंडिंग है, 30 सितंबर रात तक सेटल या रिवर्स हो जाएगा; शिकायत संख्या PF-CMP-20260930-10882; अगर कल तक राशि वापस न आए तो ऐप से डिस्प्यूट उठाएँ या हमें कॉल करें; ऐप अपडेट कर लें। क्या मैं और कुछ मदद कर सकती हूँ?
ग्राहक: नहीं, बस इतना ही। धन्यवाद।
एजेंट: धन्यवाद विनोद जी, आपका दिन शुभ हो।
[कॉल समाप्त]"""
entries.append({"id": "cc_11", "domain": "call_centre_summary", "priority": "latency", "hidden_difficulty": "medium",
    "prompt": "नीचे एक UPI ग्राहक सेवा कॉल का हिंदी प्रतिलेख है। CRM के लिए हिंदी में सारांश लिखें: (1) समस्या, (2) एजेंट ने क्या बताया और क्या किया, (3) ग्राहक को आगे क्या करना है, (4) ग्राहक का दूसरा प्रश्न और उसका उत्तर। सभी संख्याएँ और रेफ़रेंस नंबर सही लिखें।",
    "source_file": "calls/call_upi_hindi.txt",
    "reference_or_rubric": "Summary must be in Hindi (Devanagari). Problem: ₹2,350 UPI to Patil Kirana Store on 29 Sep 9:12 pm, ref 627299114508, debited but pending; customer already paid cash again. Agent: explained pending vs failed, auto-reversal by end of 30 Sep (one working day) to Saraswat Bank account if unsettled; filed complaint PF-CMP-20260930-10882; advised app update from v4.2. Customer next: wait till tomorrow, then raise dispute in app or call; if merchant receives it, ask merchant to return. Second question: ₹48,000 college fee on the 15th; limit is 1 lakh/day (5 lakh for education), so fine. Full marks need the complaint number, the UPI reference and the 30 Sep deadline. Answer in English caps at 5."})

calls["call_health_claim_hinglish.txt"] = """[Call ID HC-2026-1001-0931 | Duration 12:31 | Auto-transcribed | Note: line noise 00:00-00:40]
AGENT: Good morning, Arogya Shield Health Insurance, Priya speaking, how can I help?
CUST: Haan hello, hello? Awaaz aa rahi hai?
AGENT: Yes sir, I can hear you.
CUST: Haan, dekhiye, mera claim reject ho gaya hai aur mujhe samajh nahi aa raha kyun. Policy number hai... ek second... ASH slash 2024 slash 11 slash 30921.
AGENT: ASH/2024/11/30921, let me pull it up... Sir, is policy pe toh koi claim hi nahi hai. Yeh policy Mr Harish Mehta ke naam pe hai, individual plan, aur last claim 2024 mein tha.
CUST: Mehta? Nahi nahi, main Ganesh Iyer bol raha hoon. Ek minute, galat number pad liya shayad, yeh purana card hai. Haan, yeh wala, ASH slash 2025 slash 11 slash 30291. Two nine one, not nine two one.
AGENT: ASH/2025/11/30291. Okay, yes, Mr Ganesh Iyer, family floater, sum insured 5 lakh, you plus spouse plus one child. Aur claim number hai CLM-2026-09-77410, hospitalisation of Mrs Kavita Iyer at Lakshmi Multispeciality, Chennai, 18 to 21 September, claimed amount ₹1,84,600. Status is "repudiated". Sahi hai?
CUST: Haan wahi. Toh kyun reject hua? Hospital network mein hai, humne pre-auth bhi liya tha.
AGENT: Let me read the repudiation note... Sir, the reason given is "non-disclosure of pre-existing disease". Treatment tha laparoscopic cholecystectomy, gallbladder removal, aur discharge summary mein likha hai "known case of gallstones since 2023".
CUST: Arre lekin policy 2025 mein li thi, aur gallstones ka toh pata hi tab chala jab ultrasound hua is saal August mein. 2023 kisne likha?
AGENT: Sir, that's what the hospital's discharge summary says. Agar woh galat hai toh aapko hospital se ek corrected discharge summary ya treating doctor ka letter chahiye jo clarify kare ki diagnosis kab hua.
CUST: Theek hai, woh main le aata hoon. Doctor Subramanian the, unse baat karunga. Lekin pre-auth approve kaise hua phir?
AGENT: Pre-auth was approved for ₹1,20,000 on 17 September as an initial approval, sir. Final claim mein jab full documents aaye tab medical team ne review kiya. Pre-auth approval is always provisional, yeh policy wording mein hai.
CUST: Toh ab 1,84,600 hum pay kar chuke hain hospital ko, apne pocket se. Yeh paisa kab milega?
AGENT: Sir, abhi toh claim repudiated hai, toh pehle usko reopen karna hoga. Process yeh hai: aap doctor ka letter aur ultrasound report of August 2026 jo dikhaye first diagnosis, woh claims@arogyashield.example pe bhejiye with claim number in subject. Main ek reconsideration request abhi raise kar deti hoon, reference RC-77410-A. Medical team ka reply 15 working days mein aata hai.
CUST: 15 working days... matlab almost teen hafte. Aur agar phir bhi reject hua?
AGENT: Toh aap hamare Grievance Redressal Officer ko likh sakte hain, uska email policy document mein hai, aur uske baad IRDAI ke Bima Bharosa portal ya insurance ombudsman. Lekin pehle doctor ka letter aane dijiye, most cases waheen resolve ho jaate hain.
CUST: Hmm. Aur yeh jo 1,20,000 pre-auth tha aur 1,84,600 bill, difference ka kya? Room ka tha kya?
AGENT: Let me see the bill breakup... Room was a deluxe at 7,500 per day, but your plan allows single private AC room up to 5,000 per day. So agar claim approve bhi hota hai toh proportionate deduction lagega, roughly 33 percent on room-linked charges. Mote taur pe approximately 1,45,000 to 1,50,000 payable hota, not the full 1,84,600. Exact figure claims team dega.
CUST: Yeh toh pehle bataya nahi kisi ne. Hospital ne bola sab covered hai.
AGENT: Sir, I understand the frustration. Hospital network desk ko room category pata hona chahiye tha. Main ek feedback bhi raise kar deti hoon hospital ke against, but the policy terms would still apply.
CUST: Theek hai. Toh mujhe doctor ka letter, August ki ultrasound report, aur... bas?
AGENT: Doctor's letter stating date of first diagnosis, August 2026 ultrasound report, aur agar pehle koi ultrasound ya consultation hai gallbladder ke liye 2025 se pehle toh woh bhi, honestly. Claim number CLM-2026-09-77410 subject mein. Reference RC-77410-A. Aapko ek SMS aur email abhi jaayega.
CUST: Theek hai, email pe bhej dunga is hafte.
AGENT: Thank you sir. Aur ek baat, aapke policy renewal 11 November ko due hai, is claim ke chalte renewal pe koi asar nahi padega, bas premium ₹24,300 hoga. Reminder aa jaayega.
CUST: Okay. Theek hai, thank you.
AGENT: Thank you Mr Iyer, take care.
[End of call]"""
entries.append({"id": "cc_12", "domain": "call_centre_summary", "priority": "latency", "hidden_difficulty": "hard",
    "prompt": "Below is a health insurance claims call in Hinglish. Write the CRM note in English: correct policy and claim identifiers, what was claimed and why it was repudiated, what the customer disputes, what documents the customer must send and where, references raised by the agent, the expected payout if the claim is reinstated and why it is lower than billed, escalation path, and any process gaps to report internally. Use only the corrected identifiers.",
    "source_file": "calls/call_health_claim_hinglish.txt",
    "reference_or_rubric": "Policy ASH/2025/11/30291 (NOT ASH/2024/11/30921, which the customer read wrongly first); claim CLM-2026-09-77410; Mrs Kavita Iyer, Lakshmi Multispeciality Chennai, 18-21 Sep, laparoscopic cholecystectomy, claimed 1,84,600, repudiated for non-disclosure (discharge summary says gallstones known since 2023). Customer says first diagnosis was August 2026 ultrasound. Docs: treating doctor's (Dr Subramanian) letter on date of first diagnosis + August 2026 ultrasound report, email to claims@arogyashield.example with claim number in subject. Reconsideration ref RC-77410-A, 15 working days. Pre-auth 1,20,000 was provisional. If reinstated ~1,45,000-1,50,000 because deluxe room 7,500/day exceeds 5,000/day entitlement (proportionate deduction ~33%). Escalation: GRO, then IRDAI Bima Bharosa / ombudsman. Internal: hospital network desk didn't inform room cap, feedback raised. Renewal 11 Nov, premium 24,300, unaffected. Using the wrong policy number anywhere caps at 4."})

for name, text in calls.items():
    with open(os.path.join(CALLS, name), "w", encoding="utf-8") as f:
        f.write(text)

# ---------------------------------------------------------------- register in prompts.json
pfile = os.path.join(HERE, "prompts.json")
with open(pfile, encoding="utf-8") as f:
    prompts = json.load(f)
prompts = [p for p in prompts if p["id"] not in {e["id"] for e in entries}] + entries
with open(pfile, "w", encoding="utf-8") as f:
    json.dump(prompts, f, ensure_ascii=False, indent=2)
print(f"built {len(os.listdir(DOCS))} pdfs, {len(calls)} transcripts, prompts.json now has {len(prompts)} entries")
print("invoice check:", dict(sub=sub, disc=disc, taxable=taxable, cgst=cg, tot_taxable=tot_taxable, tot_cg=tot_cg, grand=grand))
print("statement check:", len(big_debits), "big debits, sum", round(big_total, 2), "closing", closing)
