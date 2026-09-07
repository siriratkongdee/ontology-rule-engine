"""
Ontology graph — defines concepts and their relationships.

The graph has two types of nodes:
  - Concept nodes: what things ARE (IRA, RothIRA, Person, etc.)
  - Rule nodes: logic that applies to concepts

Edges:
  - IS_A: RothIRA IS_A IRA (enables rule inheritance)
  - APPLIES_TO: a rule applies to a concept (and all its descendants)
  - OVERRIDES: rule A overrides rule B (conflict resolution)
  - REQUIRES: rule A requires another rule to fire first
"""

import networkx as nx
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ConceptNode:
    name: str
    description: str
    attributes: Dict[str, str] = field(default_factory=dict)


@dataclass
class RuleNode:
    name: str
    description: str
    applies_to: List[str]           # concept names
    priority: int = 0               # higher = more specific, wins conflicts
    overrides: List[str] = field(default_factory=list)
    effective_years: Optional[List[int]] = None  # None = all years


class Ontology:
    """
    Graph-based ontology. Concepts inherit rules from parent concepts
    via the IS_A hierarchy. More specific rules (higher priority) win
    over general ones; explicit OVERRIDES edges also resolve conflicts.
    """

    def __init__(self):
        self.graph = nx.DiGraph()

    # ── Building the graph ────────────────────────────────────────────

    def add_concept(self, concept: ConceptNode, parent: Optional[str] = None):
        self.graph.add_node(concept.name, node_type="concept", data=concept)
        if parent:
            if parent not in self.graph:
                raise ValueError(f"Parent concept '{parent}' not found — add it first.")
            self.graph.add_edge(parent, concept.name, edge_type="IS_A")

    def add_rule(self, rule: RuleNode):
        self.graph.add_node(rule.name, node_type="rule", data=rule)
        for concept in rule.applies_to:
            self.graph.add_edge(rule.name, concept, edge_type="APPLIES_TO")
        for overridden in rule.overrides:
            self.graph.add_edge(rule.name, overridden, edge_type="OVERRIDES")

    # ── Graph traversal ───────────────────────────────────────────────

    def get_ancestors(self, concept_name: str) -> List[str]:
        """Walk up the IS_A chain — returns all parent concepts."""
        ancestors = []
        for u, v, data in self.graph.edges(data=True):
            if v == concept_name and data.get("edge_type") == "IS_A":
                ancestors.append(u)
                ancestors.extend(self.get_ancestors(u))
        return ancestors

    def get_descendants(self, concept_name: str) -> List[str]:
        """Walk down the IS_A chain — returns all child concepts."""
        descendants = []
        for u, v, data in self.graph.edges(data=True):
            if u == concept_name and data.get("edge_type") == "IS_A":
                descendants.append(v)
                descendants.extend(self.get_descendants(v))
        return descendants

    def get_applicable_rules(self, concept_name: str, tax_year: Optional[int] = None) -> List[RuleNode]:
        """
        Return all rules that apply to a concept — including rules inherited
        from parent concepts via IS_A. Filtered by tax year if provided.
        """
        all_concepts = {concept_name} | set(self.get_ancestors(concept_name))
        rules = []
        for node_name, node_data in self.graph.nodes(data=True):
            if node_data.get("node_type") == "rule":
                rule: RuleNode = node_data["data"]
                if any(c in all_concepts for c in rule.applies_to):
                    if tax_year is None or rule.effective_years is None or tax_year in rule.effective_years:
                        rules.append(rule)
        return rules

    def resolves_conflict(self, winner: str, loser: str) -> bool:
        """Check if winner rule explicitly overrides loser rule."""
        edge_data = self.graph.get_edge_data(winner, loser, default={})
        return edge_data.get("edge_type") == "OVERRIDES"

    def visualize_summary(self) -> str:
        """Print a text summary of the graph."""
        concepts = [(n, d["data"]) for n, d in self.graph.nodes(data=True) if d.get("node_type") == "concept"]
        rules = [(n, d["data"]) for n, d in self.graph.nodes(data=True) if d.get("node_type") == "rule"]
        is_a_edges = [(u, v) for u, v, d in self.graph.edges(data=True) if d.get("edge_type") == "IS_A"]
        overrides_edges = [(u, v) for u, v, d in self.graph.edges(data=True) if d.get("edge_type") == "OVERRIDES"]

        lines = [
            f"Ontology: {len(concepts)} concepts, {len(rules)} rules",
            "",
            "Concept hierarchy (IS_A):",
        ]
        for u, v in is_a_edges:
            lines.append(f"  {v} IS_A {u}")
        lines.append("\nRules:")
        for name, rule in rules:
            lines.append(f"  {name} → applies to: {', '.join(rule.applies_to)}  [priority={rule.priority}]")
        if overrides_edges:
            lines.append("\nConflict resolution (OVERRIDES):")
            for u, v in overrides_edges:
                lines.append(f"  {u} overrides {v}")
        return "\n".join(lines)
