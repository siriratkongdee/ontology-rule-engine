"""
Base classes for rules and facts.

A Rule is a callable that:
  - Takes a FactContext (user's financial situation)
  - Returns a RuleResult (fired or not, conclusion, reasoning)

The engine collects all applicable rules from the ontology,
evaluates them, resolves conflicts, and synthesizes a QueryResult.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict


@dataclass
class FactContext:
    """
    User's financial facts at query time.
    This is the input to every rule evaluation.
    """
    # Personal
    age: int
    filing_status: str          # 'single' | 'married_filing_jointly' | 'married_filing_separately'
    magi: float                 # Modified Adjusted Gross Income
    earned_income: float
    tax_year: int

    # IRA balances
    traditional_ira_balance: float = 0.0   # pre-tax Traditional IRA
    rollover_ira_balance: float = 0.0      # pre-tax Rollover IRA (from old 401k)
    roth_ira_balance: float = 0.0          # Roth IRA (already tax-free)

    # Optional extras
    employer_plan_balance: float = 0.0     # 401k, 403b — NOT in pro-rata calc
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_pretax_ira_balance(self) -> float:
        """Pre-tax IRA = Traditional + Rollover (NOT Roth, NOT 401k)."""
        return self.traditional_ira_balance + self.rollover_ira_balance

    @property
    def total_ira_balance(self) -> float:
        return self.traditional_ira_balance + self.rollover_ira_balance + self.roth_ira_balance


@dataclass
class RuleResult:
    """Result of evaluating a single rule."""
    rule_name: str
    fired: bool             # True = rule condition was met
    conclusion: str         # short machine-readable tag
    reasoning: str          # human-readable explanation
    priority: int = 0
    overrides: List[str] = field(default_factory=list)


@dataclass
class QueryResult:
    """Final answer from the rule engine, with full reasoning chain."""
    question: str
    answer: str
    eligible: bool
    confidence: str                                     # 'high' | 'medium' | 'low'
    rule_results: List[RuleResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    action_steps: List[str] = field(default_factory=list)
    conflicting_rules: List[tuple] = field(default_factory=list)  # (winner, loser)


class Rule:
    """
    Base class for all rules.

    Subclasses must set:
      - name: str
      - description: str
      - applies_to: List[str]  — ontology concept names
      - priority: int          — higher wins conflicts

    And implement:
      - evaluate(facts, tax_year) -> RuleResult
    """
    name: str = ""
    description: str = ""
    applies_to: List[str] = []
    priority: int = 0
    overrides: List[str] = []

    def evaluate(self, facts: FactContext, tax_year: int) -> RuleResult:
        raise NotImplementedError(f"{self.__class__.__name__} must implement evaluate()")

    def to_rule_node(self):
        """Export as an ontology RuleNode for graph registration."""
        from rule_engine.ontology import RuleNode
        return RuleNode(
            name=self.name,
            description=self.description,
            applies_to=self.applies_to,
            priority=self.priority,
            overrides=self.overrides,
        )
