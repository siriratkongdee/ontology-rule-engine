# Ontology Rule Engine — Product Specification

**Version:** 0.1 (Prototype validated)  
**Status:** Active development  
**Last updated:** 2026-07-28

---

## 1. Problem Statement

Complex rule domains (tax law, financial planning, insurance, compliance) have rules that:
- Are written in natural language across hundreds of pages of documents
- Inherit from parent concepts ("any IRA rule also applies to a Roth IRA")
- Conflict with each other (a specific rule overrides a general rule)
- Change by year, jurisdiction, or filing status
- Must produce auditable reasoning, not just an answer

**RAG systems fail here** because retrieval finds relevant text but cannot guarantee rule precedence, inheritance, or conflict resolution. An LLM reasoning over retrieved chunks may apply the wrong rule or miss an edge case silently.

**This engine solves it** by encoding rules explicitly in a graph structure where:
- Concept hierarchies (IS_A edges) enable rule inheritance
- OVERRIDES edges make conflict resolution deterministic
- Every answer includes a full reasoning chain
- Rules are injected via YAML — no code changes needed to add or update rules

---

## 2. Product Goals

### Must Have (MVP)
- [x] Graph-based ontology with concept hierarchy (IS_A edges)
- [x] Rules stored as nodes with APPLIES_TO and OVERRIDES edges
- [x] Rule evaluation with reasoning chain output
- [x] Conflict resolution via priority + OVERRIDES edges
- [ ] YAML-injectable rules (no Python required to add rules)
- [ ] Generic condition evaluator (comparison, lookup, computed)
- [ ] LLM-powered document-to-YAML extractor

### Should Have (v1)
- [ ] Rule versioning by tax year / jurisdiction
- [ ] REST API for agent queries
- [ ] Rule validation on load (catch schema errors before runtime)
- [ ] Rule diff tool (compare YAML files across years)
- [ ] Web UI for reviewing and approving extracted rules

### Nice to Have (v2)
- [ ] Multi-domain support (tax + insurance + compliance in one engine)
- [ ] Rule conflict detector (flag YAML files with unresolved conflicts)
- [ ] Explanation localization (generate reasoning in plain English vs. technical)

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         INPUT LAYER                             │
│                                                                 │
│   Documents (PDF, Word, URL)      User query + FactContext      │
│          │                                    │                 │
│          ▼                                    ▼                 │
│   ┌─────────────┐                   ┌──────────────────┐       │
│   │  Extractor  │──── YAML rules ──▶│   Rule Loader    │       │
│   │ (LLM-based) │                   │ (validates YAML) │       │
│   └─────────────┘                   └────────┬─────────┘       │
│                                              │                  │
│                                              ▼                  │
│                                    ┌──────────────────┐        │
│                                    │    Ontology      │        │
│                                    │   (nx.DiGraph)   │        │
│                                    │                  │        │
│                                    │  Concept nodes   │        │
│                                    │  Rule nodes      │        │
│                                    │  IS_A edges      │        │
│                                    │  APPLIES_TO      │        │
│                                    │  OVERRIDES       │        │
│                                    └────────┬─────────┘        │
│                                             │                   │
│                                             ▼                   │
│                                    ┌──────────────────┐        │
│                                    │   Rule Engine    │        │
│                                    │                  │        │
│                                    │ 1. collect rules │        │
│                                    │    (IS_A walk)   │        │
│                                    │ 2. evaluate all  │        │
│                                    │ 3. resolve       │        │
│                                    │    conflicts     │        │
│                                    │ 4. synthesize    │        │
│                                    └────────┬─────────┘        │
│                                             │                   │
│                                             ▼                   │
│                                      QueryResult                │
│                              (answer + reasoning chain)         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Data Models

### 4.1 FactContext (Query Input)

The facts about the user/entity being evaluated. All rules receive this as input.

```python
@dataclass
class FactContext:
    # Required
    tax_year: int
    
    # Domain-specific fields are open (use `extra: Dict[str, Any]`)
    # Built-in fields for retirement/tax domain:
    age: int
    filing_status: str          # 'single' | 'married_filing_jointly' | 'married_filing_separately'
    magi: float                 # Modified Adjusted Gross Income
    earned_income: float
    
    # IRA balances
    traditional_ira_balance: float = 0.0
    rollover_ira_balance: float = 0.0
    roth_ira_balance: float = 0.0
    employer_plan_balance: float = 0.0   # 401k/403b — NOT in pro-rata calc
    
    # Derived properties (computed, not set by caller)
    @property
    def total_pretax_ira_balance(self) -> float: ...
    @property
    def total_ira_balance(self) -> float: ...
    
    # Extension point for other domains
    extra: Dict[str, Any] = field(default_factory=dict)
```

### 4.2 RuleResult (Per-rule Output)

```python
@dataclass
class RuleResult:
    rule_name: str
    fired: bool             # True = condition was met
    conclusion: str         # machine-readable tag, e.g. "blocked:no_earned_income"
    reasoning: str          # human-readable explanation
    priority: int
    overrides: List[str]    # rules this result suppresses
    computed: Dict[str, Any] = field(default_factory=dict)  # values computed by this rule
```

### 4.3 QueryResult (Engine Output)

```python
@dataclass
class QueryResult:
    question: str
    answer: str             # human-readable synthesis
    eligible: bool
    confidence: str         # 'high' | 'medium' | 'low'
    rule_results: List[RuleResult]
    warnings: List[str]
    action_steps: List[str]
    conflicting_rules: List[Tuple[str, str]]  # (winner, loser)
```

---

## 5. YAML Rule Schema (Source of Truth)

This is the canonical format for injectable rules. Any rule in any domain must follow this schema.

```yaml
# ── File-level metadata ───────────────────────────────────────────────────────
version: "1.0"                    # schema version
domain: "retirement.ira"          # dot-separated domain path
tax_year: 2026                    # year these rules are effective (null = always)
source: "IRS Publication 590-A"   # document this was extracted from
extracted_by: "claude-sonnet-4"   # model or author
reviewed_by: null                 # human reviewer (null = not yet reviewed)

# ── Concept declarations (optional — can extend built-in ontology) ────────────
concepts:
  - name: ConceptName
    parent: ParentConceptName     # IS_A relationship
    description: "Human-readable description"

# ── Rule definitions ──────────────────────────────────────────────────────────
rules:
  - name: RuleName               # unique identifier, PascalCase
    description: "What this rule checks"
    applies_to:                  # list of concept names (from ontology)
      - ConceptName
    priority: 10                 # integer; higher = more specific, wins conflicts
    overrides:                   # rule names this rule suppresses when it fires
      - OtherRuleName
    effective_years:             # list of years, or null for always
      - 2026

    # ── Conditions (ALL must be true for rule to fire) ─────────────────────
    conditions:
      # Type 1: Simple comparison
      - type: comparison
        field: field_name        # FactContext attribute or computed value
        operator: ">="           # ">=" | "<=" | ">" | "<" | "==" | "!=" | "in" | "not_in"
        value: 1.0               # literal value

      # Type 2: Filing-status lookup (different thresholds per status)
      - type: filing_status_lookup
        field: magi
        operator: ">="
        thresholds:
          single: 165000
          married_filing_jointly: 246000
          married_filing_separately: 10000

      # Type 3: Computed value (evaluate formula first, then compare)
      - type: computed
        name: taxable_pct
        formula: "(total_pretax_ira_balance / total_ira_balance) * 100"
        operator: ">"
        value: 0

      # Type 4: Existence check
      - type: existence
        field: field_name
        exists: true             # true = field must be present and non-null

    # ── Computed values to attach to RuleResult ────────────────────────────
    compute:
      - name: taxable_pct
        formula: "(total_pretax_ira_balance / total_ira_balance) * 100"
      - name: contribution_limit
        formula: "8000 if age >= 50 else 7000"

    # ── Output when condition is met ───────────────────────────────────────
    when_fired:
      conclusion: "category:tag"   # machine-readable, format: "category:tag"
      message: "Template with ${field} and ${computed_name} substitution"

    # ── Output when condition is NOT met ───────────────────────────────────
    when_not_fired:
      conclusion: "ok:tag"
      message: "Template string"
```

### 5.1 Condition Operators

| Operator | Description |
|----------|-------------|
| `>` | Greater than |
| `>=` | Greater than or equal |
| `<` | Less than |
| `<=` | Less than or equal |
| `==` | Equal |
| `!=` | Not equal |
| `in` | Value is in a list |
| `not_in` | Value is not in a list |

### 5.2 Conclusion Tag Format

Conclusions follow the format `category:tag`:

| Category | Meaning |
|----------|---------|
| `blocked` | User is ineligible; action is prohibited |
| `warning` | User can proceed but there is a significant caveat |
| `ok` | Rule checked; no issue found |
| `info` | Informational; does not affect eligibility |

Examples: `blocked:no_earned_income`, `warning:pro_rata_applies`, `ok:pro_rata_cleared`

---

## 6. Component Specifications

### 6.1 Ontology (`rule_engine/ontology.py`)

**Responsibility:** Maintain the concept graph and answer structural queries.

**Interface:**
```python
class Ontology:
    def add_concept(concept: ConceptNode, parent: Optional[str] = None) -> None
    def add_rule(rule: RuleNode) -> None
    def get_ancestors(concept_name: str) -> List[str]
    def get_descendants(concept_name: str) -> List[str]
    def get_applicable_rules(concept_name: str, tax_year: Optional[int]) -> List[RuleNode]
    def visualize_summary() -> str
```

**Invariants:**
- No circular IS_A relationships
- Every rule's `applies_to` concepts must exist in the graph
- Every rule's `overrides` targets must exist in the graph

### 6.2 YAML Loader (`rule_engine/loader.py`) — TO BUILD

**Responsibility:** Parse a YAML rule file, validate it against the schema, and register concepts and rules into the ontology.

**Interface:**
```python
class RuleLoader:
    def load_file(path: str) -> LoadResult
    def load_yaml(content: str) -> LoadResult
    def validate(data: dict) -> List[ValidationError]

@dataclass
class LoadResult:
    success: bool
    rules_loaded: int
    concepts_loaded: int
    errors: List[ValidationError]
    warnings: List[str]
```

**Validation rules:**
- Required fields: `name`, `applies_to`, `priority`, `when_fired.conclusion`, `when_fired.message`
- `applies_to` concepts must exist in the ontology before loading
- `overrides` targets must exist or be declared in the same file
- `priority` must be a positive integer
- Formulas in `compute` and `conditions` must be parseable Python expressions
- Field references in conditions must exist in `FactContext` or be declared in `compute`

### 6.3 Condition Evaluator (`rule_engine/evaluator.py`) — TO BUILD

**Responsibility:** Evaluate a single condition against a FactContext. Returns `(fired: bool, computed: Dict)`.

**Supported condition types:**
- `comparison` — compare a fact field to a literal value
- `filing_status_lookup` — select threshold based on `facts.filing_status`, then compare
- `computed` — evaluate a formula using fact fields, then compare result
- `existence` — check if a fact field is present and non-null
- `composite` — AND/OR of other conditions (v2)

**Formula evaluation:**
- Formulas are Python expressions evaluated in a sandboxed namespace
- Available variables: all `FactContext` fields + previously computed values
- No imports, no function calls, no side effects
- Example: `"(total_pretax_ira_balance / total_ira_balance) * 100"`

### 6.4 Rule Engine (`rule_engine/engine.py`)

**Responsibility:** Orchestrate rule collection, evaluation, conflict resolution, and synthesis.

**Query flow (implemented, will be updated for YAML rules):**
1. `get_applicable_rules(concept, tax_year)` — walk IS_A hierarchy in ontology
2. Evaluate each rule via Condition Evaluator
3. Resolve conflicts: for each OVERRIDES edge where winner fired, mark loser as overridden
4. Call domain synthesizer to build final `QueryResult`

**Conflict resolution algorithm:**
```
For each rule R that fired:
  For each rule O in R.overrides:
    If O also fired:
      Mark O as overridden (keep in reasoning chain, exclude from synthesis)
      Record (R, O) in conflicting_rules

If two rules conflict and neither overrides the other:
  The rule with higher priority wins
  If equal priority: raise ConflictError (must be resolved in YAML)
```

### 6.5 Document Extractor (`rule_engine/extractor.py`) — TO BUILD

**Responsibility:** Convert a source document (PDF, Word, plain text, URL) into a YAML rule file draft.

**Interface:**
```python
class RuleExtractor:
    def __init__(self, llm_client, schema: str)
    def extract(document_text: str, domain: str, tax_year: int) -> ExtractionResult

@dataclass
class ExtractionResult:
    yaml_draft: str
    rules_found: int
    confidence: str           # 'high' | 'medium' | 'low'
    human_review_flags: List[str]  # sections needing human review
```

**LLM prompt strategy:**
- System prompt: include full YAML schema + examples
- User prompt: document text + domain + year
- Ask model to flag ambiguous rules with `reviewed_by: null` and add a `human_review_note` field
- Parse and validate YAML output before returning

**Human review flags (auto-detected):**
- Cross-references to other documents ("see Publication 590-B")
- Conditions with the word "unless", "except", "however"
- Numerical thresholds that may change annually
- Rules that conflict with already-loaded rules

---

## 7. API Design (v1)

The engine will expose a simple REST API so any agent can query it via HTTP.

### POST /query

```json
// Request
{
  "concept": "BackdoorRoth",
  "facts": {
    "age": 50,
    "filing_status": "single",
    "magi": 234000,
    "earned_income": 234000,
    "tax_year": 2026,
    "traditional_ira_balance": 0.07,
    "rollover_ira_balance": 0,
    "roth_ira_balance": 95000
  }
}

// Response
{
  "question": "Backdoor Roth IRA eligibility (2026)",
  "answer": "ELIGIBLE (CLEAN) — Income too high for direct Roth. Backdoor conversion is 100% tax-free.",
  "eligible": true,
  "confidence": "high",
  "rule_results": [
    {
      "rule_name": "ProRataRule",
      "fired": false,
      "conclusion": "ok:pro_rata_cleared",
      "reasoning": "Pre-tax IRA balance $0.07 is negligible",
      "priority": 20
    }
  ],
  "warnings": [],
  "action_steps": [
    "1. Contribute $8,000 to Traditional IRA (non-deductible)",
    "2. Convert to Roth immediately (0% withholding)",
    "3. File Form 8606"
  ],
  "conflicting_rules": []
}
```

### POST /rules/load

Load a YAML rule file into the engine.

```json
// Request
{ "yaml_content": "...", "domain": "retirement.ira" }

// Response
{ "success": true, "rules_loaded": 5, "concepts_loaded": 2, "errors": [] }
```

### POST /extract

Extract rules from a document.

```json
// Request
{ "document_text": "...", "domain": "retirement.ira", "tax_year": 2026 }

// Response
{ "yaml_draft": "...", "rules_found": 8, "human_review_flags": ["Line 47: cross-reference to Pub 590-B"] }
```

### GET /concepts

List all concepts in the ontology with their hierarchy.

### GET /rules

List all loaded rules with metadata.

---

## 8. File Structure

```
ontology-rule-engine/
│
├── SPEC.md                          ← this file
├── README.md                        ← quick start
├── requirements.txt
│
├── rule_engine/
│   ├── __init__.py
│   ├── ontology.py                  ✅ DONE — graph, IS_A, APPLIES_TO, OVERRIDES
│   ├── engine.py                    ✅ DONE (prototype) — needs update for YAML rules
│   ├── loader.py                    ⬜ TO BUILD — YAML → Rule objects
│   ├── evaluator.py                 ⬜ TO BUILD — condition evaluation
│   ├── extractor.py                 ⬜ TO BUILD — document → YAML draft
│   ├── api.py                       ⬜ TO BUILD — FastAPI REST endpoints
│   └── rules/
│       ├── __init__.py
│       ├── base.py                  ✅ DONE — Rule, FactContext, RuleResult, QueryResult
│       └── backdoor_roth.py         ✅ DONE — 5 hardcoded rules (will be replaced by YAML)
│
├── rule_files/                      ← YAML rule files (the "database" of rules)
│   └── retirement/
│       └── backdoor_roth_2026.yaml  ⬜ TO BUILD — first YAML file
│
├── examples/
│   └── backdoor_roth_demo.py        ✅ DONE — prototype demo, 4 test cases
│
└── tests/
    ├── test_ontology.py             ⬜ TO BUILD
    ├── test_loader.py               ⬜ TO BUILD
    ├── test_evaluator.py            ⬜ TO BUILD
    └── test_backdoor_roth.py        ⬜ TO BUILD
```

---

## 9. Build Order

Build in this order — each step has a testable output before moving to the next.

### Phase 1: YAML rules ← CURRENT
**Goal:** Replace hardcoded Python rules with YAML files.

1. Write `rule_files/retirement/backdoor_roth_2026.yaml` — encode the 5 existing rules
2. Build `rule_engine/evaluator.py` — condition evaluation engine
3. Build `rule_engine/loader.py` — parse YAML, validate, register into ontology
4. Update `rule_engine/engine.py` — use YAML-loaded rules instead of hardcoded ones
5. Verify existing demo still passes all 4 test cases

**Done when:** You can delete `rules/backdoor_roth.py` and the engine still works.

### Phase 2: Generic synthesizer
**Goal:** Remove the BackdoorRoth-specific logic from engine.py.

1. Define `Synthesizer` base class with `synthesize(concept, facts, rule_results) -> QueryResult`
2. Implement `BackdoorRothSynthesizer`
3. Register synthesizers in a domain registry
4. Engine calls the right synthesizer based on query concept

**Done when:** Adding a new domain (e.g., RMD rules) requires only a YAML file + a Synthesizer class.

### Phase 3: REST API
**Goal:** Any agent can query the engine over HTTP.

1. `api.py` with FastAPI — `/query`, `/rules/load`, `/concepts`, `/rules`
2. Docker container
3. OpenAPI schema auto-generated

### Phase 4: Document extractor
**Goal:** Convert IRS publications to YAML drafts automatically.

1. PDF/Word/URL → text extraction
2. LLM prompt with schema + few-shot examples
3. YAML validation and human review flag generation
4. Simple web UI for review and approval

---

## 10. Design Decisions & Rationale

| Decision | Choice | Why |
|----------|--------|-----|
| Graph library | NetworkX | Lightweight, no server, easy to prototype. Migrate to Neo4j/Kuzu when needed |
| Rule storage | YAML files | Human-readable, diffable, version-controllable in git |
| Formula evaluation | Python eval() in sandbox | Simple for MVP; replace with safe expression parser (simpleeval) in production |
| API framework | FastAPI | Async, auto-generates OpenAPI schema agents can consume |
| Rule conflicts | Explicit OVERRIDES + priority | Deterministic; ambiguous conflicts must be resolved at authoring time, not runtime |
| Synthesizer pattern | Domain-specific synthesizer class | Keeps engine generic while allowing domain-specific answer formatting |

---

## 11. Out of Scope (v1)

- Multi-jurisdictional rules (federal vs. state tax) — v2
- Real-time rule updates (hot reload) — v2
- User authentication / multi-tenant — v2
- Rule authoring UI — v2
- Non-Python rule formulas (e.g., FEEL/DMN) — evaluate in v2

---

## 12. Glossary

| Term | Definition |
|------|------------|
| Concept | A node in the ontology representing a category of things (IRA, Person, BackdoorRoth) |
| Rule | A condition + conclusion that applies to one or more concepts |
| IS_A | Ontology edge: RothIRA IS_A IRA — child inherits all rules that apply to parent |
| APPLIES_TO | Rule edge: a rule applies to a concept (and all its descendants) |
| OVERRIDES | Rule edge: when rule A fires, it suppresses rule B's conclusion |
| FactContext | The user's facts at query time — input to all rule evaluations |
| QueryResult | The engine's final answer — includes reasoning chain, warnings, action steps |
| Synthesizer | Domain-specific logic that converts raw rule results into a QueryResult |
| Extractor | LLM-powered component that converts documents to YAML rule drafts |
| Domain | A category of rules (e.g., `retirement.ira`, `tax.deductions`) |
