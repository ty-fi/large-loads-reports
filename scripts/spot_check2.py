import csv

with open("pipeline_main.csv") as f:
    rows = list(csv.DictReader(f))

committed = [r for r in rows if r["Project_Stage"] in ("Contract for Electric Service", "Request for Service")]

# Table 1 in the PDF gives explicit subtotals we can cross-check:
#   DC broken ground: 8,070  (18 projects)
#   DC pending:       3,680  (8 projects)
#   Industrial broken ground: 423  (3 projects)
#   Industrial pending:       184  (2 projects)
# Grand total from Table 1 subtotals: 12,357
# The narrative says "12,400 MW" - let's see if that's rounding.

# Table 1 lists specific MW values for each group.
# Cross-reference: broken-ground DC values from Table 1 (page 7):
table1_dc_bg    = [1429,1400,901,800,523,432,324,311,240,240,225,216,192,182,180,180,150,145]
table1_dc_pend  = [1400,693,502,300,233,216,216,120]
table1_ind_bg   = [207,126,90]
table1_ind_pend = [105,79]

t1_total = sum(table1_dc_bg + table1_dc_pend + table1_ind_bg + table1_ind_pend)
print(f"Table 1 individual MW values sum: {t1_total}")
print(f"  DC broken ground subtotal:  {sum(table1_dc_bg)}  [Table 1 says: 8,070]")
print(f"  DC pending subtotal:        {sum(table1_dc_pend)}  [Table 1 says: 3,680]")
print(f"  Ind broken ground subtotal: {sum(table1_ind_bg)}   [Table 1 says: 423]")
print(f"  Ind pending subtotal:       {sum(table1_ind_pend)}   [Table 1 says: 184]")

# All 31 committed projects from my CSV
my_loads = sorted([int(r["Announced_Load_MW"]) for r in committed], reverse=True)
table1_all = sorted(table1_dc_bg + table1_dc_pend + table1_ind_bg + table1_ind_pend, reverse=True)

print(f"\nMy CSV loads (sorted):     {my_loads}")
print(f"Table 1 loads (sorted):    {table1_all}")

mismatches = []
for v in table1_all:
    if v in my_loads:
        my_loads.remove(v)
    else:
        mismatches.append(('in Table1 not in CSV', v))
for v in my_loads:
    mismatches.append(('in CSV not in Table1', v))

if mismatches:
    print(f"\nMismatches:")
    for m in mismatches:
        print(f"  {m}")
else:
    print(f"\nNo mismatches -- every Table 1 value is in my CSV and vice versa.")

print(f"\nConclusion: Table 1 subtotals sum to exactly {t1_total}, not 12,400.")
print(f"The narrative '12,400 MW' appears to be rounded to the nearest 100.")
