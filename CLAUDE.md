# Ontology Rule Engine — Agent Context

## What this project is

A graph-based rule engine for complex rule domains (tax law, financial planning). Rules are encoded in an ontology graph (concepts + relationships) and evaluated deterministically — with full reasoning chains, conflict resolution, and rule inheritance. Designed to replace RAG for rule-heavy domains where LLMs reason poorly over conflicting rules.

**Primary use case:** Financial advisor for pre- and post-retirement planning. User inputs their financial facts → engine returns eligibility, action steps, and full reasoning chain.

**Product goal:** Make rules injectable via YAML so domain experts (not developers) can add/update rules without writing Python. LLM-powered extractor converts source documents (IRS publications, policy PDFs) to YAML drafts for human review.

---

## What's already built

| File | Status | Description |
|------|--------|-------------|
| `SPEC.md` | ✅ Done | Full product specification — read this first for deep context |
| `rule_engine/ontology.py` | ✅ Done | Graph (NetworkX): concepts, IS_A, APPLIES_TO, OVERRIDES edges |
| `rule_engine/rules/base.py` | ✅ Done | Rule, FactContext, RuleResult, QueryResult dataclasses |
| `rule_engine/rules/backdoor_roth.py` | ✅ Done | 5 hardcoded backdoor Roth rules (prototype only) |
| `rule_engine/engine.py` | ✅ Done | Query engine: collects rules via IS_A walk, evaluates, resolves conflicts, synthesizes |
| `examples/backdoor_roth_demo.py` | ✅ Done | 4 test cases — all pass |

The prototype validates the concept. Run `python examples/backdoor_roth_demo.py` to verify.

---

## What to build next (Phase 1 — YAML rules)

**Goal:** Replace hardcoded Python rules with YAML files. Done when you can delete `rule_engine/rules/backdoor_roth.py` and the demo still passes all 4 test cases.

### Step 1: Write `rule_files/retirement/backdoor_roth_2026.yaml`
Encode the 5 existing rules in YAML following the schema in SPEC.md Section 5.

### Step 2: Build `rule_engine/evaluator.py`
Generic condition evaluator. Input: a condition dict + FactContext. Output: (fired: bool, computed: dict).

Support these condition types (see SPEC.md Section 6.3):
- `comparison` — compare a fact field to a literal value
- `filing_status_lookup` — threshold varies by filing_status
- `computed` — evaluate a formula, then compare
- `existence` — check field is present and non-null

For formula evaluation, use `simpleeval` library (safer than raw eval).

### Step 3: Build `rule_engine/loader.py`
Parse a YAML rule file → validate → register concepts and rules into the ontology.

```python
class RuleLoader:
    def load_file(path: str, ontology: Ontology) -> LoadResult
    def validate(data: dict) -> List[ValidationError]
```

### Step 4: Update `rule_engine/engine.py`
- Remove hardcoded rule imports
- Load rules from YAML files at startup
- Use generic Evaluator for condition checking

### Step 5: Verify
Run `python examples/backdoor_roth_demo.py` — all 4 test cases must still pass.

---

## Financial advisor rule domains (full roadmap)

### Pre-retirement
| Domain | Description | Priority |
|--------|-------------|----------|
| `retirement.ira.backdoor_roth` | ✅ Prototype done | P0 |
| `retirement.401k.mega_backdoor` | After-tax 401k → in-plan Roth conversion | P1 |
| `retirement.ira.contribution_limit` | IRA contribution eligibility by income/age | P1 |
| `retirement.401k.contribution_limit` | 401k limits, catch-up, employer match | P1 |
| `tax.capital_gains.rsu` | RSU vest → hold vs. sell vs. donate strategy | P2 |
| `tax.roth_conversion_ladder` | Multi-year Roth conversion optimization | P2 |
| `retirement.rule_of_55` | Penalty-free 401k access at exactly age 55 | P2 |

### Post-retirement
| Domain | Description | Priority |
|--------|-------------|----------|
| `retirement.rmd` | Required Minimum Distributions starting age 73 | P1 |
| `retirement.social_security` | Claiming age optimization (62 vs 67 vs 70) | P1 |
| `tax.medicare_irmaa` | Medicare income surcharge thresholds | P2 |
| `retirement.drawdown_order` | Taxable → Traditional → Roth drawdown sequencing | P2 |
| `tax.qcd` | Qualified Charitable Distribution from IRA (age 70½+) | P3 |

---

## Key data model: FactContext

```python
@dataclass
class FactContext:
    age: int
    filing_status: str          # 'single' | 'married_filing_jointly' | 'married_filing_separately'
    magi: float
    earned_income: float
    tax_year: int
    traditional_ira_balance: float = 0.0
    rollover_ira_balance: float = 0.0
    roth_ira_balance: float = 0.0
    employer_401k_balance: float = 0.0
    after_tax_401k_balance: float = 0.0
    social_security_age: Optional[int] = None
    pension_income: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)
```

---

## Architecture principles (do not change)

1. **Graph is the source of truth.** Rules discover applicable concepts via IS_A traversal — never hardcode which rules apply to which query.
2. **Rules are YAML-first.** No new rule domains as Python classes. Write YAML, load via loader.
3. **Conflict resolution is explicit.** Ambiguous conflicts raise `ConflictError` at load time.
4. **Reasoning chain is non-negotiable.** Every QueryResult includes full rule evaluation chain.
5. **FactContext is the only input.** Rules never call external APIs. Add fields to FactContext instead.

---

## Running the project

```bash
pip install networkx pydantic simpleeval pyyaml
python examples/backdoor_roth_demo.py
```

---

## About the primary user

Siri Kongdee, age 50, Amazon software engineer, planning to semi-retire at 55. Already executed:
- Backdoor Roth IRA 2026 ($8,600 converted at Schwab)
- Rollover IRA → Amazon 401k (pro-rata rule cleared)
- 401k mega backdoor (5% after-tax + in-plan Roth conversion)
- $80K dip fund in SWVXX (Schwab money market)

The rule engine will power a financial advisor app for people in similar situations.
