# Capex vs depreciation by year — Meridian Industrial Supply LLC

**Prepared:** deal-side financial due diligence | **Data room cut-off:** 15 Feb 2026

## 1. Short answer

In every year for which the books are closed, **capital expenditure is materially below the depreciation charge**, and the gap widens sharply in FY2025:

| Period | Capex additions (additions to PP&E, a/c 150000) | Depreciation charge (a/c 610000) | Capex ÷ Depreciation | Cumulative gap |
|---|---|---|---|---|
| FY2024 (closed) | **2,400,000** | **2,640,000** | **0.91x** | 240,000 under |
| FY2025 (closed) | **600,000** | **2,760,000** | **0.22x** | 2,160,000 under |
| FY2024 + FY2025 | **3,000,000** | **5,400,000** | **0.56x** | **2,400,000 under** |
| FY2026 YTD (Jan, open) | 0 posted | 0 posted (month-end close not run) | n/a | n/a |

Over the two closed years the business spent $3.0m of capex against $5.4m of depreciation, i.e. it replaced roughly **56 cents of every dollar of depreciation**. Net book value of property and equipment fell from $19.2m (31 Dec 2023) to $18.96m (31 Dec 2024) to **$16.8m (31 Dec 2025)**.

Management's own reported figures agree with the underlying ledger: the FY2024 and FY2025 management accounts show depreciation of $2,640,000 and $2,760,000 respectively, and closing accumulated depreciation of $7,440,000 and $10,200,000 — the same numbers that foot the SAP postings.

## 2. Supporting detail

### 2.1 Balance-sheet roll-forward (as reported)

| | 31 Dec 2023 (opening) | 31 Dec 2024 | 31 Dec 2025 |
|---|---|---|---|
| PP&E at cost | 24,000,000 | 26,400,000 | 27,000,000 |
| Accumulated depreciation | (4,800,000) | (7,440,000) | (10,200,000) |
| **Net book value** | **19,200,000** | **18,960,000** | **16,800,000** |

Sources: `Trial_balance_2024.xlsx` / `Trial_balance_2025.xlsx`, sheet "Trial Balance", accounts 150000 (Property and equipment), 150100 (Accumulated depreciation), 610000 (Depreciation); confirmed by the December balance sheets in `Management_accounts_2024-12.xlsx` and `Management_accounts_2025-12.xlsx` (rows for account ids 150000/150100).

### 2.2 Capex by year (SAP ledger)

Only three postings hit PP&E in the whole extract (`BSEG.csv`, HKONT `0000150000`, all debit/SHKZG = S, cross-checked to `BKPF.csv` for posting date and document text):

| GJAHR | Document | Posting date | Reference | Description | Amount |
|---|---|---|---|---|---|
| 2023 | 0000000039 / 003 | 2023-12-31 | OPENING-BALANCE | Opening balance | 24,000,000 |
| 2024 | 0000000063 / 001 | 2024-01-01 | ASSET-FA-004 | Asset addition (conveyor/scanner replacement) | 2,400,000 |
| 2025 | 0000005174 / 001 | 2025-01-01 | ASSET-FA-005 | Asset addition (safety / fork-truck replacements) | 600,000 |

There are **no PP&E postings at all in GJAHR 2026** (January 2026, the only open month), and no intangible/software asset account exists in the chart of accounts — so the $900,000 ERP implementation was expensed to P&L a/c 609000, not capitalised (see limitation 3.4).

### 2.3 Depreciation by year and asset (SAP ledger)

`BSEG.csv`, HKONT `0000610000`, monthly document references `DEP-FA-00x-YYYY-MM`, posted with `BLART = SA`, each month-end:

| Asset | Monthly charge | FY2024 | FY2025 |
|---|---|---|---|
| FA-001 Racking and handling equipment | 100,000 | 1,200,000 | 1,200,000 |
| FA-002 Delivery fleet | 50,000 | 600,000 | 600,000 |
| FA-003 Warehouse fit-out | 50,000 | 600,000 | 600,000 |
| FA-004 Conveyor and scanner replacement | 20,000 | 240,000 | 240,000 |
| FA-005 Safety and fork-truck replacements | 10,000 | – | 120,000 |
| **Total** | 220,000 → 230,000 | **2,640,000** | **2,760,000** |

The same totals are credited to accumulated depreciation (a/c 150100) each month, so the P&L charge and the balance-sheet movement agree exactly (no disposals, retirements or impairments appear anywhere in the extract).

### 2.4 Fixed asset register

`Fixed_asset_register.xlsx`, sheet "Assets" (dated 2026-01-10):

| Asset | In service | Cost | Life (mths) | Opening accum. (1 Jan 2024) | Accum. dep. FY2024–FY2025 | Closing net |
|---|---|---|---|---|---|---|
| FA-001 | 2022-01-01 | 12,000,000 | 120 | 2,400,000 | 2,400,000 | 7,200,000 |
| FA-002 | 2022-01-01 | 6,000,000 | 120 | 1,200,000 | 1,200,000 | 3,600,000 |
| FA-003 | 2022-01-01 | 6,000,000 | 120 | 1,200,000 | 1,200,000 | 3,600,000 |
| FA-004 | 2024-01-01 | 2,400,000 | 120 | – | 480,000 | 1,920,000 |
| FA-005 | 2025-01-01 | 600,000 | 60 | – | 120,000 | 480,000 |
| **Total** | | **27,000,000** | | **4,800,000** | **5,400,000** | **16,800,000** |

The register reconciles exactly to the ledger: opening accumulated $4.8m + FY2024–25 charge $5.4m = closing accumulated $10.2m, and cost $27.0m − $10.2m = net $16.8m. (Note the register's "Depreciation (USD)" column is the **two-year FY2024 + FY2025** charge, not a single year; the per-asset monthly charges above, which sum to $2.64m / $2.76m, are the correct annual figures.)

### 2.5 Capex programme and the deferral

`Equipment_programme.xlsx`, sheet "Capex" (16 Oct 2025), matching the table in `Board_minutes_2025-10.docx`:

| Project | Description | Approved | Completed | Planned service date |
|---|---|---|---|---|
| CAP-25-01 | Safety and fork-truck replacements | 600,000 | 600,000 | 2025-01-01 |
| CAP-25-02 | Conveyor motor renewal | 1,200,000 | 0 | 2026-04-01 |
| CAP-25-03 | Loading-bay pavement renewal | 600,000 | 0 | 2026-05-01 |

`Board_minutes_2025-01.docx` (15 Jan 2025) records that the board approved **$2.4m of maintenance capex for 2025**. `Board_minutes_2025-10.docx` records that "$1.2m conveyor renewal and $0.6m bay resurfacing" were **deferred to spring 2026 to retain year-end liquidity**, that no supplier order had been issued, and that operations reported "no immediate impairment or closure". Only the $0.6m safety project was executed — which is exactly the $600,000 booked to PP&E in FY2025.

So the low FY2025 capex is not an accounting artefact: **the board explicitly cancelled/deferred $1.8m of the approved programme into FY2026** to protect year-end liquidity.

## 3. Reasoning and interpretation

1. **The comparison is like-for-like.** Both figures come from the same ledger (SAP BSEG/BKPF extract) and the same accounts used in the management accounts, so there is no presentational mismatch. Depreciation is a monotonically increasing 220–230k/month straight-line charge; capex is a single lump at the start of each year.
2. **FY2024 capex ($2.4m) is a coincidence that flatters the ratio.** The 2024 addition (FA-004) happens to equal the annual depreciation of the three legacy 2022 assets ($2.4m) — but it is still below the total charge of $2.64m because FA-004 itself was depreciated from day one.
3. **FY2025 is the real story.** Depreciation rose to $2.76m (FA-005 came on stream) while capex collapsed to $0.6m — 22% of the charge. NBV fell $2.16m in a single year, and the asset base is now **37.8% depreciated** ($10.2m of accumulated depreciation on $27.0m cost).
4. **The business is being sweated, and there is a deferred-spend overhang.** A buyer normalising maintenance capex has to decide whether $0.6m/yr is sustainable. The board's own programme implies a **run-rate closer to $1.5–2.4m/yr** ($2.4m approved for 2025, $1.8m of it pushed into 2026 with no order placed). If the $1.8m deferred works are executed in 2026, FY2026 capex would jump to about $1.8m — roughly 3x the FY2025 level and a capex/depreciation ratio of ~0.65x against a full-year charge of ~$2.76m, but still below depreciation. FY2025's free cash flow therefore benefited from a timing deferral, not a permanent saving.
5. **Underlying assets are approaching mid-life.** The three legacy assets ($24m of the $27m cost base) have a 120-month life from 1 Jan 2022, so they are 48 months / 40% depreciated on a straight-line basis; FA-005 (60-month life) is already 12 months / 20% through its life. The gap between depreciation and capex is therefore likely to reverse: continuing to under-spend would shorten the remaining useful life and eventually force catch-up replacement spend.
6. **No signs of accounting policy change to explain the gap.** Monthly depreciation rates are stable throughout FY2024 and FY2025 (only changing because FA-005 entered service), with no revaluations, useful-life revisions, impairments or disposals in the extract.

## 4. Limitations and follow-up requests

1. **FY2026 has no close.** January 2026 is open (per `Data_dictionary.xlsx`); sales, purchases, receipts and payments are posted but month-end close entries (including the ~$230,000 monthly depreciation) are not. FY2026 capex is therefore 0 only because no asset has been invoiced yet — not evidence of no spend. Request the January–February 2026 fixed-asset additions and the order confirmations for CAP-25-02/03.
2. **No asset-level policy note.** Useful lives are derived from `Fixed_asset_register.xlsx` (cost ÷ life months) and verified against the monthly charges; I have not seen a written capitalisation/depreciation policy, a capitalisation threshold, or evidence that the 120/60-month lives are appropriate. Request the accounting policy note and a peer/benchmark view of lives.
3. **No purchase-order / commitment ledger for capital items** beyond the three-project programme. I cannot confirm whether any 2026 commitments are already contractually committed (the October minutes say no supplier order was issued at that date — request confirmation as at the data-room cut-off).
4. **ERP implementation ($900,000) was expensed, not capitalised** (a/c 609000; `Earnings_schedule.xlsx` and `Board_minutes_2025-12.docx` both show it as a ledger expense that management proposes to add back). If any part is properly capitalisable, adjusted capex would be higher and the capex/depreciation gap narrower; if the add-back is accepted at face value, note that the spend still consumed cash while generating no depreciable asset.
5. **Management accounts are unaudited** and the whole extract is pre-close for 2026. Figures above are drawn from the SAP line-item postings rather than the summaries, and the two agree, but none of the data is audited.
