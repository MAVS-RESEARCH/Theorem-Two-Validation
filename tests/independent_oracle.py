"""Independently structured finite-state oracle for the Phase 4 closeout.

This module enumerates the tiny PC graph with a FIFO queue and then
selects the minimum closing cost from the completed reachable set. It
does not import or call production search routines.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass

from checker import (
    EvaluatorPolicyClass,
    EvidenceRecord,
    Instance,
    RepresentationId,
    ValidationError,
)


LOGGER = logging.getLogger("pc_checker")


@dataclass(frozen=True, slots=True)
class OracleState:
    """Semantic oracle state plus accumulated path cost."""

    representation: RepresentationId
    admitted: frozenset[str]
    history: frozenset[str]
    cost: int


@dataclass(frozen=True, slots=True)
class OracleEvaluation:
    """Oracle comparison payload required by WorkPlan.md Phase 4."""

    policy_class: str
    closed: bool
    minimum_closure_cost: int | None
    frontier_exhausted: bool
    reachable_state_count: int


def _semantic_key(
    state: OracleState,
) -> tuple[str, frozenset[str], frozenset[str]]:
    return (state.representation.value, state.admitted, state.history)


def _record_index(instance: Instance) -> dict[str, EvidenceRecord]:
    records: dict[str, EvidenceRecord] = {}
    for record in instance.initial_state.history:
        records[record.identifier] = record
    for action in instance.evidence_actions:
        for record in action.outcomes:
            records[record.identifier] = record
    return records


def _policy_restricts_to_initial_representation(
    policy_class: EvaluatorPolicyClass,
) -> bool:
    if policy_class is EvaluatorPolicyClass.FULL_PC:
        return False
    if policy_class is EvaluatorPolicyClass.FIXED_R:
        return True
    unused: EvaluatorPolicyClass = policy_class
    raise ValidationError(f"unsupported evaluator policy class: {unused}")


def _oracle_successors(
    instance: Instance,
    state: OracleState,
    policy_class: EvaluatorPolicyClass,
) -> tuple[OracleState, ...]:
    restrict = _policy_restricts_to_initial_representation(policy_class)
    initial_representation = instance.initial_state.representation
    generated: list[OracleState] = []
    for action in instance.evidence_actions:
        if state.representation not in action.legal_from:
            continue
        if restrict and state.representation is not initial_representation:
            continue
        history = set(state.history)
        admitted = set(state.admitted)
        for outcome in action.outcomes:
            history.add(outcome.identifier)
            if outcome.valid and outcome.admitted:
                admitted.add(outcome.identifier)
        generated.append(
            OracleState(
                representation=state.representation,
                admitted=frozenset(admitted),
                history=frozenset(history),
                cost=state.cost + action.cost,
            )
        )
    for action in instance.representation_actions:
        if not action.enabled or action.source is not state.representation:
            continue
        if restrict and action.destination is not initial_representation:
            continue
        generated.append(
            OracleState(
                representation=action.destination,
                admitted=state.admitted,
                history=state.history,
                cost=state.cost + action.cost,
            )
        )
    return tuple(generated)


def _oracle_closes(
    instance: Instance,
    state: OracleState,
    records: dict[str, EvidenceRecord],
) -> bool:
    if state.representation is RepresentationId.R0:
        return len(instance.hypotheses) == 1
    if state.representation is RepresentationId.R1:
        target = instance.initial_state.certificate.target
        labels = {
            record.target_label
            for identifier in state.admitted
            if (record := records.get(identifier)) is not None
            and record.valid
            and record.admitted
            and record.target == target
            and record.target_label is not None
        }
        if len(labels) != 1:
            return False
        label = next(iter(labels))
        alternatives = [
            hypothesis
            for hypothesis in instance.hypotheses
            if hypothesis.target_label == label
        ]
        return len(alternatives) == 1
    unused: RepresentationId = state.representation
    raise ValidationError(f"unsupported representation: {unused}")


def enumerate_finite_graph(
    instance: Instance,
    policy_class: EvaluatorPolicyClass,
) -> OracleEvaluation:
    """Enumerate every reachable semantic state with a FIFO frontier."""

    # Console log P4-ORACLE-01: identify independent FIFO enumeration start.
    LOGGER.info(
        "P4-ORACLE-01 independent_fifo_enumeration_started policy=%s",
        policy_class.value,
    )
    records = _record_index(instance)
    start = OracleState(
        representation=instance.initial_state.representation,
        admitted=frozenset(instance.initial_state.admitted_evidence),
        history=frozenset(
            record.identifier for record in instance.initial_state.history
        ),
        cost=instance.initial_state.cost,
    )
    best_costs: dict[tuple[str, frozenset[str], frozenset[str]], int] = {
        _semantic_key(start): start.cost
    }
    reached: dict[tuple[str, frozenset[str], frozenset[str]], OracleState] = {
        _semantic_key(start): start
    }
    frontier: deque[OracleState] = deque([start])
    while frontier:
        current = frontier.popleft()
        current_key = _semantic_key(current)
        if current.cost != best_costs[current_key]:
            continue
        for successor in _oracle_successors(instance, current, policy_class):
            successor_key = _semantic_key(successor)
            prior = best_costs.get(successor_key)
            if prior is not None and successor.cost >= prior:
                continue
            best_costs[successor_key] = successor.cost
            reached[successor_key] = successor
            frontier.append(successor)
    # Console log P4-ORACLE-02: identify FIFO frontier exhaustion.
    LOGGER.info(
        "P4-ORACLE-02 independent_fifo_frontier_exhausted reachable=%d",
        len(reached),
    )
    closing_costs = [
        state.cost
        for state in reached.values()
        if _oracle_closes(instance, state, records)
    ]
    minimum_closure_cost = min(closing_costs) if closing_costs else None
    evaluation = OracleEvaluation(
        policy_class=policy_class.value,
        closed=bool(closing_costs),
        minimum_closure_cost=minimum_closure_cost,
        frontier_exhausted=True,
        reachable_state_count=len(reached),
    )
    # Console log P4-ORACLE-03: identify independent oracle evaluation summary.
    LOGGER.info(
        "P4-ORACLE-03 independent_oracle_result closed=%s cost=%s reachable=%d",
        evaluation.closed,
        evaluation.minimum_closure_cost,
        evaluation.reachable_state_count,
    )
    return evaluation


def evaluate_required_oracle_runs(
    canonical: Instance,
    ablation: Instance,
) -> dict[str, OracleEvaluation]:
    """Evaluate FULL_PC(I), FIXED_R(I), and the labeled ablation."""

    # Console log P4-ORACLE-04: identify the three required oracle runs.
    LOGGER.info("P4-ORACLE-04 required_oracle_runs_started")
    results = {
        "full_pc": enumerate_finite_graph(canonical, EvaluatorPolicyClass.FULL_PC),
        "fixed_r": enumerate_finite_graph(canonical, EvaluatorPolicyClass.FIXED_R),
        "ablation_full_pc": enumerate_finite_graph(
            ablation, EvaluatorPolicyClass.FULL_PC
        ),
    }
    # Console log P4-ORACLE-05: identify completion of the required oracle runs.
    LOGGER.info("P4-ORACLE-05 required_oracle_runs_completed")
    return results
