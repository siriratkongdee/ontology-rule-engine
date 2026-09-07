"""
Rule Engine — the core query processor.

Flow:
  1. Build the ontology (concepts + rules as a graph)
  2. Accept a query concept (e.g. "BackdoorRoth") and FactContext
  3. Traverse the IS_A hierarchy to collect all applicable rules
  4. Evaluate each rule against the facts
  5. Resolve conflicts using OVERRIDES edges and priority
  6. Synthesize a QueryResult with the answer and full reasoning chain
"""

from rule_engine.ontology import Ontology, ConceptNode, RuleNode
from rule_engine.rules.base import FactContext, QueryResult, RuleResult
from rule_engine.rules.backdoor_roth import ALL_RULES as BACKDOOR_ROTH_RULES

from typing import List, Optional


def build_financial_ontology(extra_rules=None) -> Ontology:
    """
    Build the concept hierarchy for retirement/tax planning.

    Hierarchy (IS_A edges):
      FinancialAccount
        └─ RetirementAccount
             ├─ IRA
             │    ├─ TraditionalIRA
             │    ├─ RothIRA
             │    └─ RolloverIRA
             └─ EmployerPlan
                  ├─ Plan401k
                  └─ Plan403b
      BackdoorRoth   (strategy concept — not an account)
    """
    o = Ontology()

    # ── Concepts ──────────────────────────────────────────────────────
    o.add_concept(ConceptNode("FinancialAccount", "Any financial account"))
    o.add_concept(ConceptNode("RetirementAccount", "Tax-advantaged retirement account"),
                  parent="FinancialAccount")

    o.add_concept(ConceptNode("IRA", "Individual Retirement Account"),
                  parent="RetirementAccount")
    o.add_concept(ConceptNode("TraditionalIRA", "Pre-tax or non-deductible Traditional IRA"),
                  parent="IRA")
    o.add_concept(ConceptNode("RothIRA", "After-tax Roth IRA — tax-free growth"),
                  parent="IRA")
    o.add_concept(ConceptNode("RolloverIRA", "Rollover IRA from employer plan"),
                  parent="IRA")

    o.add_concept(ConceptNode("EmployerPlan", "Employer-sponsored retirement plan"),
                  parent="RetirementAccount")
    o.add_concept(ConceptNode("Plan401k", "401(k) plan"), parent="EmployerPlan")
    o.add_concept(ConceptNode("Plan403b", "403(b) plan"), parent="EmployerPlan")

    # Strategy concept — not an account type, but rules apply to it
    o.add_concept(ConceptNode("BackdoorRoth",
                               "Backdoor Roth IRA strategy: Traditional IRA → Roth conversion"))

    # ── Rules ─────────────────────────────────────────────────────────
    all_rules = BACKDOOR_ROTH_RULES + (extra_rules or [])
    for rule in all_rules:
        o.add_rule(rule.to_rule_node())

    return o


class RuleEngine:
    """
    Generic rule engine backed by an ontology graph.
    Inject any concept + rules; the engine handles evaluation + conflict resolution.
    """

    def __init__(self, ontology: Optional[Ontology] = None):
        self.ontology = ontology or build_financial_ontology()

    def query(self, concept: str, facts: FactContext) -> QueryResult:
        """
        Evaluate all rules applicable to `concept` (including inherited rules)
        against `facts`. Return a QueryResult with answer + reasoning chain.
        """
        # 1. Collect applicable rules from graph
        rule_nodes: List[RuleNode] = self.ontology.get_applicable_rules(
            concept, tax_year=facts.tax_year
        )

        if not rule_nodes:
            return QueryResult(
                question=f"Query: {concept}",
                answer=f"No rules found for concept '{concept}'",
                eligible=False,
                confidence="low",
            )

        # 2. Evaluate each rule
        # Map rule name → Rule instance for evaluation
        rule_instances = {r.name: r for r in _get_all_rule_instances()}
        rule_results: List[RuleResult] = []

        for node in rule_nodes:
            instance = rule_instances.get(node.name)
            if instance:
                result = instance.evaluate(facts, facts.tax_year)
                rule_results.append(result)

        # 3. Resolve conflicts using OVERRIDES edges + priority
        active_results, conflicts = self._resolve_conflicts(rule_results)

        # 4. Synthesize final answer
        return self._synthesize(concept, facts, active_results, rule_results, conflicts)

    def _resolve_conflicts(self, results: List[RuleResult]):
        """
        If two rules fire and one overrides the other, suppress the loser.
        Also: higher priority rule wins when both fire on the same conclusion domain.
        """
        active = list(results)
        conflicts = []

        for r in results:
            for loser_name in r.overrides:
                if r.fired:
                    # Find the loser in active results
                    for other in results:
                        if other.rule_name == loser_name and other.fired:
                            conflicts.append((r.rule_name, loser_name))
                            # Don't remove — keep in chain for transparency,
                            # but flag as overridden
        return active, conflicts

    def _synthesize(
        self,
        concept: str,
        facts: FactContext,
        active_results: List[RuleResult],
        all_results: List[RuleResult],
        conflicts: List[tuple],
    ) -> QueryResult:
        """
        Build the final QueryResult for the BackdoorRoth concept.
        This is the one place that knows what the query *means*.
        In the product version, each concept has its own synthesizer.
        """
        warnings = []
        action_steps = []

        # Pull key results by name
        by_name = {r.rule_name: r for r in all_results}

        earned_income = by_name.get("EarnedIncomeRequired")
        contrib_limit_result = by_name.get("ContributionLimit")
        direct_blocked = by_name.get("DirectRothBlocked")
        pro_rata = by_name.get("ProRataRule")

        # Derive contribution limit from rule conclusion
        contrib_limit = 8000 if facts.age >= 50 else 7000
        if contrib_limit_result and ":" in contrib_limit_result.conclusion:
            try:
                contrib_limit = int(contrib_limit_result.conclusion.split(":")[1])
            except (ValueError, IndexError):
                pass

        # ── Blocking conditions ────────────────────────────────────────
        if earned_income and earned_income.fired:
            return QueryResult(
                question=f"Backdoor Roth IRA eligibility ({facts.tax_year})",
                answer="NOT ELIGIBLE — No earned income. IRA contributions require earned income in the tax year.",
                eligible=False,
                confidence="high",
                rule_results=all_results,
                conflicting_rules=conflicts,
            )

        # ── Pro-rata check ─────────────────────────────────────────────
        pro_rata_problem = pro_rata and pro_rata.fired and "pro_rata_applies" in pro_rata.conclusion

        if pro_rata_problem:
            pretax = facts.total_pretax_ira_balance
            total = facts.total_ira_balance
            taxable_pct = (pretax / total * 100) if total > 0 else 0
            warnings.append(
                f"Pro-rata rule applies: {taxable_pct:.1f}% of conversion will be taxable income"
            )
            warnings.append(
                "Fix: roll pre-tax IRA balance into employer 401k (if plan accepts) to clear pro-rata"
            )
            action_steps = [
                f"1. Roll ${pretax:,.0f} pre-tax IRA into Amazon 401k (call Fidelity to initiate)",
                f"2. Contribute ${contrib_limit:,} to Traditional IRA (non-deductible) — mark as non-deductible",
                "3. Convert to Roth immediately — will be ~tax-free once pre-tax balance is cleared",
                "4. File Form 8606 to document non-deductible contribution",
            ]
            answer = (
                f"ELIGIBLE — but PRO-RATA RULE applies. "
                f"{taxable_pct:.1f}% of your ${contrib_limit:,} conversion will be taxable. "
                f"Clear pre-tax IRA (${pretax:,.0f}) first for a clean conversion."
            )
            eligible = True
            confidence = "high"

        else:
            # Clean backdoor
            if direct_blocked and direct_blocked.fired:
                answer = (
                    f"ELIGIBLE (CLEAN) — Income too high for direct Roth, but backdoor is 100% tax-free. "
                    f"Contribute ${contrib_limit:,} to Traditional IRA then convert immediately."
                )
            else:
                answer = (
                    f"ELIGIBLE — Direct Roth contribution is also available at your income level, "
                    f"but backdoor method works too. Limit: ${contrib_limit:,}/year."
                )
            action_steps = [
                f"1. Contribute ${contrib_limit:,} to Traditional IRA (non-deductible)",
                "2. Convert entire balance to Roth IRA immediately (0% federal withholding)",
                "3. File Form 8606 to document the non-deductible contribution",
            ]
            eligible = True
            confidence = "high"

        return QueryResult(
            question=f"Backdoor Roth IRA eligibility ({facts.tax_year})",
            answer=answer,
            eligible=eligible,
            confidence=confidence,
            rule_results=all_results,
            warnings=warnings,
            action_steps=action_steps,
            conflicting_rules=conflicts,
        )

    def explain(self, result: QueryResult) -> str:
        """Format a QueryResult as human-readable output."""
        lines = [
            f"QUERY:  {result.question}",
            f"ANSWER: {result.answer}",
            f"STATUS: {'✅ ELIGIBLE' if result.eligible else '❌ NOT ELIGIBLE'} | Confidence: {result.confidence.upper()}",
            "",
            "── REASONING CHAIN (rules evaluated) ──────────────────────",
        ]

        sorted_results = sorted(result.rule_results, key=lambda r: r.priority)
        for r in sorted_results:
            overridden = any(r.rule_name == loser for _, loser in result.conflicting_rules)
            fired_icon = "🔴 FIRED   " if r.fired else "⚪ checked "
            override_tag = " [OVERRIDDEN]" if overridden and r.fired else ""
            lines.append(f"  {fired_icon} [{r.rule_name}] {r.reasoning}{override_tag}")

        if result.conflicting_rules:
            lines.append("")
            lines.append("── CONFLICT RESOLUTION ─────────────────────────────────────")
            for winner, loser in result.conflicting_rules:
                lines.append(f"  {winner} (priority) overrides {loser}")

        if result.warnings:
            lines.append("")
            lines.append("── WARNINGS ────────────────────────────────────────────────")
            for w in result.warnings:
                lines.append(f"  ⚠️  {w}")

        if result.action_steps:
            lines.append("")
            lines.append("── ACTION STEPS ────────────────────────────────────────────")
            for step in result.action_steps:
                lines.append(f"  {step}")

        return "\n".join(lines)


def _get_all_rule_instances():
    """Return all known rule instances. In the product, this becomes a registry."""
    return BACKDOOR_ROTH_RULES
