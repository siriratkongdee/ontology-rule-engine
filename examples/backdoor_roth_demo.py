"""
Prototype demo: Backdoor Roth IRA rule engine.

4 test cases that cover the main scenarios:
  1. Siri's actual situation — clean backdoor (pro-rata cleared)
  2. Same person with $100K pre-tax Rollover IRA — pro-rata problem
  3. Lower-income person — direct Roth also available
  4. Retiree with no earned income — blocked

Run:
  cd ontology-rule-engine
  python examples/backdoor_roth_demo.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rule_engine import RuleEngine, FactContext
from rule_engine.engine import build_financial_ontology

# ── Build the engine ──────────────────────────────────────────────────────────
ontology = build_financial_ontology()
engine = RuleEngine(ontology)

DIVIDER = "\n" + "=" * 65 + "\n"

# Print ontology summary
print(DIVIDER.strip())
print("ONTOLOGY GRAPH SUMMARY")
print(ontology.visualize_summary())


# ── Test Case 1: Siri — pro-rata cleared ─────────────────────────────────────
print(DIVIDER)
print("TEST 1: Siri — MAGI $234K, age 50, pre-rata IRA cleared ($0.07)")
print()

siri = FactContext(
    age=50,
    filing_status="single",
    magi=234_000,
    earned_income=234_000,
    tax_year=2026,
    traditional_ira_balance=0.07,   # residual from rollover (negligible)
    rollover_ira_balance=0.0,
    roth_ira_balance=95_000,
)
result1 = engine.query("BackdoorRoth", siri)
print(engine.explain(result1))


# ── Test Case 2: Siri WITH $100K Rollover IRA (pro-rata problem) ──────────────
print(DIVIDER)
print("TEST 2: Same person but $100K in Rollover IRA — pro-rata problem")
print()

siri_with_ira = FactContext(
    age=50,
    filing_status="single",
    magi=234_000,
    earned_income=234_000,
    tax_year=2026,
    traditional_ira_balance=0.0,
    rollover_ira_balance=100_000,   # ← triggers pro-rata
    roth_ira_balance=95_000,
)
result2 = engine.query("BackdoorRoth", siri_with_ira)
print(engine.explain(result2))


# ── Test Case 3: Lower income person — direct Roth also available ─────────────
print(DIVIDER)
print("TEST 3: Lower income — MAGI $80K, direct Roth allowed too")
print()

lower_income = FactContext(
    age=35,
    filing_status="single",
    magi=80_000,
    earned_income=80_000,
    tax_year=2026,
    traditional_ira_balance=0.0,
    rollover_ira_balance=0.0,
    roth_ira_balance=0.0,
)
result3 = engine.query("BackdoorRoth", lower_income)
print(engine.explain(result3))


# ── Test Case 4: Retiree — no earned income ───────────────────────────────────
print(DIVIDER)
print("TEST 4: Retiree — no earned income, large pre-tax IRA")
print()

retiree = FactContext(
    age=67,
    filing_status="married_filing_jointly",
    magi=120_000,
    earned_income=0,            # ← blocked
    tax_year=2026,
    traditional_ira_balance=500_000,
    rollover_ira_balance=0.0,
    roth_ira_balance=200_000,
    employer_plan_balance=400_000,
)
result4 = engine.query("BackdoorRoth", retiree)
print(engine.explain(result4))

print(DIVIDER.strip())
print("Prototype complete. All 4 scenarios evaluated.")
print("Next: make rules injectable from YAML/JSON config.")
