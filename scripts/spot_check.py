import csv

with open("pipeline_main.csv") as f:
    rows = list(csv.DictReader(f))

committed = [r for r in rows if r["Project_Stage"] in ("Contract for Electric Service", "Request for Service")]
print(f"Committed customers (CES+RFS): {len(committed)}  [expected: 31]")

committed_mw = sum(int(r["Announced_Load_MW"]) for r in committed)
print(f"Committed announced load MW:   {committed_mw}  [expected: ~12,400]")

dc = [r for r in committed if r["Segment"] == "Data Center/Crypto"]
ind = [r for r in committed if r["Segment"] != "Data Center/Crypto"]
print(f"  Data center committed:  {len(dc)}  [expected: 26]")
print(f"  Industrial committed:   {len(ind)}  [expected: 5]")

dc_mw = sum(int(r["Announced_Load_MW"]) for r in dc)
ind_mw = sum(int(r["Announced_Load_MW"]) for r in ind)
print(f"  DC total MW:            {dc_mw}  [expected: 11,750 (8,070+3,680 from Table 1)]")
print(f"  Industrial total MW:    {ind_mw}  [expected: 607 (423+184 from Table 1)]")

winter_load = sum(int(r["Load_2028"]) for r in committed)
print(f"\nCommitted 2028 load column sum: {winter_load}  [report says ~7,800 by winter 2028/2029]")

with open("new_projects.csv") as f:
    np_rows = list(csv.DictReader(f))
np_total = sum(int(r["Announced_Load_MW"]) for r in np_rows)
print(f"\nNew projects total MW:   {np_total}  [expected: 12,626]")

with open("pipeline_exits.csv") as f:
    ex_rows = list(csv.DictReader(f))
ex_total = sum(int(r["Announced_Load_MW_Q4_2025"]) for r in ex_rows)
print(f"Pipeline exits total MW: {ex_total}  [expected: 2,850]")

with open("load_changes.csv") as f:
    lc_rows = list(csv.DictReader(f))
lc_total = sum(int(r["Change_MW"]) for r in lc_rows)
print(f"Load changes net MW:     {lc_total}  [expected: -2,518]")
