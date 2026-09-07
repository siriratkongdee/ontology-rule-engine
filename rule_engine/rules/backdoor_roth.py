"""
Backdoor Roth IRA rules — first use case for the rule engine prototype.

Rules encoded here (all based on 2026 IRS guidance):
  1. DirectRothBlocked       — MAGI too high for direct Roth contribution
  2. EarnedIncomeRequired    — must have earned income to contribute
  3. ContributionLimit       — $7K/year, $8K if age 50+ (catch-up)
  4. ProRataRule             — pre-tax IRA balance makes conversion taxable
  5. BackdoorRothAvailable   — base rule: mechanism exists (low priority)

Conflict: ProRataRule (priority 20) overrides BackdoorRothAvailable (priority 1).
If ProRata fires, the answer changes from "clean tax-free" to "partially taxable."
"""

from .base import Rule, RuleResult, FactContext

# ── IRS limits by year ────────────────────────────────────────────────────────
IRS_LIMITS = {
    2025: {
        "contribution_under_50": 7000,
        "contribution_50_plus": 8000,
        "roth_phaseout_single_start": 150000,
        "roth_phaseout_single_end": 165000,
        "roth_phaseout_mfj_start": 236000,
        "roth_phaseout_mfj_end": 246000,
    },
    2026: {
        "contribution_under_50": 7000,
        "contribution_50_plus": 8000,
        "roth_phaseout_single_start": 150000,
        "roth_phaseout_single_end": 165000,
        "roth_phaseout_mfj_start": 236000,
        "roth_phaseout_mfj_end": 246000,
    },
}

NEGLIGIBLE_BALANCE = 1.0  # balances below $1 are treated as zero


def _get_limits(tax_year: int) -> dict:
    return IRS_LIMITS.get(tax_year, IRS_LIMITS[2026])


# ── Rule definitions ──────────────────────────────────────────────────────────

class EarnedIncomeRequired(Rule):
    """IRA contributions require earned income in the same tax year."""
    name = "EarnedIncomeRequired"
    description = "Must have earned income to contribute to any IRA"
    applies_to = ["IRA", "BackdoorRoth"]   # IRA via IS_A; BackdoorRoth explicitly (first step requires IRA contribution)
    priority = 15

    def evaluate(self, facts: FactContext, tax_year: int) -> RuleResult:
        if facts.earned_income <= 0:
            return RuleResult(
                rule_name=self.name,
                fired=True,
                conclusion="blocked:no_earned_income",
                reasoning="No earned income — IRA contributions not allowed",
                priority=self.priority,
            )
        return RuleResult(
            rule_name=self.name,
            fired=False,
            conclusion="ok:earned_income",
            reasoning=f"Earned income ${facts.earned_income:,.0f} satisfies IRA contribution requirement",
            priority=self.priority,
        )


class ContributionLimit(Rule):
    """Annual IRA contribution cap, with age 50+ catch-up."""
    name = "ContributionLimit"
    description = "IRA annual contribution limit based on age"
    applies_to = ["IRA"]
    priority = 5

    def evaluate(self, facts: FactContext, tax_year: int) -> RuleResult:
        limits = _get_limits(tax_year)
        if facts.age >= 50:
            limit = limits["contribution_50_plus"]
            reasoning = f"Age {facts.age} — catch-up limit: ${limit:,}/year"
        else:
            limit = limits["contribution_under_50"]
            reasoning = f"Age {facts.age} — standard limit: ${limit:,}/year"
        return RuleResult(
            rule_name=self.name,
            fired=True,
            conclusion=f"contribution_limit:{limit}",
            reasoning=reasoning,
            priority=self.priority,
        )


class DirectRothBlocked(Rule):
    """High MAGI earners cannot contribute directly to Roth IRA."""
    name = "DirectRothBlocked"
    description = "MAGI above threshold blocks direct Roth IRA contribution"
    applies_to = ["RothIRA"]
    priority = 10

    def evaluate(self, facts: FactContext, tax_year: int) -> RuleResult:
        limits = _get_limits(tax_year)
        fs = facts.filing_status

        if fs == "single":
            phaseout_end = limits["roth_phaseout_single_end"]
        elif fs == "married_filing_jointly":
            phaseout_end = limits["roth_phaseout_mfj_end"]
        else:
            # MFS: Roth contribution almost always fully phased out
            phaseout_end = 10000

        if facts.magi >= phaseout_end:
            return RuleResult(
                rule_name=self.name,
                fired=True,
                conclusion="blocked:direct_roth_income_limit",
                reasoning=(
                    f"MAGI ${facts.magi:,.0f} exceeds Roth IRA income limit "
                    f"(${phaseout_end:,} for {fs}) — direct contribution not allowed"
                ),
                priority=self.priority,
            )
        return RuleResult(
            rule_name=self.name,
            fired=False,
            conclusion="ok:direct_roth_allowed",
            reasoning=f"MAGI ${facts.magi:,.0f} is within Roth IRA income limits for {fs}",
            priority=self.priority,
        )


class ProRataRule(Rule):
    """
    Pre-tax IRA balances (Traditional + Rollover) create a taxable portion
    on any Roth conversion. This OVERRIDES the clean backdoor assumption.

    Note: employer plans (401k, 403b) are NOT included in the pro-rata calc.
    """
    name = "ProRataRule"
    description = "Pre-tax IRA balances make Roth conversion partially taxable"
    applies_to = ["BackdoorRoth"]
    priority = 20
    overrides = ["BackdoorRothAvailable"]   # conflict resolution edge

    def evaluate(self, facts: FactContext, tax_year: int) -> RuleResult:
        pretax = facts.total_pretax_ira_balance
        total = facts.total_ira_balance

        if pretax <= NEGLIGIBLE_BALANCE:
            return RuleResult(
                rule_name=self.name,
                fired=False,
                conclusion="ok:pro_rata_cleared",
                reasoning=(
                    f"Pre-tax IRA balance ${pretax:.2f} is negligible — "
                    "clean backdoor Roth available"
                ),
                priority=self.priority,
                overrides=self.overrides,
            )

        taxable_pct = (pretax / total * 100) if total > 0 else 0.0
        return RuleResult(
            rule_name=self.name,
            fired=True,
            conclusion="warning:pro_rata_applies",
            reasoning=(
                f"Pre-tax IRA balance ${pretax:,.2f} triggers pro-rata rule. "
                f"{taxable_pct:.1f}% of any conversion will be taxable. "
                f"(Total IRA: ${total:,.2f})"
            ),
            priority=self.priority,
            overrides=self.overrides,
        )


class BackdoorRothAvailable(Rule):
    """
    Base rule: the backdoor Roth mechanism exists and is legal.
    Low priority — overridden by ProRataRule when pre-tax IRA exists.
    """
    name = "BackdoorRothAvailable"
    description = "Backdoor Roth IRA: contribute to Traditional IRA then convert to Roth"
    applies_to = ["BackdoorRoth"]
    priority = 1

    def evaluate(self, facts: FactContext, tax_year: int) -> RuleResult:
        return RuleResult(
            rule_name=self.name,
            fired=True,
            conclusion="ok:backdoor_mechanism_available",
            reasoning=(
                "Backdoor Roth mechanism: contribute non-deductible to Traditional IRA, "
                "then convert immediately to Roth (Step Transaction Doctrine applies — "
                "IRS has not challenged this strategy)"
            ),
            priority=self.priority,
        )


# ── Registry: all backdoor Roth rules ────────────────────────────────────────
ALL_RULES: list[Rule] = [
    EarnedIncomeRequired(),
    ContributionLimit(),
    DirectRothBlocked(),
    ProRataRule(),
    BackdoorRothAvailable(),
]
