"""Phase 1 through Phase 4 tests for the finite complementarity checker."""

from __future__ import annotations

import ast
import copy
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

from checker import (
    ActionKind,
    CostClassification,
    EXPECTED_ABLATION_STRUCTURAL_DIFF,
    EvidenceAction,
    EvaluatorPolicyClass,
    REPRODUCTION_COMMAND,
    RepresentationAction,
    RepresentationId,
    ValidationError,
    WeightedSuccessor,
    action_policy_view,
    apply_evidence_action,
    apply_representation_action,
    canonical_fingerprint,
    canonical_json,
    compatible_hypotheses,
    evaluate_closure,
    evaluation_to_json,
    exhaustive_uniform_cost,
    initial_search_state,
    load_instance,
    pc_successors,
    project_certificate,
    successor_representation,
    structural_diff,
    validate_ablation_pair,
    validate_phase_four,
    validate_phase_one,
    validate_phase_three,
    validate_phase_two,
)


ROOT = Path(__file__).resolve().parents[1]
PLUS_PATH = ROOT / "instance_plus.json"
MINUS_PATH = ROOT / "instance_minus.json"
RESULT_PATH = ROOT / "result.json"
README_PATH = ROOT / "README.md"
CHECKER_PATH = ROOT / "checker.py"
ORACLE_PATH = Path(__file__).resolve().parent / "independent_oracle.py"
if str(ORACLE_PATH.parent) not in sys.path:
    sys.path.insert(0, str(ORACLE_PATH.parent))

from independent_oracle import (
    evaluate_required_oracle_runs,
    enumerate_finite_graph,
)

class InstanceSchemaTests(unittest.TestCase):
    """Strict schema and immutable-domain tests."""

    def test_canonical_and_ablation_files_load_and_validate(self) -> None:
        plus_raw, plus = load_instance(PLUS_PATH)
        minus_raw, minus = load_instance(MINUS_PATH)

        self.assertTrue(plus.representation_actions[0].enabled)
        self.assertFalse(minus.representation_actions[0].enabled)
        self.assertEqual(plus_raw["schema_version"], 1)
        self.assertEqual(minus_raw["schema_version"], 1)

    def test_actions_are_separate_runtime_types(self) -> None:
        _, instance = load_instance(PLUS_PATH)

        self.assertIsInstance(instance.evidence_actions[0], EvidenceAction)
        self.assertIsInstance(
            instance.representation_actions[0], RepresentationAction
        )
        self.assertNotIsInstance(instance.evidence_actions[0], RepresentationAction)
        self.assertNotIsInstance(instance.representation_actions[0], EvidenceAction)

    def test_loaded_domain_model_is_immutable(self) -> None:
        _, instance = load_instance(PLUS_PATH)

        with self.assertRaises(FrozenInstanceError):
            instance.instance_id = "mutated"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            instance.initial_state.admitted_evidence[0] = "mutated"  # type: ignore[index]

    def test_load_and_canonical_round_trip_do_not_modify_inputs(self) -> None:
        before_bytes = PLUS_PATH.read_bytes()
        raw, _ = load_instance(PLUS_PATH)
        raw_snapshot = copy.deepcopy(raw)

        canonical = canonical_json(raw)

        self.assertEqual(json.loads(canonical), raw_snapshot)
        self.assertEqual(raw, raw_snapshot)
        self.assertEqual(PLUS_PATH.read_bytes(), before_bytes)

    def test_unknown_or_missing_schema_keys_are_rejected(self) -> None:
        raw = json.loads(PLUS_PATH.read_text(encoding="utf-8"))
        unknown = copy.deepcopy(raw)
        unknown["unexpected"] = True
        missing = copy.deepcopy(raw)
        del missing["policy"]["Pi_epi"]

        with self.assertRaisesRegex(ValidationError, "invalid keys"):
            self._load_temporary(unknown)
        with self.assertRaisesRegex(ValidationError, "invalid keys"):
            self._load_temporary(missing)

    def test_invalid_scalar_types_are_rejected_strictly(self) -> None:
        raw = json.loads(PLUS_PATH.read_text(encoding="utf-8"))
        raw["representation_actions"][0]["cost"] = True

        with self.assertRaisesRegex(ValidationError, "non-negative integer"):
            self._load_temporary(raw)

    def test_unknown_action_kinds_are_controlled_validation_errors(self) -> None:
        raw = json.loads(PLUS_PATH.read_text(encoding="utf-8"))
        for action_collection in ("evidence_actions", "representation_actions"):
            with self.subTest(action_collection=action_collection):
                mutated = copy.deepcopy(raw)
                mutated[action_collection][0]["kind"] = "unknown"
                with self.assertRaisesRegex(
                    ValidationError, "must be evidence or representation"
                ):
                    self._load_temporary(mutated)

    def test_invalid_e_star_is_rejected(self) -> None:
        raw = json.loads(PLUS_PATH.read_text(encoding="utf-8"))
        raw["initial_state"]["history"][0]["valid"] = False

        with self.assertRaisesRegex(ValidationError, "valid and marked admitted"):
            self._load_temporary(raw)

    def _load_temporary(self, raw: dict[str, Any]) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "instance.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            load_instance(path)


class RepresentationSemanticsTests(unittest.TestCase):
    """Tests for representation projection and closure semantics."""

    @classmethod
    def setUpClass(cls) -> None:
        _, cls.instance = load_instance(PLUS_PATH)

    def test_r0_aliases_target_and_is_non_closing(self) -> None:
        represented = project_certificate(self.instance, RepresentationId.R0)
        alternatives = compatible_hypotheses(self.instance, RepresentationId.R0)

        self.assertIsNone(represented.represented_target_label)
        self.assertEqual(
            alternatives, ("w_target_absent", "w_target_present")
        )
        self.assertGreater(len(alternatives), 1)

    def test_r1_uses_pre_admitted_e_star_and_closes(self) -> None:
        history_before = self.instance.initial_state.history
        admitted_before = self.instance.initial_state.admitted_evidence

        represented = project_certificate(self.instance, RepresentationId.R1)
        alternatives = compatible_hypotheses(self.instance, RepresentationId.R1)

        self.assertEqual(represented.represented_target_label, "present")
        self.assertEqual(alternatives, ("w_target_present",))
        self.assertEqual(self.instance.initial_state.history, history_before)
        self.assertEqual(
            self.instance.initial_state.admitted_evidence, admitted_before
        )

    def test_r1_has_no_environmental_acquisition_parameter_or_action(self) -> None:
        _, instance = load_instance(PLUS_PATH)

        self.assertEqual(
            instance.representation_actions[0].reads, "admitted_history_only"
        )
        self.assertNotIn(
            instance.representation_actions[0], instance.evidence_actions
        )
        self.assertEqual(
            project_certificate(instance, RepresentationId.R1).represented_target_label,
            "present",
        )


class EvaluatorPolicyClassTests(unittest.TestCase):
    """Same-instance full-PC and fixed-R action-admissibility tests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical_raw, cls.instance = load_instance(PLUS_PATH)

    def test_primary_policy_views_retain_same_canonical_instance_object(self) -> None:
        canonical_before = canonical_json(self.canonical_raw)
        full_view = action_policy_view(
            self.instance,
            RepresentationId.R0,
            EvaluatorPolicyClass.FULL_PC,
        )
        fixed_view = action_policy_view(
            self.instance,
            RepresentationId.R0,
            EvaluatorPolicyClass.FIXED_R,
        )

        self.assertIs(full_view.instance, self.instance)
        self.assertIs(fixed_view.instance, self.instance)
        self.assertIs(full_view.instance, fixed_view.instance)
        self.assertTrue(self.instance.representation_actions[0].enabled)
        self.assertEqual(canonical_json(self.canonical_raw), canonical_before)

    def test_fixed_r_filters_successors_without_mutating_action_legality(self) -> None:
        full_view = action_policy_view(
            self.instance,
            RepresentationId.R0,
            EvaluatorPolicyClass.FULL_PC,
        )
        fixed_view = action_policy_view(
            self.instance,
            RepresentationId.R0,
            EvaluatorPolicyClass.FIXED_R,
        )
        expected_fixed_actions = tuple(
            action
            for action in full_view.actions
            if successor_representation(action, RepresentationId.R0)
            is RepresentationId.R0
        )

        self.assertEqual(
            tuple(action.identifier for action in full_view.actions),
            ("observe_alias_preserving_signal", "repair_R0_to_R1"),
        )
        self.assertEqual(fixed_view.actions, expected_fixed_actions)
        self.assertEqual(
            tuple(action.identifier for action in fixed_view.actions),
            ("observe_alias_preserving_signal",),
        )
        self.assertTrue(self.instance.representation_actions[0].enabled)


class AblationContractTests(unittest.TestCase):
    """Secondary ablation singleton-diff and protected-field mutation tests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.plus_raw, cls.plus = load_instance(PLUS_PATH)
        cls.minus_raw, cls.minus = load_instance(MINUS_PATH)

    def test_secondary_ablation_has_exactly_one_approved_difference(self) -> None:
        differences = validate_ablation_pair(
            self.plus_raw, self.minus_raw, self.plus, self.minus
        )

        self.assertEqual(differences, EXPECTED_ABLATION_STRUCTURAL_DIFF)
        self.assertEqual(
            structural_diff(self.plus_raw, self.minus_raw),
            ("representation_actions[0].enabled",),
        )

    def test_every_protected_ablation_leaf_rejects_mutation(self) -> None:
        excluded_intervention = ("representation_actions", 0, "enabled")
        protected_leaf_paths = tuple(
            path
            for path in self._leaf_paths(self.minus_raw)
            if path != excluded_intervention
        )
        self.assertEqual(len(protected_leaf_paths), 47)

        for path in protected_leaf_paths:
            with self.subTest(path=path):
                mutated_minus = copy.deepcopy(self.minus_raw)
                self._mutate_leaf(mutated_minus, path)
                with self.assertRaisesRegex(
                    ValidationError, "canonical instance and ablation must differ only"
                ):
                    validate_ablation_pair(
                        self.plus_raw,
                        mutated_minus,
                        self.plus,
                        self.minus,
                    )

    @staticmethod
    def _leaf_paths(
        value: Any, path: tuple[str | int, ...] = ()
    ) -> tuple[tuple[str | int, ...], ...]:
        if isinstance(value, dict):
            return tuple(
                leaf
                for key, child in value.items()
                for leaf in AblationContractTests._leaf_paths(child, (*path, key))
            )
        if isinstance(value, list):
            return tuple(
                leaf
                for index, child in enumerate(value)
                for leaf in AblationContractTests._leaf_paths(child, (*path, index))
            )
        return (path,)

    @staticmethod
    def _mutate_leaf(
        document: dict[str, Any], path: tuple[str | int, ...]
    ) -> None:
        cursor: Any = document
        for component in path[:-1]:
            cursor = cursor[component]
        key = path[-1]
        value = cursor[key]
        if type(value) is bool:
            cursor[key] = not value
        elif type(value) is int:
            cursor[key] = value + 1
        elif isinstance(value, str):
            cursor[key] = f"{value}__mutated"
        else:
            raise AssertionError(f"unsupported JSON leaf at {path}: {value!r}")

    def test_extra_second_difference_is_never_ignored(self) -> None:
        mutated_minus = copy.deepcopy(self.minus_raw)
        mutated_minus["policy"]["Pi"] = "changed"

        self.assertEqual(
            structural_diff(self.plus_raw, mutated_minus),
            ("policy.Pi", "representation_actions[0].enabled"),
        )

    def test_wrong_intervention_direction_is_rejected(self) -> None:
        plus_raw = copy.deepcopy(self.plus_raw)
        minus_raw = copy.deepcopy(self.minus_raw)
        plus_raw["representation_actions"][0]["enabled"] = False
        minus_raw["representation_actions"][0]["enabled"] = True

        with self.assertRaisesRegex(ValidationError, "canonical I must enable"):
            validate_ablation_pair(plus_raw, minus_raw, self.minus, self.plus)


class PhaseOneIntegrationAndStressTests(unittest.TestCase):
    """Phase 1 integration, logging, and deterministic stress tests."""

    def test_phase_one_evidence_satisfies_all_current_gates(self) -> None:
        evidence = validate_phase_one(PLUS_PATH, MINUS_PATH)

        self.assertEqual(evidence["canonical_instance"], "instance_plus.json")
        self.assertTrue(evidence["canonical_instance_valid"])
        self.assertTrue(evidence["canonical_transition_repair_enabled"])
        self.assertEqual(len(evidence["canonical_instance_sha256"]), 64)
        self.assertEqual(
            evidence["full_pc_instance_sha256"],
            evidence["fixed_r_instance_sha256"],
        )
        self.assertEqual(
            evidence["canonical_instance_sha256"],
            evidence["full_pc_instance_sha256"],
        )
        self.assertTrue(evidence["primary_same_instance_fingerprint"])
        self.assertTrue(evidence["primary_same_instance_object"])
        self.assertTrue(evidence["primary_same_initial_state_object"])
        self.assertTrue(evidence["primary_same_policy_object"])
        self.assertTrue(evidence["primary_same_transition_relation_object"])
        self.assertEqual(
            evidence["full_pc_admissible_actions"],
            ["observe_alias_preserving_signal", "repair_R0_to_R1"],
        )
        self.assertEqual(
            evidence["fixed_r_admissible_actions"],
            ["observe_alias_preserving_signal"],
        )
        self.assertEqual(
            evidence["fixed_r_excluded_actions"], ["repair_R0_to_R1"]
        )
        self.assertTrue(evidence["canonical_instance_unchanged_by_policy_projection"])
        self.assertTrue(evidence["ablation_instance_valid"])
        self.assertEqual(
            evidence["ablation_structural_diff"],
            ["representation_actions[0].enabled"],
        )
        self.assertFalse(evidence["r0_closes"])
        self.assertTrue(evidence["r1_closes"])
        self.assertTrue(evidence["ablation_history_unchanged"])
        self.assertTrue(evidence["ablation_admitted_evidence_unchanged"])
        self.assertTrue(evidence["e_star_pre_admitted"])
        self.assertTrue(evidence["canonical_round_trip_stable"])

    def test_all_thirteen_identified_console_steps_are_emitted_in_order(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("pc_checker")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            validate_phase_one(PLUS_PATH, MINUS_PATH)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        output = stream.getvalue()
        positions = [output.index(f"P1-{index:02d}") for index in range(1, 14)]
        self.assertEqual(positions, sorted(positions))

    def test_500_repeated_validations_are_deterministic_and_non_mutating(self) -> None:
        plus_before = PLUS_PATH.read_bytes()
        minus_before = MINUS_PATH.read_bytes()
        baseline = canonical_json(validate_phase_one(PLUS_PATH, MINUS_PATH))

        logger = logging.getLogger("pc_checker")
        previous_disabled = logger.disabled
        logger.disabled = True
        try:
            for _ in range(500):
                current = canonical_json(validate_phase_one(PLUS_PATH, MINUS_PATH))
                self.assertEqual(current, baseline)
        finally:
            logger.disabled = previous_disabled

        self.assertEqual(PLUS_PATH.read_bytes(), plus_before)
        self.assertEqual(MINUS_PATH.read_bytes(), minus_before)


class UniformCostAlgorithmTests(unittest.TestCase):
    """Independent weighted-graph tests for the traversal engine."""

    def test_longer_cheaper_path_replaces_expensive_goal_discovered_first(self) -> None:
        graph = {
            "start": (
                WeightedSuccessor("goal", "expensive_direct", 9, "00_expensive"),
                WeightedSuccessor("middle", "cheap_first", 1, "01_cheap"),
            ),
            "middle": (
                WeightedSuccessor("goal", "cheap_second", 2, "00_finish"),
            ),
            "goal": (),
        }

        result = exhaustive_uniform_cost(
            start_state="start",
            semantic_key=lambda state: state,
            deterministic_key=lambda key: key,
            is_goal=lambda state: state == "goal",
            successors=lambda state: graph[state],
        )

        self.assertEqual(result.minimum_cost, 3)
        self.assertEqual(result.path, ("cheap_first", "cheap_second"))
        self.assertEqual(result.goal_state, "goal")
        self.assertTrue(result.frontier_exhausted)
        self.assertEqual(result.reachable_state_count, 3)

    def test_reachable_cycle_is_deduplicated_before_finite_exhaustion(self) -> None:
        graph = {
            "start": (WeightedSuccessor("a", "start_to_a", 1, "00"),),
            "a": (
                WeightedSuccessor("start", "a_to_start", 1, "00"),
                WeightedSuccessor("b", "a_to_b", 1, "01"),
            ),
            "b": (WeightedSuccessor("a", "b_to_a", 1, "00"),),
        }

        result = exhaustive_uniform_cost(
            start_state="start",
            semantic_key=lambda state: state,
            deterministic_key=lambda key: key,
            is_goal=lambda state: False,
            successors=lambda state: graph[state],
        )

        self.assertIsNone(result.goal_state)
        self.assertIsNone(result.minimum_cost)
        self.assertTrue(result.frontier_exhausted)
        self.assertEqual(result.reachable_state_count, 3)
        self.assertEqual(result.expanded_state_count, 3)
        self.assertEqual(result.deduplicated_successor_count, 2)

    def test_negative_edge_cost_is_rejected(self) -> None:
        graph = {
            "start": (WeightedSuccessor("invalid", "negative", -1, "00"),),
            "invalid": (),
        }

        with self.assertRaisesRegex(ValidationError, "non-negative integer"):
            exhaustive_uniform_cost(
                start_state="start",
                semantic_key=lambda state: state,
                deterministic_key=lambda key: key,
                is_goal=lambda state: False,
                successors=lambda state: graph[state],
            )

    def test_stale_queue_entry_is_rejected_after_lower_cost_update(self) -> None:
        graph = {
            "start": (
                WeightedSuccessor("target", "expensive", 9, "00_expensive"),
                WeightedSuccessor("middle", "first", 1, "01_first"),
            ),
            "middle": (WeightedSuccessor("target", "second", 2, "00_second"),),
            "target": (),
        }

        result = exhaustive_uniform_cost(
            start_state="start",
            semantic_key=lambda state: state,
            deterministic_key=lambda key: key,
            is_goal=lambda state: False,
            successors=lambda state: graph[state],
        )

        self.assertTrue(result.frontier_exhausted)
        self.assertEqual(result.stale_queue_entry_count, 1)
        self.assertEqual(result.reachable_state_count, 3)
        self.assertEqual(result.expanded_state_count, 3)


class PhaseTwoSuccessorTests(unittest.TestCase):
    """Typed PC successor and invariant-preservation tests."""

    @classmethod
    def setUpClass(cls) -> None:
        _, cls.instance = load_instance(PLUS_PATH)
        cls.start = initial_search_state(cls.instance)

    def test_evidence_and_representation_successors_are_separate(self) -> None:
        successors = pc_successors(
            self.instance, self.start, EvaluatorPolicyClass.FULL_PC
        )
        by_kind = {candidate.edge.action_kind: candidate for candidate in successors}

        evidence = by_kind[ActionKind.EVIDENCE]
        representation = by_kind[ActionKind.REPRESENTATION]
        self.assertIn("e_aux", evidence.state.admitted_evidence)
        self.assertEqual(evidence.state.representation, RepresentationId.R0)
        self.assertEqual(evidence.edge.acquired_evidence, ("e_aux",))
        self.assertEqual(representation.state.representation, RepresentationId.R1)
        self.assertEqual(representation.edge.acquired_evidence, ())

    def test_representation_repair_preserves_nonrepresentation_state(self) -> None:
        successor, transition = apply_representation_action(
            self.start, self.instance.representation_actions[0]
        )

        self.assertIs(successor.certificate, self.start.certificate)
        self.assertIs(successor.controller, self.start.controller)
        self.assertIs(successor.authority, self.start.authority)
        self.assertIs(successor.history, self.start.history)
        self.assertIs(successor.admitted_evidence, self.start.admitted_evidence)
        self.assertEqual(successor.accumulated_cost, 1)
        self.assertEqual(successor.rank, 1)
        self.assertEqual(successor.depth, 1)
        self.assertEqual(transition.action_cost, 1)
        self.assertEqual(transition.acquired_evidence, ())

    def test_evidence_successor_has_declared_cost_and_outcome(self) -> None:
        successor, transition = apply_evidence_action(
            self.start, self.instance.evidence_actions[0]
        )

        self.assertEqual(successor.accumulated_cost, 2)
        self.assertEqual(successor.rank, 1)
        self.assertEqual(successor.depth, 1)
        self.assertEqual(transition.action_cost, 2)
        self.assertEqual(transition.acquired_evidence, ("e_aux",))


class PhaseTwoTheoremTests(unittest.TestCase):
    """Same-instance theorem and secondary ablation evaluations."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.canonical_raw, cls.canonical = load_instance(PLUS_PATH)
        cls.ablation_raw, cls.ablation = load_instance(MINUS_PATH)
        cls.canonical_fingerprint = canonical_fingerprint(cls.canonical_raw)
        cls.ablation_fingerprint = canonical_fingerprint(cls.ablation_raw)
        cls.full = evaluate_closure(
            cls.canonical,
            cls.canonical_fingerprint,
            EvaluatorPolicyClass.FULL_PC,
        )
        cls.fixed = evaluate_closure(
            cls.canonical,
            cls.canonical_fingerprint,
            EvaluatorPolicyClass.FIXED_R,
        )
        cls.ablation_full = evaluate_closure(
            cls.ablation,
            cls.ablation_fingerprint,
            EvaluatorPolicyClass.FULL_PC,
        )

    def test_full_pc_has_unit_minimum_representation_repair(self) -> None:
        self.assertTrue(self.full.closed)
        self.assertEqual(self.full.minimum_closure_cost, 1)
        self.assertIs(self.full.cost_classification, CostClassification.FINITE)
        self.assertEqual(self.full.step_count, 1)
        self.assertEqual(self.full.evidence_acquisition_count, 0)
        self.assertEqual(self.full.representation_repair_count, 1)
        self.assertEqual(self.full.path[0].action_id, "repair_R0_to_R1")
        self.assertEqual(
            self.full.path[0].destination_representation, RepresentationId.R1
        )
        self.assertEqual(self.full.closing_alternatives, ("w_target_present",))
        self.assertIsNotNone(self.full.closing_state)
        self.assertEqual(self.full.closing_state.accumulated_cost, 1)
        self.assertEqual(self.full.closing_state.rank, 1)
        self.assertEqual(self.full.closing_state.depth, 1)
        self.assertTrue(self.full.frontier_exhausted)
        self.assertEqual(self.full.reachable_state_count, 4)
        self.assertEqual(self.full.expanded_state_count, 4)

    def test_fixed_r_is_infinite_only_after_frontier_exhaustion(self) -> None:
        self.assertFalse(self.fixed.closed)
        self.assertIsNone(self.fixed.minimum_closure_cost)
        self.assertIs(self.fixed.cost_classification, CostClassification.INFINITY)
        self.assertTrue(self.fixed.frontier_exhausted)
        self.assertEqual(self.fixed.reachable_state_count, 2)
        self.assertEqual(self.fixed.expanded_state_count, 2)
        self.assertGreaterEqual(self.fixed.deduplicated_successor_count, 1)
        self.assertTrue(
            all(
                state.representation is RepresentationId.R0
                for state in self.fixed.reached_states
            )
        )
        self.assertTrue(
            any(
                "e_aux" in state.admitted_evidence
                for state in self.fixed.reached_states
            )
        )

    def test_primary_evaluations_share_exact_canonical_instance(self) -> None:
        self.assertIs(self.full.instance, self.fixed.instance)
        self.assertIs(self.full.instance, self.canonical)
        self.assertIs(
            self.full.instance.initial_state, self.fixed.instance.initial_state
        )
        self.assertIs(self.full.instance.policy, self.fixed.instance.policy)
        self.assertIs(
            self.full.instance.evidence_actions,
            self.fixed.instance.evidence_actions,
        )
        self.assertIs(
            self.full.instance.representation_actions,
            self.fixed.instance.representation_actions,
        )
        self.assertEqual(
            self.full.instance_fingerprint, self.fixed.instance_fingerprint
        )
        self.assertTrue(self.canonical.representation_actions[0].enabled)

    def test_transition_deletion_is_separate_nonclosing_ablation(self) -> None:
        self.assertIsNot(self.ablation_full.instance, self.canonical)
        self.assertFalse(self.ablation_full.closed)
        self.assertIsNone(self.ablation_full.minimum_closure_cost)
        self.assertIs(
            self.ablation_full.cost_classification, CostClassification.INFINITY
        )
        self.assertTrue(self.ablation_full.frontier_exhausted)
        self.assertNotEqual(
            self.ablation_full.instance_fingerprint,
            self.full.instance_fingerprint,
        )


class PhaseTwoIntegrationAndStressTests(unittest.TestCase):
    """Phase 2 normalized evidence, logging, and repetition tests."""

    def test_phase_two_result_satisfies_every_exit_gate(self) -> None:
        result = validate_phase_two(PLUS_PATH, MINUS_PATH)
        primary = result["primary_comparison"]
        full = primary["full_pc"]
        fixed = primary["fixed_r"]
        ablation = result["secondary_ablation"]
        assertions = result["theorem_assertions"]

        self.assertTrue(primary["same_instance_object"])
        self.assertTrue(primary["same_initial_state_object"])
        self.assertTrue(primary["same_policy_object"])
        self.assertTrue(primary["same_transition_relation_object"])
        self.assertTrue(primary["same_instance_fingerprint"])
        self.assertTrue(primary["canonical_instance_unchanged"])
        self.assertEqual(full["minimum_closure_cost"], 1)
        self.assertEqual(full["evidence_acquisitions"], 0)
        self.assertEqual(full["representation_repairs"], 1)
        self.assertEqual(full["path"][0]["destination_representation"], "R1")
        self.assertEqual(full["closing_state"]["rank"], 1)
        self.assertEqual(full["closing_state"]["depth"], 1)
        self.assertEqual(full["closing_state"]["history"], ["e_star"])
        self.assertEqual(fixed["cost_classification"], "infinity")
        self.assertTrue(fixed["frontier_exhausted"])
        self.assertEqual(fixed["reached_representations"], ["R0"])
        self.assertEqual(ablation["role"], "transition_deletion_corroboration_only")
        self.assertFalse(ablation["full_pc"]["closed"])
        self.assertTrue(assertions["kappa_pi_I_equals_1"])
        self.assertTrue(assertions["kappa_pi_fix_r_I_is_infinity"])
        self.assertTrue(assertions["same_canonical_instance_for_primary_runs"])
        self.assertEqual(assertions["optimal_path_representation_repairs"], 1)
        self.assertEqual(
            assertions["optimal_path_environmental_evidence_acquisitions"], 0
        )
        self.assertTrue(assertions["closure_after_R0_to_R1"])
        self.assertTrue(
            assertions["representation_repair_preserved_nonrepresentation_state"]
        )
        self.assertTrue(assertions["fixed_r_frontier_exhausted"])
        self.assertTrue(
            assertions["fixed_r_evidence_operation_exhaustively_traversed"]
        )
        self.assertTrue(assertions["ablation_is_secondary_only"])
        self.assertTrue(
            assertions["ablation_evidence_operation_exhaustively_traversed"]
        )

    def test_all_fifteen_phase_two_console_steps_are_emitted_in_order(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("pc_checker")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            validate_phase_two(PLUS_PATH, MINUS_PATH)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        output = stream.getvalue()
        positions = [output.index(f"P2-{index:02d}") for index in range(1, 16)]
        self.assertEqual(positions, sorted(positions))

    def test_500_phase_two_runs_are_byte_identical_and_non_mutating(self) -> None:
        plus_before = PLUS_PATH.read_bytes()
        minus_before = MINUS_PATH.read_bytes()
        baseline = canonical_json(validate_phase_two(PLUS_PATH, MINUS_PATH))

        logger = logging.getLogger("pc_checker")
        previous_disabled = logger.disabled
        logger.disabled = True
        try:
            for _ in range(500):
                current = canonical_json(validate_phase_two(PLUS_PATH, MINUS_PATH))
                self.assertEqual(current, baseline)
        finally:
            logger.disabled = previous_disabled

        self.assertEqual(PLUS_PATH.read_bytes(), plus_before)
        self.assertEqual(MINUS_PATH.read_bytes(), minus_before)

    def test_evaluation_normalization_is_deterministic(self) -> None:
        raw, instance = load_instance(PLUS_PATH)
        fingerprint = canonical_fingerprint(raw)
        first = evaluation_to_json(
            evaluate_closure(instance, fingerprint, EvaluatorPolicyClass.FULL_PC)
        )
        second = evaluation_to_json(
            evaluate_closure(instance, fingerprint, EvaluatorPolicyClass.FULL_PC)
        )

        self.assertEqual(canonical_json(first), canonical_json(second))


def _readme_interpretation_sentences(text: str) -> list[str]:
    """Split the README body into interpretation sentences."""

    body = text
    if body.startswith("#"):
        body = body.split("\n", 1)[1]
    body = body.strip()
    return [part.strip() for part in re.split(r"(?<=\.)\s+", body) if part.strip()]


def _run_checker(
    cwd: Path,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke the repository checker as a subprocess."""

    command = [sys.executable, str(CHECKER_PATH if cwd == ROOT else cwd / "checker.py")]
    if extra_args:
        command.extend(extra_args)
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


class PhaseThreeArtifactAndCliTests(unittest.TestCase):
    """CLI, schema, fail-closed, and checked-in artifact tests."""

    def test_clean_repository_root_cli_succeeds(self) -> None:
        completed = _run_checker(ROOT)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(RESULT_PATH.is_file())
        self.assertIn("P3-01", completed.stderr)
        self.assertIn("P3-20", completed.stderr)
        self.assertNotIn("P3-ERROR", completed.stderr)

    def test_two_cli_runs_leave_result_json_byte_identical(self) -> None:
        first = _run_checker(ROOT)
        first_bytes = RESULT_PATH.read_bytes()
        second = _run_checker(ROOT)
        second_bytes = RESULT_PATH.read_bytes()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first_bytes, second_bytes)

    def test_result_json_independently_reasserts_every_acceptance_value(self) -> None:
        document = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        acceptance = document["acceptance"]
        causal = document["causal_invariants"]
        phase_one = document["phase_one"]
        phase_two = document["phase_two"]
        primary = phase_two["primary_comparison"]
        full_pc = primary["full_pc"]
        fixed_r = primary["fixed_r"]
        ablation = phase_two["secondary_ablation"]
        assertions = phase_two["theorem_assertions"]
        semantics = causal["representation_semantics"]

        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(
            document["artifact_kind"], "executable_matched_theorem_witness"
        )
        self.assertEqual(document["reproduction_command"], REPRODUCTION_COMMAND)
        self.assertFalse(document["claim_scope"]["statistical_validation"])
        self.assertFalse(document["claim_scope"]["prevalence_evidence"])
        self.assertFalse(document["claim_scope"]["deployment_evidence"])
        self.assertEqual(document["inputs"]["canonical_instance"], "instance_plus.json")
        self.assertEqual(
            document["inputs"]["canonical_instance_sha256"],
            "106c978c111bd348bf5fd561a0e7487b775a94e2c720f7ad9ddf593c4526d09a",
        )
        self.assertTrue(causal["logged_before_search"])
        self.assertTrue(causal["all_passed"])
        self.assertTrue(causal["evidence_history"]["e_star_in_initial_history"])
        self.assertTrue(causal["evidence_history"]["e_star_valid"])
        self.assertTrue(
            causal["evidence_actions_outcomes_and_costs"][
                "canonical_and_ablation_evidence_actions_identical"
            ]
        )
        self.assertTrue(causal["controller"]["canonical_and_ablation_controller_identical"])
        self.assertTrue(causal["authority"]["canonical_and_ablation_authority_identical"])
        self.assertTrue(causal["policies"]["Pi"])
        self.assertTrue(causal["policies"]["Pi_eff"])
        self.assertTrue(causal["policies"]["Pi_epi"])
        self.assertTrue(causal["policies"]["terminal_rule"])
        self.assertTrue(
            causal["world_and_target_function"][
                "canonical_and_ablation_target_function_identical"
            ]
        )
        self.assertTrue(
            causal["initial_representation"]["canonical_initial_representation_is_R0"]
        )
        self.assertTrue(causal["costs"]["representation_repair_cost_is_1"])
        self.assertTrue(semantics["e_star_already_admitted_and_valid"])
        self.assertTrue(semantics["r0_aliases_relevant_distinction"])
        self.assertTrue(semantics["r1_reads_admitted_history_only"])
        self.assertEqual(acceptance["kappa_pi_I"], 1)
        self.assertTrue(acceptance["kappa_pi_I_equals_1"])
        self.assertIsNone(acceptance["kappa_pi_fix_r_I"])
        self.assertEqual(acceptance["kappa_pi_fix_r_I_classification"], "infinity")
        self.assertTrue(acceptance["kappa_pi_fix_r_I_is_infinity"])
        self.assertTrue(acceptance["full_pc_closed"])
        self.assertEqual(acceptance["full_pc_cost_classification"], "finite")
        self.assertEqual(acceptance["full_pc_steps"], 1)
        self.assertEqual(acceptance["full_pc_evidence_acquisitions"], 0)
        self.assertEqual(acceptance["full_pc_representation_repairs"], 1)
        self.assertEqual(acceptance["full_pc_reachable_state_count"], 4)
        self.assertEqual(acceptance["full_pc_explored_state_count"], 4)
        self.assertTrue(acceptance["full_pc_frontier_exhausted"])
        self.assertFalse(acceptance["fixed_r_closed"])
        self.assertEqual(acceptance["fixed_r_reachable_state_count"], 2)
        self.assertEqual(acceptance["fixed_r_explored_state_count"], 2)
        self.assertTrue(acceptance["fixed_r_frontier_exhausted"])
        self.assertTrue(acceptance["same_canonical_instance_fingerprint"])
        self.assertTrue(acceptance["same_canonical_instance_object"])
        self.assertEqual(
            acceptance["secondary_ablation_structural_diff"],
            ["representation_actions[0].enabled"],
        )
        self.assertTrue(acceptance["secondary_ablation_exactly_one_difference"])
        self.assertEqual(
            acceptance["secondary_ablation_role"],
            "transition_deletion_corroboration_only",
        )
        self.assertTrue(acceptance["e_star_already_admitted_and_valid"])
        self.assertTrue(acceptance["r0_aliases_relevant_distinction"])
        self.assertTrue(acceptance["r1_reads_admitted_history_only"])
        self.assertTrue(acceptance["causal_invariants_all_passed"])
        self.assertTrue(acceptance["all_passed"])
        self.assertEqual(full_pc["policy_class"], "full_pc")
        self.assertEqual(full_pc["minimum_closure_cost"], 1)
        self.assertEqual(full_pc["initial_alternative_count"], 2)
        self.assertEqual(full_pc["closing_alternative_count"], 1)
        self.assertEqual(full_pc["initial_alternatives"], ["w_target_absent", "w_target_present"])
        self.assertEqual(full_pc["closing_alternatives"], ["w_target_present"])
        self.assertEqual(full_pc["path"][0]["action_id"], "repair_R0_to_R1")
        self.assertEqual(full_pc["initial_admitted_action_count"], 2)
        self.assertEqual(full_pc["initial_excluded_action_count"], 0)
        self.assertEqual(fixed_r["policy_class"], "fixed_r")
        self.assertEqual(fixed_r["cost_classification"], "infinity")
        self.assertIsNone(fixed_r["minimum_closure_cost"])
        self.assertEqual(fixed_r["initial_admitted_action_count"], 1)
        self.assertEqual(fixed_r["initial_excluded_actions"], ["repair_R0_to_R1"])
        self.assertEqual(fixed_r["reached_representations"], ["R0"])
        self.assertEqual(
            ablation["structural_diff"],
            list(EXPECTED_ABLATION_STRUCTURAL_DIFF),
        )
        self.assertFalse(ablation["full_pc"]["closed"])
        self.assertTrue(assertions["kappa_pi_I_equals_1"])
        self.assertTrue(assertions["kappa_pi_fix_r_I_is_infinity"])
        self.assertEqual(phase_one["full_pc_admissible_actions"][1], "repair_R0_to_R1")
        self.assertNotIn("Infinity", RESULT_PATH.read_text(encoding="utf-8"))

    def test_result_json_has_no_timestamps_paths_or_nonstandard_numbers(self) -> None:
        text = RESULT_PATH.read_text(encoding="utf-8")
        document = json.loads(text)

        self.assertNotIn("timestamp", json.dumps(document).lower())
        self.assertNotIn("C:\\", text)
        self.assertNotIn("/Users/", text)
        self.assertNotIn("Infinity", text)
        self.assertNotIn("NaN", text)
        self.assertNotRegex(text, r"\d{4}-\d{2}-\d{2}T")

    def test_corrupt_input_in_temp_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copy(CHECKER_PATH, root / "checker.py")
            shutil.copy(PLUS_PATH, root / "instance_plus.json")
            shutil.copy(MINUS_PATH, root / "instance_minus.json")
            (root / "instance_plus.json").write_text("{", encoding="utf-8")
            completed = _run_checker(root)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("P3-ERROR", completed.stderr)
            self.assertFalse((root / "result.json").exists())

    def test_deleted_input_in_temp_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copy(CHECKER_PATH, root / "checker.py")
            shutil.copy(MINUS_PATH, root / "instance_minus.json")
            completed = _run_checker(root)

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("P3-ERROR", completed.stderr)
            self.assertFalse((root / "result.json").exists())

    def test_readme_is_five_to_eight_sentences_and_contains_exact_command(self) -> None:
        text = README_PATH.read_text(encoding="utf-8")
        sentences = _readme_interpretation_sentences(text)

        self.assertGreaterEqual(len(sentences), 5)
        self.assertLessEqual(len(sentences), 8)
        self.assertIn(REPRODUCTION_COMMAND, text)
        self.assertIn("executable matched theorem witness", text)
        self.assertIn("not statistical validation", text)
        self.assertIn("prevalence evidence", text)
        self.assertIn("deployment evidence", text)

    def test_all_twenty_phase_three_console_steps_are_emitted_in_order(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("pc_checker")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            try:
                validate_phase_three(PLUS_PATH, MINUS_PATH, output)
                self.assertTrue(output.is_file())
            finally:
                logger.removeHandler(handler)
                logger.setLevel(previous_level)

        output_text = stream.getvalue()
        positions = [output_text.index(f"P3-{index:02d}") for index in range(1, 21)]
        self.assertEqual(positions, sorted(positions))

    def test_phase_three_invariants_are_logged_before_search(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("pc_checker")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            try:
                validate_phase_three(PLUS_PATH, MINUS_PATH, output)
            finally:
                logger.removeHandler(handler)
                logger.setLevel(previous_level)

        output_text = stream.getvalue()
        self.assertLess(
            output_text.index("P3-15"),
            output_text.index("P3-17"),
        )
        self.assertLess(
            output_text.index("P3-15"),
            output_text.index("P2-05"),
        )

    def test_repeated_phase_three_documents_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first_path = Path(temporary) / "first.json"
            second_path = Path(temporary) / "second.json"
            logger = logging.getLogger("pc_checker")
            previous_disabled = logger.disabled
            logger.disabled = True
            try:
                validate_phase_three(PLUS_PATH, MINUS_PATH, first_path)
                validate_phase_three(PLUS_PATH, MINUS_PATH, second_path)
            finally:
                logger.disabled = previous_disabled
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())


class PhaseFourOracleAndCloseoutTests(unittest.TestCase):
    """Independent oracle agreement and Phase 4 acceptance-audit tests."""

    def test_oracle_module_does_not_use_production_search(self) -> None:
        tree = ast.parse(ORACLE_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        called: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
        banned = {
            "exhaustive_uniform_cost",
            "evaluate_closure",
            "pc_successors",
            "apply_evidence_action",
            "apply_representation_action",
            "action_policy_view",
            "legal_actions",
            "successor_representation",
            "heapq",
        }
        self.assertEqual(imported & banned, set())
        self.assertEqual(called & banned, set())
        self.assertIn("deque", imported | called)

    def test_oracle_agrees_with_full_pc_on_canonical_I(self) -> None:
        raw, instance = load_instance(PLUS_PATH)
        production = evaluate_closure(
            instance, canonical_fingerprint(raw), EvaluatorPolicyClass.FULL_PC
        )
        oracle = enumerate_finite_graph(instance, EvaluatorPolicyClass.FULL_PC)

        self.assertEqual(oracle.closed, production.closed)
        self.assertEqual(oracle.minimum_closure_cost, production.minimum_closure_cost)
        self.assertEqual(oracle.frontier_exhausted, production.frontier_exhausted)
        self.assertEqual(
            oracle.reachable_state_count, production.reachable_state_count
        )
        self.assertTrue(oracle.closed)
        self.assertEqual(oracle.minimum_closure_cost, 1)
        self.assertEqual(oracle.reachable_state_count, 4)

    def test_oracle_agrees_with_fixed_r_on_canonical_I(self) -> None:
        raw, instance = load_instance(PLUS_PATH)
        production = evaluate_closure(
            instance, canonical_fingerprint(raw), EvaluatorPolicyClass.FIXED_R
        )
        oracle = enumerate_finite_graph(instance, EvaluatorPolicyClass.FIXED_R)

        self.assertEqual(oracle.closed, production.closed)
        self.assertEqual(oracle.minimum_closure_cost, production.minimum_closure_cost)
        self.assertEqual(oracle.frontier_exhausted, production.frontier_exhausted)
        self.assertEqual(
            oracle.reachable_state_count, production.reachable_state_count
        )
        self.assertFalse(oracle.closed)
        self.assertIsNone(oracle.minimum_closure_cost)
        self.assertTrue(oracle.frontier_exhausted)
        self.assertEqual(oracle.reachable_state_count, 2)

    def test_oracle_agrees_with_labeled_transition_deletion_ablation(self) -> None:
        raw, instance = load_instance(MINUS_PATH)
        production = evaluate_closure(
            instance, canonical_fingerprint(raw), EvaluatorPolicyClass.FULL_PC
        )
        oracle = enumerate_finite_graph(instance, EvaluatorPolicyClass.FULL_PC)

        self.assertEqual(oracle.closed, production.closed)
        self.assertEqual(oracle.minimum_closure_cost, production.minimum_closure_cost)
        self.assertEqual(oracle.frontier_exhausted, production.frontier_exhausted)
        self.assertEqual(
            oracle.reachable_state_count, production.reachable_state_count
        )
        self.assertFalse(oracle.closed)
        self.assertIsNone(oracle.minimum_closure_cost)
        self.assertTrue(oracle.frontier_exhausted)
        self.assertEqual(oracle.reachable_state_count, 2)

    def test_oracle_three_runs_match_checked_in_result_json(self) -> None:
        _, canonical = load_instance(PLUS_PATH)
        _, ablation = load_instance(MINUS_PATH)
        oracle = evaluate_required_oracle_runs(canonical, ablation)
        document = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
        primary = document["phase_two"]["primary_comparison"]
        ablation_result = document["phase_two"]["secondary_ablation"]["full_pc"]

        self.assertEqual(
            oracle["full_pc"].minimum_closure_cost,
            primary["full_pc"]["minimum_closure_cost"],
        )
        self.assertEqual(oracle["full_pc"].closed, primary["full_pc"]["closed"])
        self.assertEqual(
            oracle["full_pc"].reachable_state_count,
            primary["full_pc"]["reachable_state_count"],
        )
        self.assertEqual(oracle["fixed_r"].closed, primary["fixed_r"]["closed"])
        self.assertEqual(
            oracle["fixed_r"].reachable_state_count,
            primary["fixed_r"]["reachable_state_count"],
        )
        self.assertTrue(oracle["fixed_r"].frontier_exhausted)
        self.assertEqual(oracle["ablation_full_pc"].closed, ablation_result["closed"])
        self.assertEqual(
            oracle["ablation_full_pc"].reachable_state_count,
            ablation_result["reachable_state_count"],
        )

    def test_representation_repair_has_no_environment_read(self) -> None:
        _, instance = load_instance(PLUS_PATH)
        start = initial_search_state(instance)
        repair = instance.representation_actions[0]
        successor, transition = apply_representation_action(start, repair)

        self.assertIs(successor.history, start.history)
        self.assertIs(successor.admitted_evidence, start.admitted_evidence)
        self.assertEqual(transition.acquired_evidence, ())
        self.assertEqual(repair.reads, "admitted_history_only")
        self.assertFalse(hasattr(repair, "outcomes"))

    def test_fixed_r_is_filter_only_and_ablation_is_singleton(self) -> None:
        plus_raw, plus = load_instance(PLUS_PATH)
        minus_raw, minus = load_instance(MINUS_PATH)
        full_view = action_policy_view(
            plus, plus.initial_state.representation, EvaluatorPolicyClass.FULL_PC
        )
        fixed_view = action_policy_view(
            plus, plus.initial_state.representation, EvaluatorPolicyClass.FIXED_R
        )

        self.assertIs(full_view.instance, fixed_view.instance)
        self.assertTrue(plus.representation_actions[0].enabled)
        self.assertEqual(
            structural_diff(plus_raw, minus_raw),
            EXPECTED_ABLATION_STRUCTURAL_DIFF,
        )
        self.assertIsNot(minus, plus)

    def test_phase_four_audit_evidence_and_console_order(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("pc_checker")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            evidence = validate_phase_four(PLUS_PATH, MINUS_PATH, RESULT_PATH, README_PATH)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        self.assertTrue(evidence["all_passed"])
        self.assertTrue(evidence["representation_repair_has_no_environment_read"])
        self.assertTrue(evidence["primary_same_canonical_object"])
        self.assertTrue(evidence["primary_same_canonical_serialization"])
        self.assertTrue(evidence["fixed_r_enforced_only_by_evaluator_filtering"])
        self.assertTrue(evidence["secondary_ablation_has_no_unapproved_diff"])
        self.assertTrue(evidence["infinity_tied_to_exhausted_finite_traversal"])
        self.assertTrue(evidence["claim_scope_has_no_widened_empirical_claim"])
        matrix = evidence["traceability_matrix"]
        self.assertTrue(all(matrix.values()))
        output = stream.getvalue()
        positions = [output.index(f"P4-{index:02d}") for index in range(1, 11)]
        self.assertEqual(positions, sorted(positions))

    def test_oracle_console_steps_are_emitted(self) -> None:
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("pc_checker")
        previous_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            _, canonical = load_instance(PLUS_PATH)
            _, ablation = load_instance(MINUS_PATH)
            evaluate_required_oracle_runs(canonical, ablation)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        output = stream.getvalue()
        for token in (
            "P4-ORACLE-01",
            "P4-ORACLE-02",
            "P4-ORACLE-03",
            "P4-ORACLE-04",
            "P4-ORACLE-05",
        ):
            self.assertIn(token, output)

    def test_repeated_oracle_runs_are_deterministic(self) -> None:
        _, canonical = load_instance(PLUS_PATH)
        _, ablation = load_instance(MINUS_PATH)
        logger = logging.getLogger("pc_checker")
        previous_disabled = logger.disabled
        logger.disabled = True
        try:
            first = evaluate_required_oracle_runs(canonical, ablation)
            for _ in range(50):
                current = evaluate_required_oracle_runs(canonical, ablation)
                self.assertEqual(current, first)
        finally:
            logger.disabled = previous_disabled


if __name__ == "__main__":
    unittest.main()
