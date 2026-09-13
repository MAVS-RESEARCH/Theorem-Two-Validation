"""Finite complementarity checker domain model and exhaustive evaluator."""

from __future__ import annotations

import argparse
import hashlib
import heapq
import inspect
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from itertools import count
from pathlib import Path
from types import MappingProxyType
from typing import (
    Any,
    Callable,
    Generic,
    Hashable,
    Mapping,
    TypeAlias,
    TypeVar,
)


LOGGER = logging.getLogger("pc_checker")
EXPECTED_ABLATION_STRUCTURAL_DIFF = ("representation_actions[0].enabled",)
REQUIRED_POLICY_VALUES = MappingProxyType(
    {
        "Pi": "retain_hypotheses_consistent_with_represented_admitted_evidence",
        "Pi_eff": "all_declared_actions_have_nonnegative_integer_cost",
        "Pi_epi": "use_only_valid_admitted_evidence",
        "terminal_rule": "close_when_exactly_one_compatible_hypothesis_remains",
    }
)

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
StateT = TypeVar("StateT")
StateKeyT = TypeVar("StateKeyT", bound=Hashable)
EdgeT = TypeVar("EdgeT")


class ValidationError(ValueError):
    """Raised when an instance violates the finite witness contract."""


class RepresentationId(str, Enum):
    """Finite representation identifiers."""

    R0 = "R0"
    R1 = "R1"


class ActionKind(str, Enum):
    """Disjoint action categories."""

    EVIDENCE = "evidence"
    REPRESENTATION = "representation"


class EvaluatorPolicyClass(str, Enum):
    """Action-policy classes evaluated over one canonical PC instance."""

    FULL_PC = "full_pc"
    FIXED_R = "fixed_r"


class CostClassification(str, Enum):
    """Machine-readable closure-cost classification."""

    FINITE = "finite"
    INFINITY = "infinity"


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """One finite world hypothesis."""

    identifier: str
    target_label: str


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """Immutable evidence datum."""

    identifier: str
    valid: bool
    admitted: bool
    target: str
    source: str
    target_label: str | None = None
    value: str | None = None


@dataclass(frozen=True, slots=True)
class Certificate:
    """Certificate target definition."""

    target: str


@dataclass(frozen=True, slots=True)
class Controller:
    """Controller state."""

    identifier: str
    mode: str


@dataclass(frozen=True, slots=True)
class Authority:
    """Epistemic authority definition."""

    identifier: str
    admission_rule: str


@dataclass(frozen=True, slots=True)
class Policy:
    """Complete policy bundle."""

    pi: str
    pi_effective: str
    pi_epistemic: str
    terminal_rule: str


@dataclass(frozen=True, slots=True)
class InitialState:
    """Immutable initial checker state."""

    certificate: Certificate
    representation: RepresentationId
    controller: Controller
    authority: Authority
    admitted_evidence: tuple[str, ...]
    history: tuple[EvidenceRecord, ...]
    cost: int
    rank: int
    depth: int


@dataclass(frozen=True, slots=True)
class EvidenceAction:
    """Typed environmental evidence operation."""

    identifier: str
    kind: ActionKind
    legal_from: tuple[RepresentationId, ...]
    outcomes: tuple[EvidenceRecord, ...]
    cost: int


@dataclass(frozen=True, slots=True)
class RepresentationAction:
    """Typed representation-only operation."""

    identifier: str
    kind: ActionKind
    source: RepresentationId
    destination: RepresentationId
    enabled: bool
    reads: str
    cost: int


Action: TypeAlias = EvidenceAction | RepresentationAction


@dataclass(frozen=True, slots=True)
class RepresentationDefinition:
    """Representation projection declaration."""

    identifier: RepresentationId
    projection: str
    exposes_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Instance:
    """Validated immutable PC instance."""

    schema_version: int
    instance_id: str
    hypotheses: tuple[Hypothesis, ...]
    target_function: str
    initial_state: InitialState
    policy: Policy
    evidence_actions: tuple[EvidenceAction, ...]
    representation_actions: tuple[RepresentationAction, ...]
    representations: tuple[RepresentationDefinition, ...]

    @property
    def actions(self) -> tuple[Action, ...]:
        """Return actions while preserving their disjoint runtime types."""

        return (*self.evidence_actions, *self.representation_actions)


@dataclass(frozen=True, slots=True)
class RepresentedCertificateState:
    """Certificate information visible through a representation."""

    target: str
    represented_target_label: str | None


@dataclass(frozen=True, slots=True)
class ActionPolicyView:
    """Admissible actions for one policy class over a retained instance reference."""

    instance: Instance
    policy_class: EvaluatorPolicyClass
    current_representation: RepresentationId
    actions: tuple[Action, ...]


@dataclass(frozen=True, slots=True)
class SearchState:
    """Finite PC state with semantic and path-local fields."""

    certificate: Certificate
    representation: RepresentationId
    controller: Controller
    authority: Authority
    admitted_evidence: tuple[str, ...]
    history: tuple[EvidenceRecord, ...]
    accumulated_cost: int
    rank: int
    depth: int


@dataclass(frozen=True, slots=True)
class SemanticStateKey:
    """Hashable state identity excluding path-local cost and depth."""

    certificate: Certificate
    representation: RepresentationId
    controller: Controller
    authority: Authority
    admitted_evidence: tuple[str, ...]
    history: tuple[EvidenceRecord, ...]


@dataclass(frozen=True, slots=True)
class SearchTransition:
    """One typed transition on a reconstructed PC path."""

    action_id: str
    action_kind: ActionKind
    action_cost: int
    source_representation: RepresentationId
    destination_representation: RepresentationId
    acquired_evidence: tuple[str, ...]
    cumulative_cost: int
    resulting_rank: int
    resulting_depth: int


@dataclass(frozen=True, slots=True)
class WeightedSuccessor(Generic[StateT, EdgeT]):
    """One deterministic non-negative edge for uniform-cost traversal."""

    state: StateT
    edge: EdgeT
    edge_cost: int
    order_key: str


@dataclass(frozen=True, slots=True)
class UniformCostTraversal(Generic[StateT, EdgeT]):
    """Internal exact result of finite uniform-cost traversal."""

    goal_state: StateT | None
    minimum_cost: int | None
    path: tuple[EdgeT, ...]
    frontier_exhausted: bool
    reachable_state_count: int
    expanded_state_count: int
    stale_queue_entry_count: int
    deduplicated_successor_count: int
    reached_states: tuple[StateT, ...]


@dataclass(frozen=True, slots=True)
class ClosureEvaluation:
    """Closure-cost evaluation under one policy class on one instance."""

    instance: Instance
    instance_fingerprint: str
    policy_class: EvaluatorPolicyClass
    closed: bool
    cost_classification: CostClassification
    minimum_closure_cost: int | None
    path: tuple[SearchTransition, ...]
    closing_state: SearchState | None
    frontier_exhausted: bool
    reachable_state_count: int
    expanded_state_count: int
    stale_queue_entry_count: int
    deduplicated_successor_count: int
    initial_alternatives: tuple[str, ...]
    closing_alternatives: tuple[str, ...] | None
    reached_states: tuple[SearchState, ...]

    @property
    def step_count(self) -> int:
        """Return the number of transitions on the optimal path."""

        return len(self.path)

    @property
    def evidence_acquisition_count(self) -> int:
        """Return newly acquired environmental evidence on the optimal path."""

        return sum(len(step.acquired_evidence) for step in self.path)

    @property
    def representation_repair_count(self) -> int:
        """Return representation transitions on the optimal path."""

        return sum(
            step.action_kind is ActionKind.REPRESENTATION for step in self.path
        )


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{context} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ValidationError(f"{context} keys must be strings")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: set[str], context: str
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValidationError(
            f"{context} has invalid keys; missing={missing}, extra={extra}"
        )


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{context} must be an array")
    return value


def _require_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{context} must be a non-empty string")
    return value


def _require_bool(value: Any, context: str) -> bool:
    if type(value) is not bool:
        raise ValidationError(f"{context} must be a boolean")
    return value


def _require_nonnegative_int(value: Any, context: str) -> int:
    if type(value) is not int or value < 0:
        raise ValidationError(f"{context} must be a non-negative integer")
    return value


def _require_unique(values: tuple[str, ...], context: str) -> None:
    if len(values) != len(set(values)):
        raise ValidationError(f"{context} must contain unique values")


def _parse_representation(value: Any, context: str) -> RepresentationId:
    try:
        return RepresentationId(_require_string(value, context))
    except ValueError as error:
        raise ValidationError(f"{context} must be R0 or R1") from error


def _parse_action_kind(value: Any, context: str) -> ActionKind:
    try:
        return ActionKind(_require_string(value, context))
    except ValueError as error:
        raise ValidationError(
            f"{context} must be evidence or representation"
        ) from error


def _parse_evidence_record(value: Any, context: str) -> EvidenceRecord:
    raw = _require_object(value, context)
    common_keys = {"id", "valid", "admitted", "target", "source"}
    variant_keys = set(raw) - common_keys
    if variant_keys not in ({"target_label"}, {"value"}):
        raise ValidationError(
            f"{context} must contain exactly one of target_label or value"
        )
    _require_exact_keys(raw, common_keys | variant_keys, context)
    return EvidenceRecord(
        identifier=_require_string(raw["id"], f"{context}.id"),
        valid=_require_bool(raw["valid"], f"{context}.valid"),
        admitted=_require_bool(raw["admitted"], f"{context}.admitted"),
        target=_require_string(raw["target"], f"{context}.target"),
        source=_require_string(raw["source"], f"{context}.source"),
        target_label=(
            _require_string(raw["target_label"], f"{context}.target_label")
            if "target_label" in raw
            else None
        ),
        value=(
            _require_string(raw["value"], f"{context}.value")
            if "value" in raw
            else None
        ),
    )


def _parse_instance(raw_value: Any) -> Instance:
    raw = _require_object(raw_value, "instance")
    _require_exact_keys(
        raw,
        {
            "schema_version",
            "instance_id",
            "world",
            "initial_state",
            "policy",
            "evidence_actions",
            "representation_actions",
            "representations",
        },
        "instance",
    )

    world = _require_object(raw["world"], "world")
    _require_exact_keys(world, {"hypotheses", "target_function"}, "world")
    hypotheses: list[Hypothesis] = []
    for index, value in enumerate(_require_list(world["hypotheses"], "world.hypotheses")):
        hypothesis = _require_object(value, f"world.hypotheses[{index}]")
        _require_exact_keys(
            hypothesis, {"id", "target_label"}, f"world.hypotheses[{index}]"
        )
        hypotheses.append(
            Hypothesis(
                _require_string(hypothesis["id"], f"world.hypotheses[{index}].id"),
                _require_string(
                    hypothesis["target_label"],
                    f"world.hypotheses[{index}].target_label",
                ),
            )
        )

    initial = _require_object(raw["initial_state"], "initial_state")
    _require_exact_keys(
        initial,
        {
            "certificate",
            "representation",
            "controller",
            "authority",
            "admitted_evidence",
            "history",
            "cost",
            "rank",
            "depth",
        },
        "initial_state",
    )
    certificate = _require_object(initial["certificate"], "initial_state.certificate")
    _require_exact_keys(certificate, {"target"}, "initial_state.certificate")
    controller = _require_object(initial["controller"], "initial_state.controller")
    _require_exact_keys(controller, {"id", "mode"}, "initial_state.controller")
    authority = _require_object(initial["authority"], "initial_state.authority")
    _require_exact_keys(authority, {"id", "admission_rule"}, "initial_state.authority")
    admitted_evidence = tuple(
        _require_string(value, f"initial_state.admitted_evidence[{index}]")
        for index, value in enumerate(
            _require_list(initial["admitted_evidence"], "initial_state.admitted_evidence")
        )
    )
    history = tuple(
        _parse_evidence_record(value, f"initial_state.history[{index}]")
        for index, value in enumerate(
            _require_list(initial["history"], "initial_state.history")
        )
    )

    policy_raw = _require_object(raw["policy"], "policy")
    _require_exact_keys(policy_raw, set(REQUIRED_POLICY_VALUES), "policy")
    policy = Policy(
        pi=_require_string(policy_raw["Pi"], "policy.Pi"),
        pi_effective=_require_string(policy_raw["Pi_eff"], "policy.Pi_eff"),
        pi_epistemic=_require_string(policy_raw["Pi_epi"], "policy.Pi_epi"),
        terminal_rule=_require_string(
            policy_raw["terminal_rule"], "policy.terminal_rule"
        ),
    )

    evidence_actions: list[EvidenceAction] = []
    for index, value in enumerate(
        _require_list(raw["evidence_actions"], "evidence_actions")
    ):
        context = f"evidence_actions[{index}]"
        action = _require_object(value, context)
        _require_exact_keys(
            action, {"id", "kind", "legal_from", "outcomes", "cost"}, context
        )
        kind = _parse_action_kind(action["kind"], f"{context}.kind")
        if kind is not ActionKind.EVIDENCE:
            raise ValidationError(f"{context}.kind must be evidence")
        evidence_actions.append(
            EvidenceAction(
                identifier=_require_string(action["id"], f"{context}.id"),
                kind=kind,
                legal_from=tuple(
                    _parse_representation(item, f"{context}.legal_from[{item_index}]")
                    for item_index, item in enumerate(
                        _require_list(action["legal_from"], f"{context}.legal_from")
                    )
                ),
                outcomes=tuple(
                    _parse_evidence_record(item, f"{context}.outcomes[{item_index}]")
                    for item_index, item in enumerate(
                        _require_list(action["outcomes"], f"{context}.outcomes")
                    )
                ),
                cost=_require_nonnegative_int(action["cost"], f"{context}.cost"),
            )
        )

    representation_actions: list[RepresentationAction] = []
    for index, value in enumerate(
        _require_list(raw["representation_actions"], "representation_actions")
    ):
        context = f"representation_actions[{index}]"
        action = _require_object(value, context)
        _require_exact_keys(
            action,
            {"id", "kind", "from", "to", "enabled", "reads", "cost"},
            context,
        )
        kind = _parse_action_kind(action["kind"], f"{context}.kind")
        if kind is not ActionKind.REPRESENTATION:
            raise ValidationError(f"{context}.kind must be representation")
        representation_actions.append(
            RepresentationAction(
                identifier=_require_string(action["id"], f"{context}.id"),
                kind=kind,
                source=_parse_representation(action["from"], f"{context}.from"),
                destination=_parse_representation(action["to"], f"{context}.to"),
                enabled=_require_bool(action["enabled"], f"{context}.enabled"),
                reads=_require_string(action["reads"], f"{context}.reads"),
                cost=_require_nonnegative_int(action["cost"], f"{context}.cost"),
            )
        )

    representations_raw = _require_object(raw["representations"], "representations")
    _require_exact_keys(representations_raw, {"R0", "R1"}, "representations")
    representations: list[RepresentationDefinition] = []
    for representation_id in RepresentationId:
        context = f"representations.{representation_id.value}"
        definition = _require_object(
            representations_raw[representation_id.value], context
        )
        _require_exact_keys(definition, {"projection", "exposes_fields"}, context)
        representations.append(
            RepresentationDefinition(
                identifier=representation_id,
                projection=_require_string(
                    definition["projection"], f"{context}.projection"
                ),
                exposes_fields=tuple(
                    _require_string(item, f"{context}.exposes_fields[{item_index}]")
                    for item_index, item in enumerate(
                        _require_list(
                            definition["exposes_fields"], f"{context}.exposes_fields"
                        )
                    )
                ),
            )
        )

    return Instance(
        schema_version=_require_nonnegative_int(
            raw["schema_version"], "schema_version"
        ),
        instance_id=_require_string(raw["instance_id"], "instance_id"),
        hypotheses=tuple(hypotheses),
        target_function=_require_string(
            world["target_function"], "world.target_function"
        ),
        initial_state=InitialState(
            certificate=Certificate(
                _require_string(
                    certificate["target"], "initial_state.certificate.target"
                )
            ),
            representation=_parse_representation(
                initial["representation"], "initial_state.representation"
            ),
            controller=Controller(
                _require_string(controller["id"], "initial_state.controller.id"),
                _require_string(controller["mode"], "initial_state.controller.mode"),
            ),
            authority=Authority(
                _require_string(authority["id"], "initial_state.authority.id"),
                _require_string(
                    authority["admission_rule"],
                    "initial_state.authority.admission_rule",
                ),
            ),
            admitted_evidence=admitted_evidence,
            history=history,
            cost=_require_nonnegative_int(initial["cost"], "initial_state.cost"),
            rank=_require_nonnegative_int(initial["rank"], "initial_state.rank"),
            depth=_require_nonnegative_int(initial["depth"], "initial_state.depth"),
        ),
        policy=policy,
        evidence_actions=tuple(evidence_actions),
        representation_actions=tuple(representation_actions),
        representations=tuple(representations),
    )


def validate_instance(instance: Instance) -> None:
    """Validate all semantic constraints for the canonical finite witness."""

    if instance.schema_version != 1:
        raise ValidationError("schema_version must be 1")
    if len(instance.hypotheses) < 2:
        raise ValidationError("world must contain at least two hypotheses")
    _require_unique(
        tuple(hypothesis.identifier for hypothesis in instance.hypotheses),
        "hypothesis identifiers",
    )
    if instance.target_function != "target_label":
        raise ValidationError("world.target_function must be target_label")
    if len({item.target_label for item in instance.hypotheses}) < 2:
        raise ValidationError("hypotheses must differ on the target label")
    if instance.initial_state.representation is not RepresentationId.R0:
        raise ValidationError("initial representation must be R0")
    if any(
        value != 0
        for value in (
            instance.initial_state.cost,
            instance.initial_state.rank,
            instance.initial_state.depth,
        )
    ):
        raise ValidationError("initial cost, rank, and depth must be zero")
    _require_unique(
        instance.initial_state.admitted_evidence, "initial admitted evidence"
    )
    _require_unique(
        tuple(record.identifier for record in instance.initial_state.history),
        "history evidence identifiers",
    )
    history_by_id = {
        record.identifier: record for record in instance.initial_state.history
    }
    if set(instance.initial_state.admitted_evidence) - set(history_by_id):
        raise ValidationError("every admitted evidence identifier must exist in history")
    for identifier in instance.initial_state.admitted_evidence:
        record = history_by_id[identifier]
        if not record.valid or not record.admitted:
            raise ValidationError("admitted evidence must be valid and marked admitted")
    if "e_star" not in instance.initial_state.admitted_evidence:
        raise ValidationError("e_star must be admitted before intervention")
    e_star = history_by_id["e_star"]
    if (
        e_star.target != instance.initial_state.certificate.target
        or e_star.target_label is None
        or e_star.source != "initial_history"
    ):
        raise ValidationError("e_star must be an initial target-bearing datum")
    actual_policy = {
        "Pi": instance.policy.pi,
        "Pi_eff": instance.policy.pi_effective,
        "Pi_epi": instance.policy.pi_epistemic,
        "terminal_rule": instance.policy.terminal_rule,
    }
    if actual_policy != dict(REQUIRED_POLICY_VALUES):
        raise ValidationError("policy bundle does not implement the declared semantics")
    if not instance.evidence_actions:
        raise ValidationError("at least one evidence action must be declared")
    if len(instance.representation_actions) != 1:
        raise ValidationError("exactly one representation action must be declared")
    action = instance.representation_actions[0]
    if (
        action.identifier != "repair_R0_to_R1"
        or action.source is not RepresentationId.R0
        or action.destination is not RepresentationId.R1
        or action.reads != "admitted_history_only"
        or action.cost != 1
    ):
        raise ValidationError("representation repair contract is invalid")
    representation_by_id = {
        definition.identifier: definition for definition in instance.representations
    }
    if (
        representation_by_id[RepresentationId.R0].projection
        != "alias_target_distinction"
        or representation_by_id[RepresentationId.R0].exposes_fields
    ):
        raise ValidationError("R0 must alias the target distinction")
    if (
        representation_by_id[RepresentationId.R1].projection
        != "expose_admitted_target_label"
        or representation_by_id[RepresentationId.R1].exposes_fields
        != ("target_label",)
    ):
        raise ValidationError("R1 must expose only the admitted target label")
    if len(compatible_hypotheses(instance, RepresentationId.R0)) <= 1:
        raise ValidationError("R0 must remain non-closing")
    if len(compatible_hypotheses(instance, RepresentationId.R1)) != 1:
        raise ValidationError("R1 must close from admitted evidence")


def load_instance(path: Path) -> tuple[dict[str, JsonValue], Instance]:
    """Load raw JSON and return it with an immutable validated domain object."""

    try:
        raw_text = path.read_text(encoding="utf-8")
        raw_value: Any = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"cannot load {path}: {error}") from error
    raw = _require_object(raw_value, str(path))
    instance = _parse_instance(raw)
    validate_instance(instance)
    return raw, instance


def canonical_json(value: Mapping[str, Any]) -> str:
    """Serialize a raw instance canonically without modifying it."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_fingerprint(value: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 fingerprint of canonical JSON."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def structural_diff(left: JsonValue, right: JsonValue, path: str = "") -> tuple[str, ...]:
    """Return every recursively differing path without ignoring any field."""

    if type(left) is not type(right):
        return (path or "$",)
    if isinstance(left, dict) and isinstance(right, dict):
        differences: list[str] = []
        for key in sorted(set(left) | set(right)):
            child_path = f"{path}.{key}" if path else key
            if key not in left or key not in right:
                differences.append(child_path)
            else:
                differences.extend(structural_diff(left[key], right[key], child_path))
        return tuple(differences)
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        for index in range(max(len(left), len(right))):
            child_path = f"{path}[{index}]"
            if index >= len(left) or index >= len(right):
                differences.append(child_path)
            else:
                differences.extend(
                    structural_diff(left[index], right[index], child_path)
                )
        return tuple(differences)
    return () if left == right else (path or "$",)


def validate_ablation_pair(
    canonical_raw: dict[str, JsonValue],
    ablation_raw: dict[str, JsonValue],
    canonical_instance: Instance,
    ablation_instance: Instance,
) -> tuple[str, ...]:
    """Assert the secondary ablation's singleton transition deletion."""

    differences = structural_diff(canonical_raw, ablation_raw)
    if differences != EXPECTED_ABLATION_STRUCTURAL_DIFF:
        raise ValidationError(
            "canonical instance and ablation must differ only at "
            f"{EXPECTED_ABLATION_STRUCTURAL_DIFF[0]}; actual={differences}"
        )
    canonical_action = canonical_instance.representation_actions[0]
    ablation_action = ablation_instance.representation_actions[0]
    if not canonical_action.enabled or ablation_action.enabled:
        raise ValidationError(
            "canonical I must enable repair and the ablation must delete it"
        )
    if canonical_instance.initial_state != ablation_instance.initial_state:
        raise ValidationError("canonical and ablation initial states must be identical")
    return differences


def legal_actions(
    instance: Instance, current_representation: RepresentationId
) -> tuple[Action, ...]:
    """Return actions legal in the unchanged canonical transition relation."""

    evidence_actions = tuple(
        action
        for action in instance.evidence_actions
        if current_representation in action.legal_from
    )
    representation_actions = tuple(
        action
        for action in instance.representation_actions
        if action.enabled and action.source is current_representation
    )
    return (*evidence_actions, *representation_actions)


def successor_representation(
    action: Action, current_representation: RepresentationId
) -> RepresentationId:
    """Return the representation component of T(sigma, action)."""

    if isinstance(action, EvidenceAction):
        return current_representation
    return action.destination


def action_policy_view(
    instance: Instance,
    current_representation: RepresentationId,
    policy_class: EvaluatorPolicyClass,
) -> ActionPolicyView:
    """Project an evaluator policy class without changing the PC instance."""

    actions = legal_actions(instance, current_representation)
    if policy_class is EvaluatorPolicyClass.FIXED_R:
        initial_representation = instance.initial_state.representation
        actions = tuple(
            action
            for action in actions
            if successor_representation(action, current_representation)
            is initial_representation
        )
    return ActionPolicyView(
        instance=instance,
        policy_class=policy_class,
        current_representation=current_representation,
        actions=actions,
    )


def exhaustive_uniform_cost(
    start_state: StateT,
    semantic_key: Callable[[StateT], StateKeyT],
    deterministic_key: Callable[[StateKeyT], str],
    is_goal: Callable[[StateT], bool],
    successors: Callable[[StateT], tuple[WeightedSuccessor[StateT, EdgeT], ...]],
) -> UniformCostTraversal[StateT, EdgeT]:
    """Find the first settled minimum-cost goal and exhaust reachable states."""

    start_key = semantic_key(start_state)
    best_costs: dict[StateKeyT, int] = {start_key: 0}
    states: dict[StateKeyT, StateT] = {start_key: start_state}
    predecessors: dict[StateKeyT, tuple[StateKeyT, EdgeT]] = {}
    sequence = count()
    frontier: list[tuple[int, str, int, StateKeyT]] = [
        (0, deterministic_key(start_key), next(sequence), start_key)
    ]
    expanded_state_count = 0
    stale_queue_entry_count = 0
    deduplicated_successor_count = 0
    minimum_goal_key: StateKeyT | None = None
    minimum_goal_state: StateT | None = None
    minimum_goal_cost: int | None = None

    while frontier:
        current_cost, _, _, current_key = heapq.heappop(frontier)
        if current_cost != best_costs[current_key]:
            stale_queue_entry_count += 1
            continue
        current_state = states[current_key]
        expanded_state_count += 1
        if minimum_goal_key is None and is_goal(current_state):
            minimum_goal_key = current_key
            minimum_goal_state = current_state
            minimum_goal_cost = current_cost

        ordered_successors = sorted(
            successors(current_state),
            key=lambda item: (
                item.order_key,
                deterministic_key(semantic_key(item.state)),
            ),
        )
        for candidate in ordered_successors:
            if type(candidate.edge_cost) is not int or candidate.edge_cost < 0:
                raise ValidationError(
                    "uniform-cost traversal requires non-negative integer edge costs"
                )
            candidate_key = semantic_key(candidate.state)
            candidate_cost = current_cost + candidate.edge_cost
            prior_cost = best_costs.get(candidate_key)
            if prior_cost is not None and candidate_cost >= prior_cost:
                deduplicated_successor_count += 1
                continue
            best_costs[candidate_key] = candidate_cost
            states[candidate_key] = candidate.state
            predecessors[candidate_key] = (current_key, candidate.edge)
            heapq.heappush(
                frontier,
                (
                    candidate_cost,
                    deterministic_key(candidate_key),
                    next(sequence),
                    candidate_key,
                ),
            )

    reverse_path: list[EdgeT] = []
    if minimum_goal_key is not None:
        path_key = minimum_goal_key
        while path_key in predecessors:
            previous_key, edge = predecessors[path_key]
            reverse_path.append(edge)
            path_key = previous_key
    return UniformCostTraversal(
        goal_state=minimum_goal_state,
        minimum_cost=minimum_goal_cost,
        path=tuple(reversed(reverse_path)),
        frontier_exhausted=True,
        reachable_state_count=len(best_costs),
        expanded_state_count=expanded_state_count,
        stale_queue_entry_count=stale_queue_entry_count,
        deduplicated_successor_count=deduplicated_successor_count,
        reached_states=tuple(
            states[key] for key in sorted(states, key=deterministic_key)
        ),
    )


def initial_search_state(instance: Instance) -> SearchState:
    """Materialize the canonical initial state for graph traversal."""

    initial = instance.initial_state
    return SearchState(
        certificate=initial.certificate,
        representation=initial.representation,
        controller=initial.controller,
        authority=initial.authority,
        admitted_evidence=initial.admitted_evidence,
        history=initial.history,
        accumulated_cost=initial.cost,
        rank=initial.rank,
        depth=initial.depth,
    )


def semantic_state_key(state: SearchState) -> SemanticStateKey:
    """Exclude path-local fields while preserving all future-relevant state."""

    return SemanticStateKey(
        certificate=state.certificate,
        representation=state.representation,
        controller=state.controller,
        authority=state.authority,
        admitted_evidence=state.admitted_evidence,
        history=state.history,
    )


def semantic_state_order_key(key: SemanticStateKey) -> str:
    """Return a stable total-order key for deterministic queue ties."""

    return json.dumps(
        {
            "certificate": key.certificate.target,
            "representation": key.representation.value,
            "controller": [key.controller.identifier, key.controller.mode],
            "authority": [key.authority.identifier, key.authority.admission_rule],
            "admitted_evidence": list(key.admitted_evidence),
            "history": [
                {
                    "id": record.identifier,
                    "valid": record.valid,
                    "admitted": record.admitted,
                    "target": record.target,
                    "source": record.source,
                    "target_label": record.target_label,
                    "value": record.value,
                }
                for record in key.history
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def apply_evidence_action(
    state: SearchState, action: EvidenceAction
) -> tuple[SearchState, SearchTransition]:
    """Apply one environmental action while canonicalizing finite evidence."""

    history_by_id = {record.identifier: record for record in state.history}
    acquired_evidence: list[str] = []
    for outcome in action.outcomes:
        existing = history_by_id.get(outcome.identifier)
        if existing is not None and existing != outcome:
            raise ValidationError(
                f"evidence outcome {outcome.identifier} conflicts with history"
            )
        if existing is None:
            history_by_id[outcome.identifier] = outcome
            if outcome.source == "environment":
                acquired_evidence.append(outcome.identifier)
    admitted = set(state.admitted_evidence)
    admitted.update(
        outcome.identifier
        for outcome in action.outcomes
        if outcome.valid and outcome.admitted
    )
    cumulative_cost = state.accumulated_cost + action.cost
    successor = SearchState(
        certificate=state.certificate,
        representation=state.representation,
        controller=state.controller,
        authority=state.authority,
        admitted_evidence=tuple(sorted(admitted)),
        history=tuple(
            history_by_id[identifier] for identifier in sorted(history_by_id)
        ),
        accumulated_cost=cumulative_cost,
        rank=state.rank + 1,
        depth=state.depth + 1,
    )
    transition = SearchTransition(
        action_id=action.identifier,
        action_kind=action.kind,
        action_cost=action.cost,
        source_representation=state.representation,
        destination_representation=successor.representation,
        acquired_evidence=tuple(sorted(acquired_evidence)),
        cumulative_cost=cumulative_cost,
        resulting_rank=successor.rank,
        resulting_depth=successor.depth,
    )
    return successor, transition


def apply_representation_action(
    state: SearchState, action: RepresentationAction
) -> tuple[SearchState, SearchTransition]:
    """Apply representation repair without acquiring environmental evidence."""

    cumulative_cost = state.accumulated_cost + action.cost
    successor = SearchState(
        certificate=state.certificate,
        representation=action.destination,
        controller=state.controller,
        authority=state.authority,
        admitted_evidence=state.admitted_evidence,
        history=state.history,
        accumulated_cost=cumulative_cost,
        rank=state.rank + 1,
        depth=state.depth + 1,
    )
    transition = SearchTransition(
        action_id=action.identifier,
        action_kind=action.kind,
        action_cost=action.cost,
        source_representation=state.representation,
        destination_representation=successor.representation,
        acquired_evidence=(),
        cumulative_cost=cumulative_cost,
        resulting_rank=successor.rank,
        resulting_depth=successor.depth,
    )
    return successor, transition


def pc_successors(
    instance: Instance,
    state: SearchState,
    policy_class: EvaluatorPolicyClass,
) -> tuple[WeightedSuccessor[SearchState, SearchTransition], ...]:
    """Generate typed legal successors under one evaluator policy class."""

    policy_view = action_policy_view(
        instance, state.representation, policy_class
    )
    generated: list[WeightedSuccessor[SearchState, SearchTransition]] = []
    for action in policy_view.actions:
        if isinstance(action, EvidenceAction):
            successor, transition = apply_evidence_action(state, action)
        else:
            successor, transition = apply_representation_action(state, action)
        generated.append(
            WeightedSuccessor(
                state=successor,
                edge=transition,
                edge_cost=action.cost,
                order_key=f"{action.kind.value}:{action.identifier}",
            )
        )
    return tuple(generated)


def compatible_hypotheses_for_state(
    instance: Instance, state: SearchState
) -> tuple[str, ...]:
    """Evaluate closure from the represented evidence in a search state."""

    if state.representation is RepresentationId.R0:
        represented_target_label = None
    else:
        admitted = set(state.admitted_evidence)
        labels = {
            record.target_label
            for record in state.history
            if record.identifier in admitted
            and record.valid
            and record.admitted
            and record.target == state.certificate.target
            and record.target_label is not None
        }
        if len(labels) != 1:
            raise ValidationError(
                "R1 requires exactly one admitted target label in search state"
            )
        represented_target_label = next(iter(labels))
    return tuple(
        hypothesis.identifier
        for hypothesis in instance.hypotheses
        if represented_target_label is None
        or hypothesis.target_label == represented_target_label
    )


def evaluate_closure(
    instance: Instance,
    instance_fingerprint: str,
    policy_class: EvaluatorPolicyClass,
) -> ClosureEvaluation:
    """Compute exact closure cost under one policy class."""

    start_state = initial_search_state(instance)
    traversal = exhaustive_uniform_cost(
        start_state=start_state,
        semantic_key=semantic_state_key,
        deterministic_key=semantic_state_order_key,
        is_goal=lambda state: (
            len(compatible_hypotheses_for_state(instance, state)) == 1
        ),
        successors=lambda state: pc_successors(instance, state, policy_class),
    )
    closing_alternatives = (
        compatible_hypotheses_for_state(instance, traversal.goal_state)
        if traversal.goal_state is not None
        else None
    )
    return ClosureEvaluation(
        instance=instance,
        instance_fingerprint=instance_fingerprint,
        policy_class=policy_class,
        closed=traversal.goal_state is not None,
        cost_classification=(
            CostClassification.FINITE
            if traversal.goal_state is not None
            else CostClassification.INFINITY
        ),
        minimum_closure_cost=traversal.minimum_cost,
        path=traversal.path,
        closing_state=traversal.goal_state,
        frontier_exhausted=traversal.frontier_exhausted,
        reachable_state_count=traversal.reachable_state_count,
        expanded_state_count=traversal.expanded_state_count,
        stale_queue_entry_count=traversal.stale_queue_entry_count,
        deduplicated_successor_count=traversal.deduplicated_successor_count,
        initial_alternatives=compatible_hypotheses_for_state(instance, start_state),
        closing_alternatives=closing_alternatives,
        reached_states=traversal.reached_states,
    )


def project_certificate(
    instance: Instance, representation: RepresentationId
) -> RepresentedCertificateState:
    """Project only already-admitted history; never acquire environmental evidence."""

    target = instance.initial_state.certificate.target
    if representation is RepresentationId.R0:
        return RepresentedCertificateState(target, None)
    admitted = set(instance.initial_state.admitted_evidence)
    labels = {
        record.target_label
        for record in instance.initial_state.history
        if record.identifier in admitted
        and record.valid
        and record.admitted
        and record.target == target
        and record.target_label is not None
    }
    if len(labels) != 1:
        raise ValidationError(
            "R1 requires exactly one admitted target label in initial history"
        )
    return RepresentedCertificateState(target, next(iter(labels)))


def compatible_hypotheses(
    instance: Instance, representation: RepresentationId
) -> tuple[str, ...]:
    """Evaluate A_Pi(C^R) under the declared policy."""

    represented = project_certificate(instance, representation)
    return tuple(
        hypothesis.identifier
        for hypothesis in instance.hypotheses
        if represented.represented_target_label is None
        or hypothesis.target_label == represented.represented_target_label
    )


def validate_phase_one(
    canonical_path: Path, ablation_path: Path
) -> dict[str, JsonValue]:
    """Run the complete Phase 1 contract and return deterministic evidence."""

    # Console log P1-01: identify the start of Phase 1 validation.
    LOGGER.info("P1-01 phase_one_validation_started")
    # Console log P1-02: identify loading canonical instance I.
    LOGGER.info("P1-02 loading_canonical_instance path=%s", canonical_path)
    canonical_raw, canonical_instance = load_instance(canonical_path)
    # Console log P1-03: identify strict validation of canonical instance I.
    LOGGER.info("P1-03 canonical_instance_validation_passed")
    canonical_before = canonical_json(canonical_raw)
    full_view = action_policy_view(
        canonical_instance,
        canonical_instance.initial_state.representation,
        EvaluatorPolicyClass.FULL_PC,
    )
    # Console log P1-04: identify full-PC action projection on canonical I.
    LOGGER.info("P1-04 full_pc_action_projection count=%d", len(full_view.actions))
    fixed_view = action_policy_view(
        canonical_instance,
        canonical_instance.initial_state.representation,
        EvaluatorPolicyClass.FIXED_R,
    )
    # Console log P1-05: identify fixed-R action projection on canonical I.
    LOGGER.info("P1-05 fixed_r_action_projection count=%d", len(fixed_view.actions))
    if full_view.instance is not fixed_view.instance:
        raise ValidationError("primary policy classes must share one instance object")
    full_action_ids = tuple(action.identifier for action in full_view.actions)
    fixed_action_ids = tuple(action.identifier for action in fixed_view.actions)
    full_evidence_ids = tuple(
        action.identifier
        for action in full_view.actions
        if isinstance(action, EvidenceAction)
    )
    fixed_evidence_ids = tuple(
        action.identifier
        for action in fixed_view.actions
        if isinstance(action, EvidenceAction)
    )
    full_representation_ids = tuple(
        action.identifier
        for action in full_view.actions
        if isinstance(action, RepresentationAction)
    )
    fixed_representation_ids = tuple(
        action.identifier
        for action in fixed_view.actions
        if isinstance(action, RepresentationAction)
    )
    if full_evidence_ids != fixed_evidence_ids:
        raise ValidationError("fixed R must retain representation-preserving evidence actions")
    if full_representation_ids != ("repair_R0_to_R1",):
        raise ValidationError("full PC must admit the canonical representation repair")
    if fixed_representation_ids:
        raise ValidationError("fixed R must exclude representation-changing actions")
    if canonical_json(canonical_raw) != canonical_before:
        raise ValidationError("policy projection mutated the canonical raw instance")
    if not canonical_instance.representation_actions[0].enabled:
        raise ValidationError("canonical transition relation must retain legal repair")
    # Console log P1-06: identify same-instance policy restriction.
    LOGGER.info("P1-06 same_instance_policy_restriction_passed")
    # Console log P1-07: identify loading the secondary ablation instance.
    LOGGER.info("P1-07 loading_ablation_instance path=%s", ablation_path)
    ablation_raw, ablation_instance = load_instance(ablation_path)
    # Console log P1-08: identify strict validation of the ablation instance.
    LOGGER.info("P1-08 ablation_instance_validation_passed")
    differences = validate_ablation_pair(
        canonical_raw,
        ablation_raw,
        canonical_instance,
        ablation_instance,
    )
    # Console log P1-09: identify the secondary ablation structural diff.
    LOGGER.info("P1-09 ablation_structural_diff_passed paths=%s", differences)
    r0_alternatives = compatible_hypotheses(
        canonical_instance, RepresentationId.R0
    )
    # Console log P1-10: identify the R0 non-closure semantic check.
    LOGGER.info(
        "P1-10 r0_non_closure_passed alternative_count=%d",
        len(r0_alternatives),
    )
    r1_alternatives = compatible_hypotheses(
        canonical_instance, RepresentationId.R1
    )
    # Console log P1-11: identify the R1 closure semantic check.
    LOGGER.info(
        "P1-11 r1_closure_passed alternative_count=%d",
        len(r1_alternatives),
    )
    if canonical_instance.initial_state.history != ablation_instance.initial_state.history:
        raise ValidationError("history changed in the secondary ablation")
    if (
        canonical_instance.initial_state.admitted_evidence
        != ablation_instance.initial_state.admitted_evidence
    ):
        raise ValidationError("admitted evidence changed in the secondary ablation")
    # Console log P1-12: identify unchanged ablation history and admitted evidence.
    LOGGER.info("P1-12 ablation_admitted_history_invariant_passed")
    canonical_instance_sha256 = canonical_fingerprint(canonical_raw)
    evidence: dict[str, JsonValue] = {
        "canonical_instance": "instance_plus.json",
        "canonical_instance_sha256": canonical_instance_sha256,
        "full_pc_instance_sha256": canonical_instance_sha256,
        "fixed_r_instance_sha256": canonical_instance_sha256,
        "primary_same_instance_fingerprint": True,
        "canonical_instance_valid": True,
        "canonical_transition_repair_enabled": (
            canonical_instance.representation_actions[0].enabled
        ),
        "primary_same_instance_object": full_view.instance is fixed_view.instance,
        "primary_same_initial_state_object": (
            full_view.instance.initial_state is fixed_view.instance.initial_state
        ),
        "primary_same_policy_object": (
            full_view.instance.policy is fixed_view.instance.policy
        ),
        "primary_same_transition_relation_object": (
            full_view.instance.representation_actions
            is fixed_view.instance.representation_actions
        ),
        "full_pc_admissible_actions": list(full_action_ids),
        "fixed_r_admissible_actions": list(fixed_action_ids),
        "fixed_r_excluded_actions": sorted(set(full_action_ids) - set(fixed_action_ids)),
        "canonical_instance_unchanged_by_policy_projection": (
            canonical_json(canonical_raw) == canonical_before
        ),
        "ablation_instance_valid": True,
        "ablation_structural_diff": list(differences),
        "r0_alternatives": list(r0_alternatives),
        "r0_closes": len(r0_alternatives) == 1,
        "r1_alternatives": list(r1_alternatives),
        "r1_closes": len(r1_alternatives) == 1,
        "ablation_history_unchanged": True,
        "ablation_admitted_evidence_unchanged": True,
        "e_star_pre_admitted": (
            "e_star" in canonical_instance.initial_state.admitted_evidence
        ),
        "canonical_round_trip_stable": (
            json.loads(canonical_json(canonical_raw)) == canonical_raw
            and json.loads(canonical_json(ablation_raw)) == ablation_raw
        ),
    }
    # Console log P1-13: identify successful completion of all Phase 1 gates.
    LOGGER.info("P1-13 phase_one_validation_completed")
    return evidence


def transition_to_json(transition: SearchTransition) -> dict[str, JsonValue]:
    """Normalize one path transition for deterministic comparison."""

    return {
        "action_id": transition.action_id,
        "action_kind": transition.action_kind.value,
        "action_cost": transition.action_cost,
        "source_representation": transition.source_representation.value,
        "destination_representation": transition.destination_representation.value,
        "acquired_evidence": list(transition.acquired_evidence),
        "cumulative_cost": transition.cumulative_cost,
        "resulting_rank": transition.resulting_rank,
        "resulting_depth": transition.resulting_depth,
    }


def evaluation_to_json(evaluation: ClosureEvaluation) -> dict[str, JsonValue]:
    """Normalize one closure evaluation without process-specific identity data."""

    initial_view = action_policy_view(
        evaluation.instance,
        evaluation.instance.initial_state.representation,
        evaluation.policy_class,
    )
    full_view = action_policy_view(
        evaluation.instance,
        evaluation.instance.initial_state.representation,
        EvaluatorPolicyClass.FULL_PC,
    )
    admitted_actions = [action.identifier for action in initial_view.actions]
    full_actions = [action.identifier for action in full_view.actions]
    excluded_actions = sorted(set(full_actions) - set(admitted_actions))
    closing_alternatives = (
        list(evaluation.closing_alternatives)
        if evaluation.closing_alternatives is not None
        else None
    )
    return {
        "instance_fingerprint": evaluation.instance_fingerprint,
        "policy_class": evaluation.policy_class.value,
        "closed": evaluation.closed,
        "cost_classification": evaluation.cost_classification.value,
        "minimum_closure_cost": evaluation.minimum_closure_cost,
        "steps": evaluation.step_count,
        "path": [transition_to_json(step) for step in evaluation.path],
        "closing_state": (
            {
                "representation": evaluation.closing_state.representation.value,
                "accumulated_cost": evaluation.closing_state.accumulated_cost,
                "rank": evaluation.closing_state.rank,
                "depth": evaluation.closing_state.depth,
                "admitted_evidence": list(
                    evaluation.closing_state.admitted_evidence
                ),
                "history": [
                    record.identifier for record in evaluation.closing_state.history
                ],
            }
            if evaluation.closing_state is not None
            else None
        ),
        "evidence_acquisitions": evaluation.evidence_acquisition_count,
        "representation_repairs": evaluation.representation_repair_count,
        "reachable_state_count": evaluation.reachable_state_count,
        "expanded_state_count": evaluation.expanded_state_count,
        "explored_state_count": evaluation.expanded_state_count,
        "stale_queue_entry_count": evaluation.stale_queue_entry_count,
        "deduplicated_successor_count": evaluation.deduplicated_successor_count,
        "frontier_exhausted": evaluation.frontier_exhausted,
        "initial_alternatives": list(evaluation.initial_alternatives),
        "initial_alternative_count": len(evaluation.initial_alternatives),
        "closing_alternatives": closing_alternatives,
        "closing_alternative_count": (
            None if closing_alternatives is None else len(closing_alternatives)
        ),
        "initial_admitted_actions": admitted_actions,
        "initial_admitted_action_count": len(admitted_actions),
        "initial_excluded_actions": excluded_actions,
        "initial_excluded_action_count": len(excluded_actions),
        "reached_representations": sorted(
            {state.representation.value for state in evaluation.reached_states}
        ),
    }


def validate_phase_two(
    canonical_path: Path, ablation_path: Path
) -> dict[str, JsonValue]:
    """Run exhaustive same-instance theorem and secondary ablation evaluations."""

    # Console log P2-01: identify the start of Phase 2 evaluation.
    LOGGER.info("P2-01 phase_two_evaluation_started")
    canonical_raw, canonical_instance = load_instance(canonical_path)
    canonical_instance_sha256 = canonical_fingerprint(canonical_raw)
    canonical_before = canonical_json(canonical_raw)
    # Console log P2-02: identify canonical instance loading.
    LOGGER.info(
        "P2-02 canonical_instance_loaded fingerprint=%s",
        canonical_instance_sha256,
    )
    ablation_raw, ablation_instance = load_instance(ablation_path)
    ablation_instance_sha256 = canonical_fingerprint(ablation_raw)
    # Console log P2-03: identify secondary ablation loading.
    LOGGER.info(
        "P2-03 ablation_instance_loaded fingerprint=%s",
        ablation_instance_sha256,
    )
    ablation_differences = validate_ablation_pair(
        canonical_raw,
        ablation_raw,
        canonical_instance,
        ablation_instance,
    )
    # Console log P2-04: identify validation of the ablation boundary.
    LOGGER.info(
        "P2-04 ablation_contract_validated paths=%s",
        ablation_differences,
    )
    # Console log P2-05: identify full-PC search start on canonical I.
    LOGGER.info("P2-05 full_pc_search_started")
    full_evaluation = evaluate_closure(
        canonical_instance,
        canonical_instance_sha256,
        EvaluatorPolicyClass.FULL_PC,
    )
    # Console log P2-06: identify full-PC search completion.
    LOGGER.info(
        "P2-06 full_pc_search_completed closed=%s cost=%s reachable=%d expanded=%d",
        full_evaluation.closed,
        full_evaluation.minimum_closure_cost,
        full_evaluation.reachable_state_count,
        full_evaluation.expanded_state_count,
    )
    # Console log P2-07: identify fixed-R search start on the same canonical I.
    LOGGER.info("P2-07 fixed_r_search_started")
    fixed_evaluation = evaluate_closure(
        canonical_instance,
        canonical_instance_sha256,
        EvaluatorPolicyClass.FIXED_R,
    )
    # Console log P2-08: identify fixed-R search completion by exhaustion.
    LOGGER.info(
        "P2-08 fixed_r_search_completed closed=%s exhausted=%s reachable=%d expanded=%d",
        fixed_evaluation.closed,
        fixed_evaluation.frontier_exhausted,
        fixed_evaluation.reachable_state_count,
        fixed_evaluation.expanded_state_count,
    )
    if full_evaluation.instance is not fixed_evaluation.instance:
        raise ValidationError("primary evaluations must use the same instance object")
    if (
        full_evaluation.instance.initial_state
        is not fixed_evaluation.instance.initial_state
        or full_evaluation.instance.policy is not fixed_evaluation.instance.policy
        or full_evaluation.instance.evidence_actions
        is not fixed_evaluation.instance.evidence_actions
        or full_evaluation.instance.representation_actions
        is not fixed_evaluation.instance.representation_actions
    ):
        raise ValidationError(
            "primary evaluations must share initial state, policy, and transition data"
        )
    if full_evaluation.instance_fingerprint != fixed_evaluation.instance_fingerprint:
        raise ValidationError("primary instance fingerprints must be identical")
    if canonical_json(canonical_raw) != canonical_before:
        raise ValidationError("primary evaluations mutated canonical instance data")
    # Console log P2-09: identify same-instance primary-run proof.
    LOGGER.info("P2-09 same_instance_primary_comparison_validated")
    # Console log P2-10: identify full-PC ablation search start.
    LOGGER.info("P2-10 secondary_ablation_search_started")
    ablation_evaluation = evaluate_closure(
        ablation_instance,
        ablation_instance_sha256,
        EvaluatorPolicyClass.FULL_PC,
    )
    # Console log P2-11: identify ablation search completion.
    LOGGER.info(
        "P2-11 secondary_ablation_search_completed closed=%s exhausted=%s",
        ablation_evaluation.closed,
        ablation_evaluation.frontier_exhausted,
    )
    if (
        not full_evaluation.closed
        or full_evaluation.minimum_closure_cost != 1
        or full_evaluation.cost_classification is not CostClassification.FINITE
        or full_evaluation.step_count != 1
        or full_evaluation.evidence_acquisition_count != 0
        or full_evaluation.representation_repair_count != 1
        or full_evaluation.path[0].action_id != "repair_R0_to_R1"
        or full_evaluation.path[0].destination_representation
        is not RepresentationId.R1
        or full_evaluation.closing_alternatives != ("w_target_present",)
        or full_evaluation.closing_state is None
        or full_evaluation.closing_state.history
        != canonical_instance.initial_state.history
        or full_evaluation.closing_state.admitted_evidence
        != canonical_instance.initial_state.admitted_evidence
        or full_evaluation.closing_state.controller
        is not canonical_instance.initial_state.controller
        or full_evaluation.closing_state.authority
        is not canonical_instance.initial_state.authority
        or full_evaluation.closing_state.accumulated_cost != 1
        or full_evaluation.closing_state.rank != 1
        or full_evaluation.closing_state.depth != 1
    ):
        raise ValidationError("full-PC theorem assertions failed")
    # Console log P2-12: identify kappa_Pi(I)=1 theorem assertion.
    LOGGER.info("P2-12 full_pc_theorem_assertions_passed")
    if (
        fixed_evaluation.closed
        or fixed_evaluation.minimum_closure_cost is not None
        or fixed_evaluation.cost_classification is not CostClassification.INFINITY
        or not fixed_evaluation.frontier_exhausted
        or any(
            state.representation is not RepresentationId.R0
            for state in fixed_evaluation.reached_states
        )
        or not any(
            "e_aux" in state.admitted_evidence
            for state in fixed_evaluation.reached_states
        )
    ):
        raise ValidationError("fixed-R theorem assertions failed")
    # Console log P2-13: identify kappa_Pi_fixR(I)=infinity assertion.
    LOGGER.info("P2-13 fixed_r_theorem_assertions_passed")
    if (
        ablation_evaluation.instance is canonical_instance
        or ablation_evaluation.closed
        or ablation_evaluation.minimum_closure_cost is not None
        or ablation_evaluation.cost_classification
        is not CostClassification.INFINITY
        or not ablation_evaluation.frontier_exhausted
        or not any(
            "e_aux" in state.admitted_evidence
            for state in ablation_evaluation.reached_states
        )
    ):
        raise ValidationError("secondary ablation assertions failed")
    # Console log P2-14: identify secondary ablation assertion.
    LOGGER.info("P2-14 secondary_ablation_assertions_passed")
    phase_two_result: dict[str, JsonValue] = {
        "primary_comparison": {
            "canonical_instance": "instance_plus.json",
            "canonical_instance_sha256": canonical_instance_sha256,
            "same_instance_object": (
                full_evaluation.instance is fixed_evaluation.instance
            ),
            "same_initial_state_object": (
                full_evaluation.instance.initial_state
                is fixed_evaluation.instance.initial_state
            ),
            "same_policy_object": (
                full_evaluation.instance.policy is fixed_evaluation.instance.policy
            ),
            "same_transition_relation_object": (
                full_evaluation.instance.evidence_actions
                is fixed_evaluation.instance.evidence_actions
                and full_evaluation.instance.representation_actions
                is fixed_evaluation.instance.representation_actions
            ),
            "same_instance_fingerprint": (
                full_evaluation.instance_fingerprint
                == fixed_evaluation.instance_fingerprint
            ),
            "canonical_instance_unchanged": (
                canonical_json(canonical_raw) == canonical_before
            ),
            "full_pc": evaluation_to_json(full_evaluation),
            "fixed_r": evaluation_to_json(fixed_evaluation),
        },
        "secondary_ablation": {
            "role": "transition_deletion_corroboration_only",
            "instance": "instance_minus.json",
            "instance_sha256": ablation_instance_sha256,
            "structural_diff": list(ablation_differences),
            "full_pc": evaluation_to_json(ablation_evaluation),
        },
        "theorem_assertions": {
            "kappa_pi_I_equals_1": True,
            "kappa_pi_fix_r_I_is_infinity": True,
            "same_canonical_instance_for_primary_runs": True,
            "optimal_path_representation_repairs": 1,
            "optimal_path_environmental_evidence_acquisitions": 0,
            "closure_after_R0_to_R1": True,
            "representation_repair_preserved_nonrepresentation_state": True,
            "fixed_r_frontier_exhausted": True,
            "fixed_r_evidence_operation_exhaustively_traversed": True,
            "ablation_is_secondary_only": True,
            "ablation_evidence_operation_exhaustively_traversed": True,
        },
    }
    # Console log P2-15: identify completion of the Phase 2 theorem evaluation.
    LOGGER.info("P2-15 phase_two_evaluation_completed")
    return phase_two_result


REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_CANONICAL_PATH = REPOSITORY_ROOT / "instance_plus.json"
DEFAULT_ABLATION_PATH = REPOSITORY_ROOT / "instance_minus.json"
DEFAULT_RESULT_PATH = REPOSITORY_ROOT / "result.json"
DEFAULT_README_PATH = REPOSITORY_ROOT / "README.md"
REPRODUCTION_COMMAND = "python checker.py"


def _require_invariant(condition: bool, message: str) -> bool:
    """Fail closed when a required causal invariant is false."""

    if not condition:
        raise ValidationError(message)
    return True


def evaluate_pre_intervention_causal_invariants(
    canonical: Instance,
    ablation: Instance,
) -> dict[str, JsonValue]:
    """Validate and log every pre-intervention causal invariant before search."""

    # Console log P3-03: identify start of pre-intervention causal checks before search.
    LOGGER.info("P3-03 pre_intervention_causal_invariants_started")
    history_by_id = {
        record.identifier: record for record in canonical.initial_state.history
    }
    e_star = history_by_id.get("e_star")
    e_star_present = _require_invariant(
        e_star is not None, "e_star must exist in canonical initial history"
    )
    assert e_star is not None
    e_star_in_admitted = _require_invariant(
        "e_star" in canonical.initial_state.admitted_evidence,
        "e_star must be admitted before intervention",
    )
    e_star_valid = _require_invariant(
        e_star.valid, "e_star must be valid before intervention"
    )
    e_star_admitted_flag = _require_invariant(
        e_star.admitted, "e_star must be marked admitted"
    )
    e_star_target_bearing = _require_invariant(
        e_star.target == canonical.initial_state.certificate.target
        and e_star.target_label is not None
        and e_star.source == "initial_history",
        "e_star must be the initial target-bearing datum",
    )
    history_identical = _require_invariant(
        canonical.initial_state.history == ablation.initial_state.history,
        "canonical and ablation initial histories must be identical",
    )
    admitted_identical = _require_invariant(
        canonical.initial_state.admitted_evidence
        == ablation.initial_state.admitted_evidence,
        "canonical and ablation admitted evidence must be identical",
    )
    # Console log P3-04: identify evidence and history invariant checks.
    LOGGER.info(
        "P3-04 evidence_history_invariants_passed e_star_present=%s admitted=%s",
        e_star_present,
        e_star_in_admitted,
    )
    evidence_actions_identical = _require_invariant(
        canonical.evidence_actions == ablation.evidence_actions,
        "evidence action definitions must be identical",
    )
    evidence_outcomes_identical = _require_invariant(
        tuple(action.outcomes for action in canonical.evidence_actions)
        == tuple(action.outcomes for action in ablation.evidence_actions),
        "evidence action outcomes must be identical",
    )
    evidence_costs_identical = _require_invariant(
        tuple(action.cost for action in canonical.evidence_actions)
        == tuple(action.cost for action in ablation.evidence_actions),
        "evidence action costs must be identical",
    )
    repair_costs_identical = _require_invariant(
        canonical.representation_actions[0].cost
        == ablation.representation_actions[0].cost,
        "representation repair costs must be identical",
    )
    all_costs_nonnegative = _require_invariant(
        all(action.cost >= 0 for action in canonical.actions)
        and all(action.cost >= 0 for action in ablation.actions),
        "all declared action costs must be non-negative",
    )
    # Console log P3-05: identify evidence-action definition, outcome, and cost checks.
    LOGGER.info("P3-05 evidence_action_definition_outcome_cost_invariants_passed")
    controller_present = _require_invariant(
        canonical.initial_state.controller.identifier == "M0",
        "canonical controller must be present",
    )
    controller_identical = _require_invariant(
        canonical.initial_state.controller == ablation.initial_state.controller,
        "controller state must be identical",
    )
    # Console log P3-06: identify controller invariant check.
    LOGGER.info("P3-06 controller_invariant_passed")
    authority_present = _require_invariant(
        canonical.initial_state.authority.identifier == "epistemic_authority_0",
        "canonical authority must be present",
    )
    authority_identical = _require_invariant(
        canonical.initial_state.authority == ablation.initial_state.authority,
        "epistemic authority must be identical",
    )
    # Console log P3-07: identify authority invariant check.
    LOGGER.info("P3-07 authority_invariant_passed")
    actual_policy = {
        "Pi": canonical.policy.pi,
        "Pi_eff": canonical.policy.pi_effective,
        "Pi_epi": canonical.policy.pi_epistemic,
        "terminal_rule": canonical.policy.terminal_rule,
    }
    policy_matches_contract = _require_invariant(
        actual_policy == dict(REQUIRED_POLICY_VALUES),
        "canonical policy bundle must match the declared contract",
    )
    policy_identical = _require_invariant(
        canonical.policy == ablation.policy,
        "policy bundle must be identical",
    )
    # Console log P3-08: identify Pi, Pi_eff, Pi_epi, and terminal-rule checks.
    LOGGER.info("P3-08 policy_bundle_invariants_passed")
    distinct_target_labels = _require_invariant(
        len({item.target_label for item in canonical.hypotheses}) >= 2,
        "world hypotheses must differ on the target",
    )
    hypotheses_identical = _require_invariant(
        canonical.hypotheses == ablation.hypotheses,
        "world hypotheses must be identical",
    )
    target_function_identical = _require_invariant(
        canonical.target_function == ablation.target_function
        and canonical.target_function == "target_label",
        "world target function must be identical",
    )
    # Console log P3-09: identify world and target-function invariant checks.
    LOGGER.info("P3-09 world_and_target_function_invariants_passed")
    initial_representation_r0 = _require_invariant(
        canonical.initial_state.representation is RepresentationId.R0,
        "canonical initial representation must be R0",
    )
    initial_representation_identical = _require_invariant(
        canonical.initial_state.representation
        == ablation.initial_state.representation,
        "initial representation must be identical",
    )
    # Console log P3-10: identify initial-representation invariant check.
    LOGGER.info("P3-10 initial_representation_invariant_passed")
    initial_cost_zero = _require_invariant(
        canonical.initial_state.cost == 0 and ablation.initial_state.cost == 0,
        "initial costs must be zero",
    )
    evidence_cost_nonnegative = _require_invariant(
        all(action.cost >= 0 for action in canonical.evidence_actions),
        "evidence action costs must be non-negative",
    )
    repair_cost_is_one = _require_invariant(
        canonical.representation_actions[0].cost == 1,
        "representation repair cost must be 1",
    )
    costs_identical = _require_invariant(
        evidence_costs_identical and repair_costs_identical and initial_cost_zero,
        "primary and ablation costs must be identical",
    )
    # Console log P3-11: identify cost invariant checks.
    LOGGER.info("P3-11 cost_invariants_passed")
    e_star_already_admitted_and_valid = _require_invariant(
        e_star_present
        and e_star_in_admitted
        and e_star_valid
        and e_star_admitted_flag
        and e_star_target_bearing,
        "e_star must already be admitted and valid",
    )
    # Console log P3-12: identify the e_star pre-admission assertion.
    LOGGER.info("P3-12 e_star_already_admitted_and_valid")
    r0_definition = next(
        item
        for item in canonical.representations
        if item.identifier is RepresentationId.R0
    )
    r0_aliases = _require_invariant(
        r0_definition.projection == "alias_target_distinction"
        and not r0_definition.exposes_fields
        and len(compatible_hypotheses(canonical, RepresentationId.R0)) > 1,
        "R0 must alias the relevant distinction",
    )
    # Console log P3-13: identify the R0 aliasing assertion.
    LOGGER.info("P3-13 r0_aliases_relevant_distinction")
    r1_definition = next(
        item
        for item in canonical.representations
        if item.identifier is RepresentationId.R1
    )
    r1_reads_admitted_history_only = _require_invariant(
        canonical.representation_actions[0].reads == "admitted_history_only"
        and r1_definition.projection == "expose_admitted_target_label"
        and r1_definition.exposes_fields == ("target_label",)
        and len(compatible_hypotheses(canonical, RepresentationId.R1)) == 1,
        "R1 must read admitted history only",
    )
    # Console log P3-14: identify the R1 admitted-history-only assertion.
    LOGGER.info("P3-14 r1_reads_admitted_history_only")
    representations_identical = _require_invariant(
        canonical.representations == ablation.representations,
        "representation definitions must be identical",
    )
    canonical_repair_enabled = _require_invariant(
        canonical.representation_actions[0].enabled,
        "canonical I must retain the legal repair transition",
    )
    ablation_repair_disabled = _require_invariant(
        not ablation.representation_actions[0].enabled,
        "secondary ablation must disable only the repair transition",
    )
    invariants: dict[str, JsonValue] = {
        "logged_before_search": True,
        "evidence_history": {
            "e_star_in_initial_history": e_star_present,
            "e_star_in_admitted_evidence": e_star_in_admitted,
            "e_star_valid": e_star_valid,
            "e_star_admitted": e_star_admitted_flag,
            "e_star_target_bearing": e_star_target_bearing,
            "canonical_and_ablation_history_identical": history_identical,
            "canonical_and_ablation_admitted_evidence_identical": admitted_identical,
        },
        "evidence_actions_outcomes_and_costs": {
            "canonical_and_ablation_evidence_actions_identical": (
                evidence_actions_identical
            ),
            "canonical_and_ablation_evidence_outcomes_identical": (
                evidence_outcomes_identical
            ),
            "canonical_and_ablation_evidence_costs_identical": (
                evidence_costs_identical
            ),
            "canonical_and_ablation_repair_cost_identical": repair_costs_identical,
            "all_action_costs_nonnegative": all_costs_nonnegative,
        },
        "controller": {
            "canonical_controller_present": controller_present,
            "canonical_and_ablation_controller_identical": controller_identical,
        },
        "authority": {
            "canonical_authority_present": authority_present,
            "canonical_and_ablation_authority_identical": authority_identical,
        },
        "policies": {
            "Pi": policy_matches_contract,
            "Pi_eff": policy_matches_contract,
            "Pi_epi": policy_matches_contract,
            "terminal_rule": policy_matches_contract,
            "canonical_and_ablation_policy_identical": policy_identical,
        },
        "world_and_target_function": {
            "canonical_world_has_distinct_target_labels": distinct_target_labels,
            "canonical_and_ablation_hypotheses_identical": hypotheses_identical,
            "canonical_and_ablation_target_function_identical": (
                target_function_identical
            ),
        },
        "initial_representation": {
            "canonical_initial_representation_is_R0": initial_representation_r0,
            "canonical_and_ablation_initial_representation_identical": (
                initial_representation_identical
            ),
        },
        "costs": {
            "initial_cost_zero": initial_cost_zero,
            "evidence_action_cost_nonnegative": evidence_cost_nonnegative,
            "representation_repair_cost_is_1": repair_cost_is_one,
            "canonical_and_ablation_costs_identical": costs_identical,
        },
        "representation_semantics": {
            "e_star_already_admitted_and_valid": e_star_already_admitted_and_valid,
            "r0_aliases_relevant_distinction": r0_aliases,
            "r1_reads_admitted_history_only": r1_reads_admitted_history_only,
            "representation_definitions_identical": representations_identical,
            "canonical_repair_enabled": canonical_repair_enabled,
            "ablation_repair_disabled": ablation_repair_disabled,
        },
        "all_passed": True,
    }
    # Console log P3-15: identify completion of all pre-search causal invariants.
    LOGGER.info("P3-15 pre_intervention_causal_invariants_passed_before_search")
    return invariants


def serialize_result_document(document: Mapping[str, Any]) -> str:
    """Serialize the machine-readable result as sorted indented UTF-8 JSON."""

    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if "Infinity" in text or "NaN" in text:
        raise ValidationError("result JSON must not contain non-standard numbers")
    return text


def write_result_json_atomically(path: Path, document: Mapping[str, Any]) -> None:
    """Replace the result file only after a complete successful serialization."""

    text = serialize_result_document(document)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def _all_mapping_bools_true(value: JsonValue) -> bool:
    """Return whether every boolean leaf in a JSON object is true."""

    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return all(_all_mapping_bools_true(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_mapping_bools_true(item) for item in value)
    return True


def build_result_document(
    causal_invariants: Mapping[str, JsonValue],
    phase_one: Mapping[str, JsonValue],
    phase_two: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    """Assemble the checked-in machine-readable theorem witness."""

    primary = phase_two["primary_comparison"]
    full_pc = primary["full_pc"]
    fixed_r = primary["fixed_r"]
    ablation = phase_two["secondary_ablation"]
    assertions = phase_two["theorem_assertions"]
    semantics = causal_invariants["representation_semantics"]
    if not isinstance(primary, dict) or not isinstance(full_pc, dict):
        raise ValidationError("phase two primary comparison is malformed")
    if not isinstance(fixed_r, dict) or not isinstance(ablation, dict):
        raise ValidationError("phase two evaluation payload is malformed")
    if not isinstance(assertions, dict) or not isinstance(semantics, dict):
        raise ValidationError("phase two theorem assertions are malformed")
    acceptance: dict[str, JsonValue] = {
        "kappa_pi_I": full_pc["minimum_closure_cost"],
        "kappa_pi_I_equals_1": assertions["kappa_pi_I_equals_1"],
        "kappa_pi_fix_r_I": fixed_r["minimum_closure_cost"],
        "kappa_pi_fix_r_I_classification": fixed_r["cost_classification"],
        "kappa_pi_fix_r_I_is_infinity": assertions["kappa_pi_fix_r_I_is_infinity"],
        "full_pc_closed": full_pc["closed"],
        "full_pc_cost_classification": full_pc["cost_classification"],
        "full_pc_steps": full_pc["steps"],
        "full_pc_evidence_acquisitions": full_pc["evidence_acquisitions"],
        "full_pc_representation_repairs": full_pc["representation_repairs"],
        "full_pc_reachable_state_count": full_pc["reachable_state_count"],
        "full_pc_explored_state_count": full_pc["explored_state_count"],
        "full_pc_frontier_exhausted": full_pc["frontier_exhausted"],
        "fixed_r_closed": fixed_r["closed"],
        "fixed_r_reachable_state_count": fixed_r["reachable_state_count"],
        "fixed_r_explored_state_count": fixed_r["explored_state_count"],
        "fixed_r_frontier_exhausted": fixed_r["frontier_exhausted"],
        "same_canonical_instance_fingerprint": primary["same_instance_fingerprint"],
        "same_canonical_instance_object": primary["same_instance_object"],
        "secondary_ablation_structural_diff": ablation["structural_diff"],
        "secondary_ablation_exactly_one_difference": (
            ablation["structural_diff"] == list(EXPECTED_ABLATION_STRUCTURAL_DIFF)
        ),
        "secondary_ablation_role": ablation["role"],
        "e_star_already_admitted_and_valid": semantics[
            "e_star_already_admitted_and_valid"
        ],
        "r0_aliases_relevant_distinction": semantics[
            "r0_aliases_relevant_distinction"
        ],
        "r1_reads_admitted_history_only": semantics[
            "r1_reads_admitted_history_only"
        ],
        "causal_invariants_all_passed": causal_invariants["all_passed"],
        "all_passed": True,
    }
    return {
        "acceptance": acceptance,
        "artifact_kind": "executable_matched_theorem_witness",
        "causal_invariants": dict(causal_invariants),
        "claim_scope": {
            "deployment_evidence": False,
            "llm_evaluation": False,
            "prevalence_evidence": False,
            "statistical_validation": False,
        },
        "inputs": {
            "canonical_instance": "instance_plus.json",
            "canonical_instance_sha256": primary["canonical_instance_sha256"],
            "secondary_ablation": "instance_minus.json",
            "secondary_ablation_sha256": ablation["instance_sha256"],
        },
        "phase_one": dict(phase_one),
        "phase_two": dict(phase_two),
        "reproduction_command": REPRODUCTION_COMMAND,
        "schema_version": 1,
    }


def assert_phase_three_acceptance(document: Mapping[str, JsonValue]) -> None:
    """Fail closed unless every Phase 3 acceptance value is present and true."""

    acceptance = document["acceptance"]
    causal = document["causal_invariants"]
    phase_two = document["phase_two"]
    if not isinstance(acceptance, dict) or not isinstance(causal, dict):
        raise ValidationError("result document is missing required objects")
    if not isinstance(phase_two, dict):
        raise ValidationError("result document is missing phase two evidence")
    primary = phase_two["primary_comparison"]
    if not isinstance(primary, dict):
        raise ValidationError("result document is missing the primary comparison")
    full_pc = primary["full_pc"]
    fixed_r = primary["fixed_r"]
    ablation = phase_two["secondary_ablation"]
    if not isinstance(full_pc, dict) or not isinstance(fixed_r, dict):
        raise ValidationError("primary run results are malformed")
    if not isinstance(ablation, dict):
        raise ValidationError("secondary ablation result is malformed")
    if acceptance["kappa_pi_I"] != 1:
        raise ValidationError("acceptance requires kappa_Pi(I) = 1")
    if acceptance["kappa_pi_fix_r_I"] is not None:
        raise ValidationError("acceptance requires kappa_Pi_fixR(I) cost null")
    if acceptance["kappa_pi_fix_r_I_classification"] != "infinity":
        raise ValidationError("acceptance requires infinity classification")
    if full_pc["path"][0]["action_id"] != "repair_R0_to_R1":
        raise ValidationError("acceptance requires the optimal repair path")
    if full_pc["evidence_acquisitions"] != 0:
        raise ValidationError("acceptance requires zero new environmental evidence")
    if full_pc["representation_repairs"] != 1:
        raise ValidationError("acceptance requires one representation repair")
    if not _all_mapping_bools_true(causal):
        raise ValidationError("acceptance requires every causal invariant to be true")
    if document["reproduction_command"] != REPRODUCTION_COMMAND:
        raise ValidationError("acceptance requires the exact reproduction command")
    serialized = serialize_result_document(document)
    if "C:\\" in serialized or "/Users/" in serialized:
        raise ValidationError("result JSON must not contain machine-specific paths")


def validate_phase_three(
    canonical_path: Path = DEFAULT_CANONICAL_PATH,
    ablation_path: Path = DEFAULT_ABLATION_PATH,
    result_path: Path = DEFAULT_RESULT_PATH,
) -> dict[str, JsonValue]:
    """Run the Phase 3 artifact pipeline and write result.json only on success."""

    # Console log P3-01: identify the start of the Phase 3 artifact pipeline.
    LOGGER.info("P3-01 phase_three_started")
    canonical_raw, canonical_instance = load_instance(canonical_path)
    _ablation_raw, ablation_instance = load_instance(ablation_path)
    # Console log P3-02: identify input loading completed before search.
    LOGGER.info(
        "P3-02 inputs_loaded_before_search canonical_fingerprint=%s",
        canonical_fingerprint(canonical_raw),
    )
    causal_invariants = evaluate_pre_intervention_causal_invariants(
        canonical_instance,
        ablation_instance,
    )
    # Console log P3-16: identify invocation of Phase 1 validation after invariants.
    LOGGER.info("P3-16 phase_one_validation_invoked")
    phase_one = validate_phase_one(canonical_path, ablation_path)
    # Console log P3-17: identify invocation of Phase 2 search after invariants.
    LOGGER.info("P3-17 phase_two_evaluation_invoked")
    phase_two = validate_phase_two(canonical_path, ablation_path)
    # Console log P3-18: identify assembly of the machine-readable acceptance document.
    LOGGER.info("P3-18 acceptance_document_assembled")
    document = build_result_document(causal_invariants, phase_one, phase_two)
    assert_phase_three_acceptance(document)
    write_result_json_atomically(result_path, document)
    # Console log P3-19: identify atomic write of result.json after all assertions.
    LOGGER.info("P3-19 result_json_written_atomically")
    # Console log P3-20: identify successful completion of Phase 3.
    LOGGER.info("P3-20 phase_three_completed")
    return document


def _representation_repair_has_no_environment_read() -> bool:
    """Inspect the repair transition for any environmental acquisition path."""

    repair_source = inspect.getsource(apply_representation_action)
    projection_source = inspect.getsource(project_certificate)
    return _require_invariant(
        '"environment"' not in repair_source
        and "outcomes" not in repair_source
        and "acquired_evidence=()" in repair_source
        and "history=state.history" in repair_source
        and "admitted_evidence=state.admitted_evidence" in repair_source
        and '"environment"' not in projection_source,
        "representation repair must not read the environment",
    )


def _readme_sentence_count(readme_text: str) -> int:
    """Count interpretation sentences after the README heading."""

    body = readme_text
    if body.startswith("#"):
        body = body.split("\n", 1)[1]
    body = body.strip()
    sentences = [part.strip() for part in re.split(r"(?<=\.)\s+", body) if part.strip()]
    return len(sentences)


def _traceability_matrix_evidence(
    document: Mapping[str, JsonValue],
    canonical: Instance,
    ablation: Instance,
    readme_text: str,
) -> dict[str, bool]:
    """Evaluate every WorkPlan section-5 source requirement against the artifact."""

    phase_two = document["phase_two"]
    if not isinstance(phase_two, dict):
        raise ValidationError("phase two evidence is missing from result.json")
    primary = phase_two["primary_comparison"]
    ablation_result = phase_two["secondary_ablation"]
    assertions = phase_two["theorem_assertions"]
    causal = document["causal_invariants"]
    acceptance = document["acceptance"]
    if not isinstance(primary, dict) or not isinstance(ablation_result, dict):
        raise ValidationError("primary or ablation evidence is malformed")
    if not isinstance(assertions, dict) or not isinstance(causal, dict):
        raise ValidationError("assertion or causal evidence is malformed")
    if not isinstance(acceptance, dict):
        raise ValidationError("acceptance evidence is malformed")
    full_pc = primary["full_pc"]
    fixed_r = primary["fixed_r"]
    if not isinstance(full_pc, dict) or not isinstance(fixed_r, dict):
        raise ValidationError("primary run results are malformed")
    evidence = {
        "one_deterministic_finite_checker": (
            document["reproduction_command"] == REPRODUCTION_COMMAND
            and document["artifact_kind"] == "executable_matched_theorem_witness"
        ),
        "canonical_I_enables_R0_to_R1": (
            canonical.representation_actions[0].enabled
            and full_pc["path"][0]["action_id"] == "repair_R0_to_R1"
        ),
        "fixed_R_preserves_R0": (
            fixed_r["reached_representations"] == ["R0"]
            and "repair_R0_to_R1" in fixed_r["initial_excluded_actions"]
        ),
        "same_world_and_target_function": bool(primary["same_instance_object"]),
        "same_initial_history_containing_e_star": (
            "e_star" in canonical.initial_state.admitted_evidence
            and bool(primary["same_initial_state_object"])
        ),
        "same_admitted_evidence": bool(primary["same_initial_state_object"]),
        "same_controller_and_authority": bool(primary["same_initial_state_object"]),
        "same_full_policy_and_terminal_rule": bool(primary["same_policy_object"]),
        "same_actions_outcomes_costs_transition": bool(
            primary["same_transition_relation_object"]
            and primary["same_instance_fingerprint"]
        ),
        "same_initial_R0": (
            canonical.initial_state.representation is RepresentationId.R0
            and bool(primary["same_initial_state_object"])
        ),
        "secondary_ablation_exactly_one_difference": (
            ablation_result["structural_diff"]
            == list(EXPECTED_ABLATION_STRUCTURAL_DIFF)
        ),
        "R0_remains_non_closing": full_pc["initial_alternative_count"] == 2,
        "R1_closes_from_admitted_history": (
            full_pc["closing_alternative_count"] == 1
            and full_pc["evidence_acquisitions"] == 0
        ),
        "kappa_Pi_I_equals_1": full_pc["minimum_closure_cost"] == 1,
        "zero_new_evidence_on_closing_path": (
            full_pc["evidence_acquisitions"] == 0
        ),
        "kappa_Pi_fixR_I_is_infinity": (
            fixed_r["cost_classification"] == "infinity"
            and fixed_r["minimum_closure_cost"] is None
            and bool(fixed_r["frontier_exhausted"])
            and not bool(fixed_r["closed"])
        ),
        "transition_deletion_destroys_closure": (
            ablation_result["role"] == "transition_deletion_corroboration_only"
            and not bool(ablation_result["full_pc"]["closed"])
        ),
        "causal_invariants_logged_and_true": bool(causal["all_passed"]),
        "machine_readable_report": document["schema_version"] == 1,
        "one_command_reproducibility": (
            document["reproduction_command"] == REPRODUCTION_COMMAND
        ),
        "five_to_eight_sentence_interpretation": (
            5 <= _readme_sentence_count(readme_text) <= 8
            and REPRODUCTION_COMMAND in readme_text
        ),
        "narrow_paper_wording": (
            document["claim_scope"]["statistical_validation"] is False
            and document["claim_scope"]["prevalence_evidence"] is False
            and document["claim_scope"]["deployment_evidence"] is False
            and document["claim_scope"]["llm_evaluation"] is False
        ),
        "ablation_is_not_canonical": ablation is not canonical,
        "acceptance_all_passed": bool(acceptance["all_passed"]),
    }
    failed = [name for name, passed in evidence.items() if not passed]
    if failed:
        raise ValidationError(f"traceability matrix failed: {failed}")
    return evidence


def validate_phase_four(
    canonical_path: Path = DEFAULT_CANONICAL_PATH,
    ablation_path: Path = DEFAULT_ABLATION_PATH,
    result_path: Path = DEFAULT_RESULT_PATH,
    readme_path: Path = DEFAULT_README_PATH,
) -> dict[str, JsonValue]:
    """Run the Phase 4 independent acceptance audit and fail closed on gaps."""

    # Console log P4-01: identify the start of the Phase 4 acceptance audit.
    LOGGER.info("P4-01 phase_four_audit_started")
    if not result_path.is_file():
        raise ValidationError("result.json is required for the Phase 4 audit")
    if not readme_path.is_file():
        raise ValidationError("README.md is required for the Phase 4 audit")
    canonical_raw, canonical_instance = load_instance(canonical_path)
    ablation_raw, ablation_instance = load_instance(ablation_path)
    document = json.loads(result_path.read_text(encoding="utf-8"))
    readme_text = readme_path.read_text(encoding="utf-8")
    if not isinstance(document, dict):
        raise ValidationError("result.json must be a JSON object")
    # Console log P4-02: identify loading of instances and checked-in artifacts.
    LOGGER.info("P4-02 audit_artifacts_loaded")
    no_environment_read = _representation_repair_has_no_environment_read()
    repair = canonical_instance.representation_actions[0]
    if repair.reads != "admitted_history_only":
        raise ValidationError("repair must declare admitted-history-only reads")
    # Console log P4-03: identify the no-environment-read repair audit.
    LOGGER.info("P4-03 representation_repair_has_no_environment_read")
    full_view = action_policy_view(
        canonical_instance,
        canonical_instance.initial_state.representation,
        EvaluatorPolicyClass.FULL_PC,
    )
    fixed_view = action_policy_view(
        canonical_instance,
        canonical_instance.initial_state.representation,
        EvaluatorPolicyClass.FIXED_R,
    )
    same_object = _require_invariant(
        full_view.instance is fixed_view.instance
        and full_view.instance is canonical_instance,
        "primary policy views must share the canonical instance object",
    )
    same_serialization = _require_invariant(
        canonical_fingerprint(canonical_raw)
        == document["inputs"]["canonical_instance_sha256"],
        "checked-in fingerprint must match the loaded canonical serialization",
    )
    # Console log P4-04: identify same-instance object and serialization audit.
    LOGGER.info("P4-04 primary_runs_share_canonical_object_and_serialization")
    filter_only = _require_invariant(
        canonical_instance.representation_actions[0].enabled
        and any(
            isinstance(action, RepresentationAction)
            and action.identifier == "repair_R0_to_R1"
            for action in full_view.actions
        )
        and not any(
            isinstance(action, RepresentationAction)
            for action in fixed_view.actions
        ),
        "fixed R must exclude repair only by evaluator filtering",
    )
    # Console log P4-05: identify fixed-R filter-only audit.
    LOGGER.info("P4-05 fixed_r_enforced_only_by_evaluator_filtering")
    differences = validate_ablation_pair(
        canonical_raw,
        ablation_raw,
        canonical_instance,
        ablation_instance,
    )
    ablation_clean = _require_invariant(
        differences == EXPECTED_ABLATION_STRUCTURAL_DIFF,
        "secondary ablation must have no unapproved structural difference",
    )
    # Console log P4-06: identify secondary ablation singleton-diff audit.
    LOGGER.info("P4-06 secondary_ablation_has_no_unapproved_diff")
    phase_two = document["phase_two"]
    if not isinstance(phase_two, dict):
        raise ValidationError("result.json is missing phase two evidence")
    fixed_r = phase_two["primary_comparison"]["fixed_r"]
    if not isinstance(fixed_r, dict):
        raise ValidationError("fixed-R result is malformed")
    infinity_by_exhaustion = _require_invariant(
        fixed_r["closed"] is False
        and fixed_r["minimum_closure_cost"] is None
        and fixed_r["cost_classification"] == "infinity"
        and fixed_r["frontier_exhausted"] is True,
        "infinity must be tied to exhausted finite traversal",
    )
    # Console log P4-07: identify infinity-by-exhaustion audit.
    LOGGER.info("P4-07 infinity_tied_to_exhausted_finite_traversal")
    claim_scope = document["claim_scope"]
    if not isinstance(claim_scope, dict):
        raise ValidationError("result.json is missing claim_scope")
    claim_scope_narrow = _require_invariant(
        claim_scope["statistical_validation"] is False
        and claim_scope["prevalence_evidence"] is False
        and claim_scope["deployment_evidence"] is False
        and claim_scope["llm_evaluation"] is False
        and "not statistical validation" in readme_text
        and "prevalence evidence" in readme_text
        and "deployment evidence" in readme_text
        and "executable matched theorem witness" in readme_text
        and "benchmark" not in document["artifact_kind"]
        and "training" not in readme_text.lower(),
        "artifact must not widen into training, statistical, benchmark, prevalence, or deployment claims",
    )
    # Console log P4-08: identify claim-scope and wording audit.
    LOGGER.info("P4-08 claim_scope_has_no_widened_empirical_claim")
    matrix = _traceability_matrix_evidence(
        document, canonical_instance, ablation_instance, readme_text
    )
    # Console log P4-09: identify source-to-deliverable matrix closeout.
    LOGGER.info(
        "P4-09 source_traceability_matrix_complete items=%d",
        len(matrix),
    )
    evidence: dict[str, JsonValue] = {
        "representation_repair_has_no_environment_read": no_environment_read,
        "primary_same_canonical_object": same_object,
        "primary_same_canonical_serialization": same_serialization,
        "fixed_r_enforced_only_by_evaluator_filtering": filter_only,
        "secondary_ablation_has_no_unapproved_diff": ablation_clean,
        "infinity_tied_to_exhausted_finite_traversal": infinity_by_exhaustion,
        "claim_scope_has_no_widened_empirical_claim": claim_scope_narrow,
        "traceability_matrix": {name: True for name in matrix},
        "all_passed": True,
    }
    # Console log P4-10: identify successful completion of the Phase 4 audit.
    LOGGER.info("P4-10 phase_four_audit_completed")
    return evidence


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse optional path overrides while keeping repository-root defaults."""

    parser = argparse.ArgumentParser(
        description=(
            "Deterministic finite complementarity checker for Theorem 2, Part I."
        )
    )
    parser.add_argument(
        "--canonical",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
        help="Canonical instance path. Default: instance_plus.json beside checker.py.",
    )
    parser.add_argument(
        "--ablation",
        type=Path,
        default=DEFAULT_ABLATION_PATH,
        help="Secondary ablation path. Default: instance_minus.json beside checker.py.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULT_PATH,
        help="Result artifact path. Default: result.json beside checker.py.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Repository-root CLI entry point with fail-closed nonzero status."""

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    arguments = parse_args(argv)
    try:
        validate_phase_three(
            arguments.canonical,
            arguments.ablation,
            arguments.output,
        )
    except ValidationError as error:
        # Console log P3-ERROR: identify a failed Phase 3 contract or theorem assertion.
        LOGGER.error("P3-ERROR phase_three_failed reason=%s", error)
        return 1
    try:
        validate_phase_four(
            arguments.canonical,
            arguments.ablation,
            arguments.output,
        )
    except ValidationError as error:
        # Console log P4-ERROR: identify a failed Phase 4 acceptance audit.
        LOGGER.error("P4-ERROR phase_four_failed reason=%s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
