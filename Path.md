# Implementation path

## Document purpose

This file is the live, evidence-backed ledger for implementing `WorkPlan.md`. It records what was actually implemented, how it was verified, and whether execution follows the plan. It must be updated during each implementation phase. Planned work is not represented as completed work.

Status vocabulary:

- `Not started` — no implementation work for the phase has begun.
- `In progress` — implementation has begun but one or more exit gates remain unmet.
- `Complete` — all phase exit gates have objective evidence.
- `Blocked` — a specific external or technical blocker prevents progress.
- `Deviated` — actual implementation differs from `WorkPlan.md`; the deviation must be explained and resolved or accepted explicitly.

## Planning baseline

**Status:** Complete

**Source studied**

- Document: `PC_Matched_Complementarity_Checker_Implementation_Spec.docx`
- Source SHA-256: `3FD95DBEE2A4E5D9F418334C5DE4C59186FEC6306F228C4BCA714A47B6D39F09`
- Source conclusion: implement a deterministic matched finite checker; no AI model or training is required.

**Repository baseline**

- Repository: `theorem-2-validation-artifact` (author repository URL removed for blind review)
- Branch: `main`
- Baseline commit: `<AUTHOR_REPO_COMMIT_001>` (`Initial commit`)
- Baseline tracked artifact: `LICENSE`

**Files created**

- `WorkPlan.md`
- `Path.md`

**Work performed**

- Read the complete specification after extracting its OOXML document text.
- Reduced the requirements into a canonical-instance theorem contract, a secondary matched-ablation contract, a finite-state search contract, deterministic output requirements, and acceptance assertions.
- Selected four phases because the requested artifact is deliberately minimal and the specification explicitly prohibits scope expansion.
- Added source-to-deliverable traceability and non-ML anti-hard-coding verification.
- Explicitly excluded model training and model benchmarks because the source says no AI model is required and prohibits triggering a new benchmark or LLM evaluation.

**Verification evidence**

- Every requirement from source sections 1–7 is represented in `WorkPlan.md`'s implementation contract, phase gates, or traceability matrix.
- The plan includes all required artifacts: `checker.py`, `instance_plus.json`, `instance_minus.json`, `result.json`, and `README.md`, plus focused tests and the two requested planning/ledger files.
- The corrected plan requires one canonical instance for both evaluator policy classes, an exact singleton diff only for the secondary ablation, admitted `e_star`, zero new environmental evidence, minimum repair cost `1`, same-instance fixed-`R` exhaustion, deterministic one-command output, and narrow theorem-witness language.

**Plan conformance**

- Followed the requested planning scope after incorporating the documented same-instance mathematical correction.
- At the planning baseline no implementation code existed; completed Phase 1 work is recorded below.
- The original two-instance interpretation was superseded and is documented in the Phase 1 audit and deviation log.

**Temporary analysis artifact**

- `.spec-extracted.txt` was generated only to read the Word document, then removed after analysis. It is not a deliverable and is not present in the repository handoff.

## Phase 1 — Define the canonical instance and evaluator policy classes

**Status:** Complete

**Planned scope and gates**

See the corrected `WorkPlan.md`, Phase 1. Completion requires one immutable canonical theorem instance `I`, typed full-PC and fixed-`R` evaluator policy classes over that same instance, strict schema and closure semantics, a separately labeled one-difference ablation, exhaustive protected-ablation mutation tests, and proof that `R0` is non-closing while `R1` closes from unchanged admitted evidence.

**Files created/modified**

- `instance_plus.json` — canonical theorem instance `I`; its underlying transition relation keeps `R0 -> R1` enabled.
- `instance_minus.json` — secondary transition-deletion ablation only; it is not the input used to represent the fixed-`R` evaluator.
- `checker.py` — strict schema parser, immutable typed domain model, `EvaluatorPolicyClass`, same-instance action filtering, semantic validation, canonical fingerprinting, recursive ablation comparison, representation projection, policy-compatible alternative evaluation, Phase 1 console instrumentation, and Phase 1 command entry point.
- `tests/test_checker.py` — 20 standard-library tests covering schema validity, immutability, action typing, same-instance policy-class semantics, closure semantics, ablation mutations, logging order, deterministic repetition, and input preservation.
- `WorkPlan.md` — corrected primary theorem comparison and all downstream Phase 2–4 requirements.
- `Path.md` — this implementation record and compliance audit.

**Actual code and algorithmic decisions**

- All external JSON objects are accepted only with exact key sets. Missing and unknown fields fail closed through `ValidationError`.
- JSON scalar validation is strict: booleans are not accepted as integers, costs/rank/depth are non-negative integers, identifiers are non-empty strings, and action kinds and representations are finite enums.
- JSON is parsed into frozen, slotted dataclasses. Arrays become tuples and the policy reference mapping is read-only. Tests prove the resulting domain model cannot be mutated.
- `EvidenceAction` and `RepresentationAction` are separate frozen dataclasses joined only by the `Action` type alias. The representation action contains no evidence outcome field.
- `instance_plus.json` is designated canonical `I`. The finite world contains `w_target_absent` and `w_target_present`; they differ on `target_label`. Canonical `I` contains the target function, controller `M0`, authority, complete policy bundle, evidence operation/outcome/cost, initial state, representations, and enabled repair transition used by both primary evaluator policy classes.
- `e_star` is present in initial history and admitted evidence in both files, and validation requires it to be valid, admitted, target-bearing, and sourced from `initial_history`.
- `R0` returns a represented certificate with no target label. Consequently both hypotheses remain compatible and `|A_Pi(C^R0)| = 2`.
- `R1` filters only the immutable initial history by the immutable admitted-evidence identifiers and exposes the unique admitted target label. It has no callback, parameter, or action path for environmental acquisition. Consequently only `w_target_present` remains and `|A_Pi(C^R1)| = 1`.
- `EvaluatorPolicyClass.FULL_PC` and `EvaluatorPolicyClass.FIXED_R` are explicit enum members. `action_policy_view` receives canonical `I`, current representation, and one policy class.
- `legal_actions` derives action legality from canonical `I` without changing it. At `R0`, full PC admits `observe_alias_preserving_signal` and `repair_R0_to_R1`.
- Fixed `R` is implemented as the restriction `R(T(sigma, a)) = R0`. `successor_representation` computes the successor representation; `action_policy_view` filters the already-legal full-PC action set against canonical `I.initial_state.representation`. At `R0`, it retains `observe_alias_preserving_signal` and excludes `repair_R0_to_R1`.
- Both `ActionPolicyView` objects retain the exact same canonical `Instance` reference. Therefore their initial state, policy, costs, evidence outcomes, and transition relation are also the same objects. Machine-readable Phase 1 evidence reports each identity invariant and the canonical SHA-256 fingerprint.
- Fixed-`R` projection does not set `enabled = false`, copy the instance, rewrite an action, or change the transition relation. Tests assert the canonical repair remains enabled before and after both policy projections.
- `instance_minus.json` remains a secondary ablation. `structural_diff` checks every object key, array index, scalar value, and runtime JSON type, and `validate_ablation_pair` requires its sole difference from canonical `I` to be `representation_actions[0].enabled`.
- Phase 2 graph traversal, minimum-cost evaluation, and path reconstruction were intentionally not implemented in Phase 1.

**Console instrumentation and identifying comments**

Python has no `console.log`; the professional language-equivalent is the standard-library `logging` API. Each Phase 1 console statement is immediately preceded by an identifying comment in `checker.py`:

| Step | Comment line | Log line(s) | Purpose |
| --- | ---: | ---: | --- |
| `P1-01` | 1236 | 1237 | Phase 1 validation started |
| `P1-02` | 1238 | 1239 | Load canonical instance `I` |
| `P1-03` | 1241 | 1242 | Canonical instance strict validation passed |
| `P1-04` | 1249 | 1250 | Full-PC actions projected from canonical `I` |
| `P1-05` | 1256 | 1257 | Fixed-`R` actions projected from canonical `I` |
| `P1-06` | 1292 | 1293 | Same-instance policy restriction passed |
| `P1-07` | 1294 | 1295 | Load secondary ablation |
| `P1-08` | 1297 | 1298 | Ablation strict validation passed |
| `P1-09` | 1305 | 1306 | Exact ablation structural diff passed |
| `P1-10` | 1310 | 1311–1314 | `R0` non-closure passed and count reported |
| `P1-11` | 1318 | 1319–1322 | `R1` closure passed and count reported |
| `P1-12` | 1330 | 1331 | Ablation history/evidence invariants passed |
| `P1-13` | 1376 | 1377 | All corrected Phase 1 gates completed |

Test `test_all_thirteen_identified_console_steps_are_emitted_in_order` verifies that `P1-01` through `P1-13` are all emitted and ordered. Controlled CLI failure logging remains a Phase 3 responsibility.

**Commands and observed results**

- `python -m py_compile checker.py tests/test_checker.py` — exit code `0`; no syntax errors.
- Independent `ast.parse` over both Python files — `AST validation passed for 2 Python files`.
- Historical Phase 1 development harness: `python checker.py` exited `0` and emitted all 13 Phase 1 logs with the documented evidence. That temporary module entry point was removed during Phase 2 compliance correction so the repository-root CLI remains exclusively a Phase 3 deliverable; current Phase 1 logging is exercised through `validate_phase_one` and its tests.
- `python -m unittest discover -s tests -v` — final corrected suite exit code `0`; `Ran 20 tests in 0.414s`; `OK`.
- Determinism stress test — 500 complete canonical load, dual-policy projection, ablation validation/diff, and representation-evaluation cycles yielded one identical canonical result and left both JSON files byte-identical.
- Independent subprocess stream comparison — two complete corrected executions produced byte-identical stdout (`1418` bytes) and byte-identical stderr (`763` bytes).
- Direct Python trailing-whitespace scan over all six untracked deliverables — `direct whitespace scan passed for 6 deliverables`. This direct scan is used because `git diff --check` does not inspect untracked files.
- Import-location audit — all imports occur at module tops; no inline imports.
- Phase-scope search — no search/traversal functions or `heapq`/`deque` usage exists, confirming Phase 2 was not implemented prematurely.

**Stress-test coverage**

- 20 test methods and 47 protected-ablation-leaf mutation subtests.
- Two primary-comparison tests prove both action-policy views retain the same canonical object and fixed `R` equals an explicit filter of full-PC legal actions by `R(T(sigma, a)) = R0`.
- The tests assert canonical repair legality remains `true` after fixed-`R` projection and that both policy classes retain the same representation-preserving evidence action.
- The secondary ablation mutation test recursively enumerates every scalar leaf in `instance_minus.json`, excludes only the approved `representation_actions[0].enabled` ablation leaf, asserts the expected protected-leaf count of 47, mutates each leaf individually, and requires ablation validation to reject every mutation.
- Negative tests cover unknown fields, missing fields, strict scalar types, unknown enum values, invalid admitted evidence, extra structural differences, and reversed intervention direction.
- Semantic tests check exact alternatives under both representations and prove history and admitted evidence are unchanged by `R1`.
- Repetition tests check deterministic evidence and byte-level preservation of both input files.

**Acceptance evidence**

1. **Canonical `I` and the secondary ablation parse and pass strict validation:** proven by `test_canonical_and_ablation_files_load_and_validate`, direct `validate_phase_one` execution, and the 500-run validation stress test.
2. **Full PC and fixed `R` operate on the same canonical object:** both `ActionPolicyView.instance` references are identical; explicit evidence also confirms identical initial-state, policy, and transition-relation references and stable canonical SHA-256.
3. **Policy classes differ only by admissibility:** full PC admits `observe_alias_preserving_signal` and `repair_R0_to_R1`; fixed `R` admits `observe_alias_preserving_signal` and excludes the repair because its successor has `R1`. Canonical repair legality remains enabled.
4. **Each protected ablation field rejects mutation:** `test_every_protected_ablation_leaf_rejects_mutation` discovers and individually mutates all 47 protected JSON leaves; extra-diff and reversed-direction tests add independent negative coverage.
5. **The secondary ablation has exactly one difference:** `structural_diff` returns only `representation_actions[0].enabled`; asserted by unit/integration tests and printed under the explicit `ablation_structural_diff` field.
6. **`R0` is non-closing and `R1` closes with unchanged history and `E`:** exact alternatives are respectively `("w_target_absent", "w_target_present")` and `("w_target_present",)`; semantic and integration tests assert both counts and invariants.
7. **JSON round trips and source preservation:** canonical JSON re-parses to the original structures, 500 iterations are stable, and before/after input bytes are equal.

**Plan conformance**

- Scope, files, code method, and every gate in the corrected `WorkPlan.md` Phase 1 are implemented.
- The primary theorem setup is now one canonical instance under two evaluator policy classes. No primary result is inferred from the ablation instance.
- No Phase 2 search behavior was present when Phase 1 was closed; Phase 2 implementation is recorded separately below.
- The implementation uses only the Python standard library.

**Deviations**

- The user requested `console.log`, but the planned implementation language is Python. Literal `console.log` would be invalid Python. The standard `logging.Logger.info` equivalent was used, preserving the requested console visibility and adding structured step identifiers and adjacent comments. This is a language-syntax adaptation, not a behavioral or WorkPlan deviation.

**Audit observation**

- An initial PowerShell check merged stdout and stderr and observed nondeterministic interleaving because logging writes to stderr while JSON evidence writes to stdout. An independent subprocess check compared the streams separately and proved each stream byte-identical across runs. No implementation defect was found.
- The first independent compliance audit found incomplete per-leaf mutation coverage, an unwrapped action-kind enum error, and a missing adjacent failure-log comment. All three findings were corrected: all 47 protected leaves are now mutated independently, invalid action kinds raise `ValidationError`, and `P1-ERROR` has an identifying comment. The full suite passed after correction.
- A subsequent mathematical review identified that the original plan treated `instance_minus.json` as the primary fixed-`R` problem, which changed the underlying transition relation and therefore compared two different closure problems. That interpretation was incorrect for the intended Theorem 2 Part I realization.
- The correction designates `I := instance_plus.json`, keeps `R0 -> R1` legal, and applies `FULL_PC` versus `FIXED_R` as evaluator policy classes over the same `Instance` object. `instance_minus.json` is retained only as a secondary transition-deletion ablation.
- Phase 1 proves the corrected action-set semantics and object/transition invariants. The numerical computations `kappa_Pi(I) = 1` and `kappa_Pi_fixR(I) = infinity` remain Phase 2 obligations and have not been claimed as Phase 1 results.
- The first correction audit found three documentation defects: a false BFS equivalence despite unequal action costs, ambiguous Phase 4 oracle wording, and a vacuous `git diff --check` claim for untracked files. `WorkPlan.md` now requires weighted uniform-cost search and explicitly names both canonical policy-class oracle runs plus the separate ablation; whitespace evidence now comes from a direct scan of every deliverable.

**Risks/blockers:** None identified. Phase 1 remains complete.

## Phase 2 — Implement exhaustive minimum-cost closure evaluation

**Status:** Complete

**Planned scope and gates**

See the corrected `WorkPlan.md`, Phase 2. Completion requires deterministic uniform-cost exhaustive traversal of canonical `I` under both `FULL_PC` and `FIXED_R`, a one-repair/zero-evidence full-PC optimum, an empty-frontier proof of fixed-`R` infinity on the same instance, a separately labeled full-PC ablation run on `instance_minus.json`, and algorithm tests on distinct finite fixtures.

**Files created/modified**

- `checker.py` — added finite search-state types, semantic keys, typed transitions, separate evidence/representation transition functions, deterministic generic uniform-cost traversal, PC successor generation, dynamic closure evaluation, normalized evaluation output, same-instance theorem assertions, secondary ablation evaluation, and Phase 2 console instrumentation.
- `tests/test_checker.py` — expanded from 20 to 35 standard-library tests with weighted-graph minimality, stale-entry, negative-cost, cycle/exhaustion, typed-successor, state-preservation, theorem, ablation, logging, and 500-run determinism coverage.
- `Path.md` — updated Phase 1 line references after source growth and added this detailed Phase 2 ledger.

**State and transition model**

- `SearchState` carries certificate state `C`, representation `R`, controller `M`, authority, admitted evidence `E`, history, accumulated cost, rank, and depth.
- `SemanticStateKey` includes every future-relevant semantic field but intentionally excludes accumulated cost, rank, and depth. This allows a higher-cost or cyclic route to the same semantic state to be rejected by the best-cost map.
- `SearchTransition` records action identifier/type, action cost, source/destination representation, newly acquired evidence, cumulative cost, resulting rank, and resulting depth.
- `apply_evidence_action` and `apply_representation_action` are separate typed functions. Evidence application canonicalizes evidence/history and records only newly acquired environmental records. Representation application changes only `R`, accumulated cost, rank, and depth; it reuses the exact certificate, controller, authority, admitted-evidence, and history objects.
- The canonical representation repair costs `1`, moves `R0 -> R1`, increments rank/depth from `0` to `1`, and records no environmental evidence acquisition.
- The evidence operation costs `2`, preserves `R`, adds declared outcome `e_aux`, and remains traversable under both primary evaluator policies.

**Uniform-cost traversal**

- `exhaustive_uniform_cost` uses a `heapq` frontier ordered by accumulated cost, stable semantic-state string, and deterministic insertion sequence.
- A best-cost map stores the least discovered cost for each semantic key. A lower-cost update replaces the state and predecessor; equal/higher-cost successors are deduplicated.
- Queue entries whose cost no longer equals the best-cost map are counted and rejected as stale.
- Edge costs must be integers `>= 0`; invalid negative costs fail closed through `ValidationError`.
- Predecessors are retained by semantic key and reversed to reconstruct the exact minimum-cost path after the first settled closing state.
- The first closing state settled by the heap is retained as the proven minimum, but traversal continues until the finite frontier is empty so reachable and expanded counters describe the complete legal graph rather than the prefix before closure.
- Reachable, expanded, stale-entry, and deduplicated-successor counts are retained. Reached states are normalized into deterministic semantic-key order. An infinite result is emitted only when exhaustion found no closing state.
- Closure is evaluated dynamically from each state's represented admitted history via `compatible_hypotheses_for_state`; the search algorithm contains no instance-name or expected-cost special case.

**Primary same-instance theorem evaluation**

- Canonical `instance_plus.json` is loaded once and the same `Instance` object and SHA-256 fingerprint are passed first to `FULL_PC`, then to `FIXED_R`.
- Full PC and fixed `R` share exact initial-state, policy, evidence-action tuple, representation-action tuple, action costs, outcomes, and transition relation objects.
- Full PC generates every legal canonical successor. Fixed `R` uses the Phase 1 admissibility filter at successor generation and admits only actions satisfying `R(T(sigma, a)) = R0`.
- Full PC discovers the cost-`2` evidence successor and cost-`1` representation successor, then settles the representation successor first. It closes at minimum cost `1`.
- Full PC continues graph accounting after recording that minimum and exhausts all four reachable semantic states: `R0/E0`, `R0/E0+e_aux`, `R1/E0`, and `R1/E0+e_aux`.
- The optimal full-PC path is exactly one `repair_R0_to_R1` transition. It has one representation repair, zero environmental evidence acquisitions, final rank/depth `1`, unchanged history/admitted evidence/controller/authority, and sole alternative `w_target_present`.
- Fixed `R` traverses the representation-preserving evidence operation, reaches the `e_aux` state, rejects repeated acquisition as a semantic cycle, empties the frontier, and reports `minimum_closure_cost = null`, classification `infinity`, and `frontier_exhausted = true`.
- Fixed `R` reaches two semantic states, expands both, records at least one deduplicated successor, and reaches only `R0`.
- The primary raw canonical input remains byte/canonically unchanged after both evaluations.

**Secondary ablation**

- `instance_minus.json` is evaluated separately under `FULL_PC`.
- Its result is labeled `transition_deletion_corroboration_only`.
- It is not passed to the fixed-`R` evaluator and is not used to establish `kappa_Pi_fixR(I)`.
- The ablation traverses its evidence operation, exhausts two reachable states under `R0`, and is non-closing with classification `infinity`.

**Console instrumentation and identifying comments**

Python standard-library `LOGGER.info` is the language-equivalent of `console.log`. Every Phase 2 statement has an immediately preceding identifying comment:

| Step | Comment line | Log line(s) | Purpose |
| --- | ---: | ---: | --- |
| `P2-01` | 1471 | 1472 | Phase 2 evaluation started |
| `P2-02` | 1476 | 1477–1480 | Canonical `I` loaded with fingerprint |
| `P2-03` | 1483 | 1484–1487 | Secondary ablation loaded with fingerprint |
| `P2-04` | 1494 | 1495–1498 | Ablation boundary validated |
| `P2-05` | 1499 | 1500 | Full-PC search started on canonical `I` |
| `P2-06` | 1506 | 1507–1513 | Full-PC search result logged |
| `P2-07` | 1514 | 1515 | Fixed-`R` search started on the same `I` |
| `P2-08` | 1521 | 1522–1528 | Fixed-`R` exhaustion result logged |
| `P2-09` | 1547 | 1548 | Same-instance comparison validated |
| `P2-10` | 1549 | 1550 | Secondary ablation search started |
| `P2-11` | 1556 | 1557–1561 | Secondary ablation result logged |
| `P2-12` | 1587 | 1588 | `kappa_Pi(I) = 1` assertions passed |
| `P2-13` | 1604 | 1605 | `kappa_Pi_fixR(I) = infinity` assertions passed |
| `P2-14` | 1619 | 1620 | Secondary ablation assertions passed |
| `P2-15` | 1672 | 1673 | Phase 2 theorem evaluation completed |

Test `test_all_fifteen_phase_two_console_steps_are_emitted_in_order` verifies that `P2-01` through `P2-15` are emitted and ordered. Controlled CLI failure logging remains a Phase 3 responsibility.

**Commands and observed results**

- `python -m py_compile checker.py tests/test_checker.py` — exit code `0`.
- Independent `ast.parse` over both Python files — `AST validation passed for 2 Python files`.
- `python -m unittest discover -s tests -v` — final suite exit code `0`; `Ran 35 tests in 9.190s`; `OK` (runtime varies with concurrent IDE process load).
- Direct `validate_phase_two` invocation — returned normalized theorem evidence; the repository-root CLI is intentionally deferred to Phase 3.
- Focused theorem probe — `same_instance=True`, `same_fingerprint=True`; full PC `closed=True`, cost `1`, reachable/expanded `4/4`, exhausted `True`, evidence `0`, repairs `1`; fixed `R` `closed=False`, classification `infinity`, exhausted `True`, reachable states `2`; ablation `closed=False`, classification `infinity`, exhausted `True`.
- Normalized-object determinism check — two direct Phase 2 evaluations produced the same `3127`-byte canonical JSON object.
- `python checker.py` — exit code `0` with no output, confirming the Phase 3 CLI entry point is not implemented prematurely.
- Direct trailing-whitespace scan — passed for all six deliverables.

**Stress-test coverage**

- A structurally different weighted graph lists an expensive direct goal edge before a two-edge cheaper route. The evaluator returns the longer route at cost `3`, not the first-discovered direct route at cost `9`.
- A different cyclic graph reaches `start -> a -> b`, rejects both back edges, expands exactly three semantic states, and proves non-closure by frontier exhaustion.
- A stale-entry graph first discovers a state at cost `9`, improves it to cost `3`, and records exactly one rejected stale heap entry.
- A negative-edge fixture raises controlled `ValidationError`.
- Canonical successor tests independently inspect typed evidence and representation successors and their costs/outcomes.
- The fixed-`R` theorem test proves the evidence outcome was actually reached before exhaustion.
- The complete Phase 2 load/evaluate/assert/normalize pipeline ran 500 times with byte-identical normalized objects and byte-identical source JSON before/after.

**Acceptance evidence**

1. **`kappa_Pi(I) == 1`:** full PC closes with `minimum_closure_cost = 1`, finite classification, one step, and closing alternative `w_target_present`.
2. **Same canonical instance:** full/fixed evaluation objects retain the same `Instance`, initial-state, policy, evidence-action, and representation-action identities and identical fingerprint `106c978c111bd348bf5fd561a0e7487b775a94e2c720f7ad9ddf593c4526d09a`.
3. **One repair and zero evidence:** reconstructed path contains only `repair_R0_to_R1`; counters are repairs `1`, acquisitions `0`.
4. **Closure after `R0 -> R1`:** path source/destination are `R0`/`R1`; represented alternatives become exactly `("w_target_present",)`.
5. **Exact full-PC counters:** exhaustive accounting reports all four reachable and four expanded semantic states while preserving the first settled goal and minimum path.
6. **`kappa_Pi_fixR(I) == infinity`:** same canonical `I`, fixed-`R` filter, no closing state, `null` minimum cost, infinity classification, only `R0` reached, and empty frontier after both reachable states were expanded.
7. **Secondary ablation:** distinct ablation instance under full PC is separately labeled, non-closing, and exhausted; it is never substituted for fixed `R`.
8. **True weighted minimum:** the independent cost-`9` versus two-edge cost-`3` fixture returns cost `3`.
9. **Cycle/stale safety:** independent fixtures prove semantic-cycle deduplication, stale-entry rejection, and finite termination.
10. **Determinism:** 500 Phase 2 repetitions and direct canonical normalization are byte-identical.

**Plan conformance**

- Every Phase 2 scope item, code method, and exit gate in corrected `WorkPlan.md` has implementation and local test evidence.
- No CLI, `result.json`, or README was created; those remain Phase 3 responsibilities.
- The implementation uses only the Python standard library.

**Deviations:** None.

**Risks/blockers**

- The first audit found an undercounted full-PC reachable-state metric, Phase 3 CLI leakage, an overbroad `P2-15` comment, and a stale test-module description. All four findings were corrected before re-audit.
- The final independent re-audit found no remaining actionable findings and returned `PASS`. It independently reproduced full canonical cost `1` with `4/4` reachable/expanded states, fixed canonical non-closure with `2/2` states, full ablation non-closure with `2/2` states, all 35 passing tests, exact P1/P2 line tables, and absence of Phase 3 scope.
- No unresolved Phase 2 risks or blockers remain.

## Phase 3 — Produce the reproducible artifact and machine-readable proof

**Status:** Complete

**Planned scope and gates**

See `WorkPlan.md`, Phase 3. Completion requires the repository-root command `python checker.py`, pre-search causal-invariant validation and logging, atomic write of checked-in `result.json` only after both primary same-instance runs, the labeled ablation, and every acceptance assertion, fail-closed nonzero exit with no successful theorem result on contract failure, and a README whose interpretation is 5–8 sentences and states the exact one-command path.

**Files created/modified**

- `checker.py` — added the repository-root CLI (`parse_args`, `main`, `if __name__ == "__main__"`), pre-intervention causal-invariant evaluator, deterministic sorted/indented UTF-8 serializer, atomic `result.json` writer, Phase 3 acceptance assembler/asserter, and Phase 3 console instrumentation. `evaluation_to_json` was additively enriched with alternative counts, admitted/excluded action counts, and `explored_state_count` so each run result reports every WorkPlan §2.4 field. Search semantics were not changed.
- `result.json` — checked-in machine-readable witness containing both primary run results, the labeled ablation, pairwise causal invariants, and the acceptance block.
- `README.md` — exact command `python checker.py` and a 6-sentence theorem-witness-only interpretation.
- `tests/test_checker.py` — expanded from 35 to 45 standard-library tests covering clean CLI success, two-run byte identity, independent `result.json` re-assertion of every acceptance value, corrupt/missing-input fail-closed fixtures, README sentence count and wording, Phase 3 log order, pre-search invariant ordering, and repeated Phase 3 document identity.
- `Path.md` — this Phase 3 ledger, refreshed Phase 1/2 console line tables after source growth, and updated final acceptance items owned by Phase 3.

**Actual code and algorithmic decisions**

- Default input/output paths are resolved from `Path(__file__).resolve().parent`, so `python checker.py` is stable from the repository root and does not embed machine-specific paths in `result.json`. Optional `--canonical`, `--ablation`, and `--output` overrides exist only so temporary fixtures can exercise fail-closed behavior without mutating the checked-in inputs.
- `evaluate_pre_intervention_causal_invariants` runs after both instances load and before `validate_phase_one` or any `evaluate_closure` call. It checks evidence/history, evidence-action definitions/outcomes/costs, controller, authority, `Pi` / `Pi_eff` / `Pi_epi` / terminal rule, world/target function, initial representation, costs, `e_star` already admitted and valid, `R0` aliasing, and `R1` admitted-history-only reads. Any false invariant raises `ValidationError`.
- `validate_phase_three` then invokes Phase 1, then Phase 2 (full PC on `I`, fixed `R` on the same `I`, labeled full-PC ablation on `instance_minus.json`). `build_result_document` assembles the artifact. `assert_phase_three_acceptance` re-checks every required acceptance value. `write_result_json_atomically` serializes sorted indented UTF-8 JSON with a trailing newline, writes `result.json.tmp`, and replaces the destination only after that serialization succeeds. A failed assertion never reaches the writer.
- JSON forbids non-standard numbers: infinite cost remains JSON `null` plus the string `"infinity"`. The serializer rejects the substrings `Infinity` and `NaN`. The acceptance asserter also rejects machine-specific path substrings `C:\` and `/Users/`.
- `result.json` contains `artifact_kind = executable_matched_theorem_witness`, `reproduction_command = python checker.py`, `claim_scope` with statistical/prevalence/deployment/LLM flags false, `causal_invariants`, `phase_one`, `phase_two` (both primary runs and the secondary ablation), and `acceptance`.
- `main` configures logging and returns `1` on `ValidationError` after emitting `P3-ERROR`. It does not write a successful theorem result on that path.
- README interpretation is exactly six sentences and states that the artifact is an executable matched theorem witness, not statistical validation, prevalence evidence, or deployment evidence.

**Console instrumentation and identifying comments**

Python standard-library `LOGGER.info` / `LOGGER.error` is the language-equivalent of `console.log`. Every Phase 3 statement has an immediately preceding identifying comment:

| Step | Comment line | Log line(s) | Purpose |
| --- | ---: | ---: | --- |
| `P3-01` | 2130 | 2131 | Phase 3 artifact pipeline started |
| `P3-02` | 2134 | 2135–2138 | Inputs loaded before search; canonical fingerprint reported |
| `P3-03` | 1699 | 1700 | Pre-intervention causal-invariant checks started |
| `P3-04` | 1734 | 1735–1739 | Evidence/history invariants passed |
| `P3-05` | 1764 | 1765 | Evidence-action definition, outcome, and cost invariants passed |
| `P3-06` | 1774 | 1775 | Controller invariant passed |
| `P3-07` | 1784 | 1785 | Authority invariant passed |
| `P3-08` | 1800 | 1801 | `Pi`, `Pi_eff`, `Pi_epi`, and terminal-rule invariants passed |
| `P3-09` | 1815 | 1816 | World and target-function invariants passed |
| `P3-10` | 1826 | 1827 | Initial-representation invariant passed |
| `P3-11` | 1844 | 1845 | Cost invariants passed |
| `P3-12` | 1854 | 1855 | `e_star` already admitted and valid |
| `P3-13` | 1867 | 1868 | `R0` aliases the relevant distinction |
| `P3-14` | 1881 | 1882 | `R1` reads admitted history only |
| `P3-15` | 1963 | 1964 | All pre-search causal invariants passed |
| `P3-16` | 2143 | 2144 | Phase 1 validation invoked after invariants |
| `P3-17` | 2146 | 2147 | Phase 2 search invoked after invariants |
| `P3-18` | 2149 | 2150 | Acceptance document assembled |
| `P3-19` | 2154 | 2155 | `result.json` written atomically after all assertions |
| `P3-20` | 2156 | 2157 | Phase 3 completed |
| `P3-ERROR` | 2465 | 2466 | Failed contract or theorem assertion; nonzero exit |

Runtime order is `P3-01` through `P3-20`. Source order places `P3-03`–`P3-15` above `P3-01` because the invariant function is defined before the pipeline function. Test `test_all_twenty_phase_three_console_steps_are_emitted_in_order` checks emission order. Test `test_phase_three_invariants_are_logged_before_search` checks `P3-15` precedes both `P3-17` and `P2-05`.

**Commands and observed results**

- `python checker.py` from the repository root — exit code `0`; emitted `P3-01` through `P3-20` with `P3-15` before `P2-05`; wrote `result.json`.
- Second identical invocation — exit code `0`; `result.json` remained `11160` bytes and SHA-256 `da6fc493dd4202aa41b4aa301cbee4ea2ce04a9f5a5b5718e76befc39a1e01a9`.
- `python -m py_compile checker.py tests/test_checker.py` — exit code `0`.
- Independent `ast.parse` over both Python files — `AST validation passed for 2 Python files`.
- `python -m unittest discover -s tests -v` — exit code `0`; `Ran 45 tests in 2.387s`; `OK`.
- Direct trailing-whitespace scan — passed for all eight deliverables.
- Import-location audit — no inline imports inside functions.
- Independent 2.4-field parse of `result.json` — `kappa_Pi(I) = 1`, `kappa_Pi_fixR(I)` classification `infinity` with cost `null`, all causal invariants true, no `Infinity`/`NaN`/machine path/timestamp substrings.

**Stress-test coverage**

- Two repository-root CLI runs produced byte-identical `result.json`.
- In-process `validate_phase_three` wrote two temporary artifacts that compared equal.
- A temporary fixture with a copied `checker.py` and corrupted `instance_plus.json` (`{`) exited nonzero, emitted `P3-ERROR`, and did not create `result.json`.
- A temporary fixture with the canonical input deleted exited nonzero, emitted `P3-ERROR`, and did not create `result.json`.
- README sentence split yielded exactly 6 sentences and contained `python checker.py` plus the required witness-only exclusions.
- Existing Phase 1/2 500-run determinism tests remain passing.

**Acceptance evidence**

1. **Clean `python checker.py` succeeds from the repository root:** exit code `0`; `P3-20` emitted; `result.json` present.
2. **Two runs leave `result.json` byte-for-byte unchanged:** `11160` bytes, SHA-256 `da6fc493dd4202aa41b4aa301cbee4ea2ce04a9f5a5b5718e76befc39a1e01a9`.
3. **Tests independently parse `result.json` and re-assert every acceptance value:** `test_result_json_independently_reasserts_every_acceptance_value` reads the file and checks `kappa_Pi(I)`, infinity classification, zero evidence, one repair, same-instance identity, ablation singleton diff, `e_star`/`R0`/`R1` assertions, alternative counts, action counts, reachable/explored counts, and exhaustion.
4. **Corrupt or deleted input in a temporary fixture fails closed:** nonzero status, `P3-ERROR`, no successful `result.json`.
5. **README interpretation is 5–8 sentences and gives the exact command:** 6 sentences; command `python checker.py`; witness-only wording present.
6. **Pre-intervention causal invariants are logged before search:** `P3-03`–`P3-15` precede `P3-17`/`P2-05`; `causal_invariants.logged_before_search` is `true`.
7. **Atomic write occurs only after both primary runs, the labeled ablation, and every assertion:** writer is invoked only after `validate_phase_two` and `assert_phase_three_acceptance`.
8. **`result.json` contains every WorkPlan §2.4 observability field:** closure, classification, min cost, alternative sets/counts, path/steps, evidence acquisitions, repairs, reachable/explored counts, exhaustion, fingerprints, policy class, admitted/excluded action counts, ablation structural diff, and all listed invariant families.

**Plan conformance**

- Every Phase 3 scope item, code method, and exit gate in `WorkPlan.md` has implementation and local test evidence.
- Phase 4 independent-oracle and source-omission closeout are recorded in the Phase 4 section below.
- The implementation uses only the Python standard library.

**Deviations**

- Language adaptation only: requested `console.log` is implemented as `LOGGER.info` / `LOGGER.error` with adjacent identifying comments, as in Phases 1–2. This is not a WorkPlan behavioral deviation.
- Optional CLI path overrides were added so fail-closed tests can use a temporary fixture while the documented default command remains `python checker.py`. Defaults are unchanged.

**Risks/blockers:** None identified. Phase 3 remains complete.

## Phase 4 — Independent acceptance audit and traceability closeout

**Status:** Complete

**Planned scope and gates**

See `WorkPlan.md`, Phase 4. Completion requires a passing full suite from the documented command, an independently structured oracle that agrees with `FULL_PC(I)`, `FIXED_R(I)`, and the labeled ablation, a deterministic `result.json`, a finished source-to-deliverable matrix with no `Not implemented` / `Unverified` / unexplained `Deviated` item, and no widened training, statistical, benchmark, prevalence, or deployment claim.

**Files created/modified**

- `tests/independent_oracle.py` — independently structured FIFO enumerator. It does not import or call production search (`exhaustive_uniform_cost`, `evaluate_closure`, `pc_successors`, `apply_*`, `action_policy_view`, `legal_actions`, `successor_representation`, or `heapq`). After the frontier is empty it selects the minimum closing cost from the completed reachable set.
- `checker.py` — added `validate_phase_four` and the Phase 4 console instrumentation. `main` runs the audit after a successful Phase 3 write. `result.json` content is not changed by the audit. `WorkPlan.md` was not edited because no plan correction was required. `README.md` was not edited because the audit found no acceptance defect.
- `tests/test_checker.py` — 10 Phase 4 tests: oracle independence, agreement on both primary runs and the ablation, agreement with checked-in `result.json`, no environment read on repair, filter-only fixed `R`, Phase 4 log order, oracle log emission, and 50-run oracle determinism. Suite size is 55.
- `Path.md` — this Phase 4 ledger, refreshed Phase 1–3 console line tables after source growth, closed acceptance items, and the finished source-to-deliverable matrix.

**Actual code and algorithmic decisions**

- The oracle represents a state as `(representation, admitted identifiers, history identifiers, cost)`. Successors are generated from instance action fields. Evidence actions preserve `R` and union declared outcomes. Representation actions change only `R` and cost and reuse the same admitted/history identifier sets.
- Fixed `R` in the oracle is an independent successor-destination filter: a representation action is dropped when its destination is not the initial `R0`. The instance is not copied or mutated.
- Closure in the oracle is independent of `compatible_hypotheses` / `project_certificate`. Under `R0` every hypothesis remains. Under `R1` the oracle reads already-indexed admitted records and requires exactly one remaining hypothesis.
- Enumeration uses `collections.deque` FIFO, not `heapq`. Minimum cost is `min` over all reached closing states after the frontier is empty. Production search remains uniform-cost heap search. The two algorithms agreed on this witness.
- `validate_phase_four` inspects `apply_representation_action` and `project_certificate` source for the absence of an `"environment"` acquisition path, requires `acquired_evidence=()` and reused history/admitted objects, proves both policy views share the canonical object and the checked-in fingerprint, proves fixed `R` excludes repair only by filtering, proves the ablation singleton diff, proves infinity is `closed=false` plus `cost=null` plus `frontier_exhausted=true`, proves claim-scope flags are false and README uses witness-only wording, and evaluates every WorkPlan §5 matrix row against the artifact.
- No acceptance defect was found, so `result.json` and `README.md` were left unchanged. Two CLI runs after the Phase 4 hook produced the same `11160`-byte artifact as Phase 3.

**Console instrumentation and identifying comments**

Python `LOGGER.info` / `LOGGER.error` is the language-equivalent of `console.log`. Every Phase 4 statement has an immediately preceding identifying comment.

Audit closeout in `checker.py`:

| Step | Comment line | Log line(s) | Purpose |
| --- | ---: | ---: | --- |
| `P4-01` | 2298 | 2299 | Phase 4 acceptance audit started |
| `P4-02` | 2310 | 2311 | Instances and checked-in artifacts loaded |
| `P4-03` | 2316 | 2317 | Representation repair has no environment read |
| `P4-04` | 2338 | 2339 | Primary runs share canonical object and serialization |
| `P4-05` | 2353 | 2354 | Fixed `R` is evaluator-filter only |
| `P4-06` | 2365 | 2366 | Secondary ablation has no unapproved diff |
| `P4-07` | 2380 | 2381 | Infinity is tied to exhausted finite traversal |
| `P4-08` | 2398 | 2399 | Claim scope has no widened empirical claim |
| `P4-09` | 2403 | 2404–2407 | Source-to-deliverable matrix complete |
| `P4-10` | 2419 | 2420 | Phase 4 audit completed |
| `P4-ERROR` | 2475 | 2476 | Failed Phase 4 audit; nonzero exit |

Independent oracle in `tests/independent_oracle.py`:

| Step | Comment line | Log line(s) | Purpose |
| --- | ---: | ---: | --- |
| `P4-ORACLE-01` | 154 | 155–158 | Independent FIFO enumeration started |
| `P4-ORACLE-02` | 188 | 189–192 | Independent FIFO frontier exhausted |
| `P4-ORACLE-03` | 206 | 207–211 | Independent oracle result summarized |
| `P4-ORACLE-04` | 222 | 223 | Required three oracle runs started |
| `P4-ORACLE-05` | 231 | 232 | Required three oracle runs completed |

`test_phase_four_audit_evidence_and_console_order` checks `P4-01` through `P4-10` emission order. `test_oracle_console_steps_are_emitted` checks `P4-ORACLE-01` through `P4-ORACLE-05`. Live `python checker.py` emits `P3-20` before `P4-01`.

**Commands and observed results**

- `python -m unittest discover -s tests -v` — exit code `0`; `Ran 55 tests in 1.876s`; `OK`.
- `python checker.py` — exit code `0`; `P4-01` through `P4-10` emitted after `P3-20`; no `P4-ERROR`.
- Second `python checker.py` — exit code `0`; `result.json` unchanged at `11160` bytes, SHA-256 `da6fc493dd4202aa41b4aa301cbee4ea2ce04a9f5a5b5718e76befc39a1e01a9`.
- Independent oracle versus production: `FULL_PC(I)` closed cost `1`, reachable `4`; `FIXED_R(I)` non-closing, exhausted, reachable `2`; ablation full PC non-closing, exhausted, reachable `2`.
- AST independence check: oracle imports/calls contain none of the banned production-search names and do use `deque`.
- Direct trailing-whitespace scan — passed for all deliverables including `tests/independent_oracle.py`.

**Stress-test coverage**

- 50 repeated `evaluate_required_oracle_runs` calls produced equal result objects.
- Two CLI runs after the Phase 4 hook left `result.json` byte-identical.
- Existing Phase 1/2 500-run determinism tests remain passing.
- Fail-closed Phase 3 fixtures still fail before Phase 4 and do not write a successful theorem result.

**Acceptance evidence**

1. **All tests pass from the documented command:** `python -m unittest discover -s tests -v` — 55 tests, `OK`.
2. **Independent oracle agrees with `FULL_PC(I)`:** closed, cost `1`, exhausted, reachable `4`.
3. **Independent oracle agrees with `FIXED_R(I)`:** not closed, cost `null`, exhausted, reachable `2`.
4. **Independent oracle agrees with the labeled ablation:** not closed, cost `null`, exhausted, reachable `2`; role remains `transition_deletion_corroboration_only` in `result.json`.
5. **`result.json` proves acceptance and is deterministic:** same SHA-256 as Phase 3; `acceptance.all_passed` true; two CLI runs identical.
6. **No environment read during representation repair:** repair source has no `"environment"` or `outcomes`; successor reuses history and admitted evidence; `acquired_evidence` is empty.
7. **Same canonical object/serialization:** both policy views retain the loaded `Instance`; fingerprint matches `result.json`.
8. **Fixed `R` is filter only:** canonical repair remains enabled; full PC admits it; fixed `R` excludes it.
9. **Ablation has no unapproved diff:** `structural_diff` is exactly `representation_actions[0].enabled`.
10. **Infinity is exhausted finite traversal:** `closed=false`, `minimum_closure_cost=null`, `cost_classification=infinity`, `frontier_exhausted=true`.
11. **No widened claim:** `claim_scope` flags false; README states executable matched theorem witness and the required exclusions; `artifact_kind` is not a benchmark; README contains no training claim.
12. **Traceability matrix has no open item:** every WorkPlan §5 row is `Implemented` in the matrix below.

**Plan conformance**

- Every Phase 4 scope item, code method, and exit gate in `WorkPlan.md` has implementation and local test evidence.
- `WorkPlan.md` was not modified. `result.json` and `README.md` were not modified because the audit found no acceptance defect.
- The oracle remains outside production search.

**Deviations**

- Language adaptation only: requested `console.log` is implemented as `LOGGER.info` / `LOGGER.error` with adjacent identifying comments.
- `checker.py` was modified even though the Phase 4 file list names tests, `Path.md`, and conditional plan/artifact edits. The added function is the logged closeout required by the Phase 4 method bullets and does not change search or `result.json`. This is an additive instrumentation choice, not a change to the theorem contract.

**Risks/blockers:** None identified. No further implementation phase is authorized by `WorkPlan.md`.

## Final acceptance ledger

| Acceptance item | Status | Evidence |
| --- | --- | --- |
| Primary full-PC and fixed-`R` evaluators use one canonical `I` | Implemented | Same `Instance`, initial-state, policy, and transition-relation object references |
| Canonical repair remains legal in both primary policy projections | Implemented | `canonical_transition_repair_enabled == true`; fixed `R` filters rather than mutates |
| Full PC admits repair and fixed `R` excludes it by successor representation | Implemented | Full actions contain repair; fixed actions exclude only repair |
| Secondary ablation has exactly one modeled difference | Implemented | Ablation structural diff is exactly `representation_actions[0].enabled` |
| `e_star` is already admitted and valid in both inputs | Implemented | Strict loader, Phase 3 causal invariants, and semantic tests pass |
| `R0` has more than one policy-compatible alternative | Implemented | Alternatives are `w_target_absent`, `w_target_present` |
| `R1` has exactly one policy-compatible alternative | Implemented | Sole alternative is `w_target_present` |
| `kappa_Pi(I) = 1` on canonical `I` | Implemented | Production and independent oracle both return finite cost `1` |
| Optimal full-PC path on canonical `I` acquires zero environmental evidence | Implemented | One repair step; acquisition count `0` |
| `kappa_Pi_fixR(I) = infinity` on the same canonical `I` | Implemented | Same object/fingerprint; production and oracle exhaust 2 states |
| Full PC on transition-deletion ablation is non-closing | Implemented | Separately labeled infinity result after `2/2` exhaustion; oracle agrees |
| Infinity is established by finite exhaustion, not timeout | Implemented | No timeout/cutoff; empty-frontier result |
| Required causal invariants are logged and true | Implemented | `causal_invariants.all_passed == true`; `P3-03`–`P3-15` precede search |
| Machine-readable result contains all required fields | Implemented | `result.json` includes both primary runs, labeled ablation, §2.4 observability, and acceptance |
| Single command is deterministic and reproducible | Implemented | `python checker.py` twice leaves `11160`-byte SHA-256 `da6fc493dd4202aa41b4aa301cbee4ea2ce04a9f5a5b5718e76befc39a1e01a9` |
| Independent oracle agrees with production checker | Implemented | FIFO oracle matches closed/cost/exhaustion/reachable counts on all three required runs |
| README uses theorem-witness-only interpretation | Implemented | 6-sentence README; exact command; no statistical/prevalence/deployment claim |
| Source specification has no omitted requirement | Implemented | WorkPlan §5 matrix below; every row `Implemented` |

## Final source-to-deliverable traceability matrix

Status vocabulary used here: `Implemented`. This table contains no `Not implemented`, `Unverified`, or unexplained `Deviated` item.

| Source requirement | Realization | Status | Evidence |
| --- | --- | --- | --- |
| One deterministic finite checker | `checker.py`, finite domains, deterministic traversal/serialization | Implemented | Two CLI runs, byte-identical `result.json` |
| Canonical `I` enables `R0 -> R1` | `instance_plus.json` transition relation | Implemented | Repair enabled; full-PC path is `repair_R0_to_R1` |
| Fixed `R` preserves `R0` | Evaluator policy-class filter | Implemented | Fixed-`R` reached representations `["R0"]`; repair excluded |
| Same world and target function in both primary runs | Same canonical object | Implemented | `same_instance_object` and identical fingerprint |
| Same initial history containing `e_star` | Same canonical `h0` | Implemented | `e_star` admitted; same initial-state object |
| Same admitted evidence | Same canonical `E0` | Implemented | Same initial-state object |
| Same controller and authority | Same canonical initial state | Implemented | Same initial-state object |
| Same full policy and terminal rule | Same canonical policy | Implemented | Same policy object |
| Same actions, outcomes, costs, transition relation | Same canonical instance | Implemented | Same transition-relation object and fingerprint |
| Same initial `R0` | Same canonical initial state | Implemented | Initial representation `R0`; same initial-state object |
| Secondary ablation has exactly one modeled difference | Recursive full structural diff | Implemented | Diff is exactly `representation_actions[0].enabled` |
| `R0` remains non-closing | Representation projection aliases target distinction | Implemented | Initial alternative count `2` |
| `R1` closes from admitted history | Projection exposes `e_star` target label | Implemented | Closing alternative count `1`; evidence acquisitions `0` |
| `kappa_Pi(I) = 1` | Full-PC uniform-cost evaluator plus independent oracle | Implemented | Production and oracle cost `1` |
| Zero new evidence on closing path | Typed path counters | Implemented | `evidence_acquisitions == 0` |
| `kappa_Pi_fixR(I) = infinity` | Fixed-`R` evaluator on the same `I` plus oracle | Implemented | Exhausted, not closed, cost `null` |
| Transition-deletion destroys closure | Full-PC run on `instance_minus.json` plus oracle | Implemented | Labeled non-closing exhausted result |
| Log causal invariants | Pairwise checks in `result.json` | Implemented | `causal_invariants.all_passed == true` |
| Machine-readable report | Deterministic `result.json` | Implemented | Schema/value tests and SHA-256 identity |
| One-command reproducibility | `python checker.py` in `README.md` | Implemented | Clean invocation test |
| 5–8 sentence interpretation | Focused README interpretation | Implemented | 6 sentences; command present |
| Narrow paper wording | Explicit witness-only language | Implemented | `claim_scope` false; README exclusions |

## Deviation log

- Phase 1 language adaptation: the requested JavaScript-specific `console.log` syntax was implemented as Python standard-library `LOGGER.info` calls because `checker.py` is the artifact language selected by `WorkPlan.md`. All requested step visibility, identifying comments, and line-level documentation are present; there is no functional scope deviation.
- Mathematical correction after Phase 1: the original plan encoded fixed `R` by disabling the repair transition in `I_minus`, which would compare two instances rather than two policy classes on one instance. `WorkPlan.md`, `checker.py`, tests, Phase 1 evidence, and this ledger were corrected. Canonical `I` now retains the repair transition for both primary policy classes; fixed `R` is an evaluator-only successor-representation filter. The former pair remains only as a secondary ablation.
