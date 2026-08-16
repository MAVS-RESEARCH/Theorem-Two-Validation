# Work plan: canonical-instance finite complementarity checker

## 1. Purpose, source, and scope boundary

This plan translates `PC_Matched_Complementarity_Checker_Implementation_Spec.docx` into an executable, inspectable witness for Theorem 2, Part I of Perceptive Closure (PC). The source document used for this plan has SHA-256:

`3FD95DBEE2A4E5D9F418334C5DE4C59186FEC6306F228C4BCA714A47B6D39F09`

The checker will demonstrate one narrow theorem claim on one canonical PC instance `I`: full PC closes because its policy class may use the legal representation transition `R0 -> R1`, while the fixed-representation policy class cannot close because it may use only legal transitions whose successor preserves the initial representation `R0`. The world, hypotheses, initial history, admitted evidence, controller state, epistemic authority, policy, action costs, transition relation, and initial representation are therefore literally the same object in the primary comparison.

The required result is:

- `kappa_Pi(I) = 1`: full PC closes after one unit-cost representation repair.
- `kappa_Pi_fixR(I) = infinity`: the fixed-`R` evaluator exhausts the states reachable from the same `I` while preserving `R = R0` and cannot close.
- The optimal full-PC closing path for `I` acquires zero new environmental evidence.

The previously specified `I_plus` / `I_minus` pair remains as a secondary matched ablation. `I := I_plus` is the canonical theorem instance. `I_minus` differs only by deleting the representation transition and is used only to confirm that transition deletion destroys closure; it is not used to define or compute `kappa_Pi_fixR(I)`.

This is a deterministic finite theorem witness, not a statistical experiment. No AI/ML model will be created or trained, so training datasets, training benchmarks, held-out model benchmarks, and overfitting controls are inapplicable. No LLM evaluation, prevalence estimate, deployment claim, or new empirical benchmark will be introduced. Correctness will instead be established by exact assertions, finite-state exhaustion, deterministic regression tests, and independent output validation.

## 2. Formal implementation contract

### 2.1 State and action model

The implementation will use explicit, serializable finite structures:

- `C`: certificate-relevant state, computed from the represented admitted history and policy rather than supplied as an unverified closure flag.
- `R`: representation identifier (`R0` or `R1`).
- `M`: controller state.
- `E`: admitted evidence identifiers.
- `history`: evidence records available from the initial history or acquired by an evidence action.
- `cost`: accumulated non-negative action cost.
- `rank` / `depth`: monotone traversal metadata used to enforce and report finite ranked exploration.
- Evidence actions and representation actions will be distinct typed variants. Representation repair will never invoke an environmental observation function.

The search node's identity will contain only semantic state needed to determine future behavior; path-local reporting fields such as accumulated cost and steps will be retained separately. Canonical JSON serialization and sorted collections will make hashing, equality, traversal, and outputs deterministic.

### 2.2 Canonical witness

The canonical base instance will contain a target-bearing datum `e_star` in both `h0` and `E0`, marked valid and admitted before any action. Its world will contain at least two hypotheses that differ on the target. Under `R0`, the representation aliases the target-relevant distinction, so policy-compatible alternatives satisfy `|A_Pi(C^R0)| > 1`. Under `R1`, the representation exposes the target label already carried by `e_star`, without adding evidence, and the same policy leaves exactly one alternative: `|A_Pi(C^R1)| = 1`.

`instance_plus.json` is the canonical theorem instance `I` and contains the legal `R0 -> R1` transition. Both primary evaluators will receive this exact same loaded immutable instance and initial state. Their only difference is evaluator policy class:

- `FULL_PC`: admits every action legal under `Pi` and the canonical transition relation.
- `FIXED_R`: admits only actions legal under `Pi` whose successor representation equals the initial `R0`.

Formally, the restricted action set is `A_fixR(sigma) = {a in A_Pi(sigma) : R(T(sigma, a)) = R0}`. The restriction must not mutate action legality, the transition relation, or any instance field.

`instance_minus.json` is retained only as a secondary ablation input. It is a deep, independent materialization that differs from canonical `I` only in the boolean enabling `R0 -> R1`. A recursive structural-diff function will assert that this ablation diff is exactly the approved representation-transition path; ablation results will be reported separately from the primary same-instance theorem result.

### 2.3 Closure cost and infinity

The checker will perform uniform-cost exhaustive traversal twice over the canonical instance `I`: once under `FULL_PC` and once under `FIXED_R`. Uniform-cost search is required because declared legal actions may have different non-negative costs.

1. Validate the schema, finite domains, non-negative costs, admitted evidence, and ranked transition assumptions.
2. Evaluate closure at the initial state and after each reachable legal transition.
3. Track the least cost and a deterministic predecessor path for every semantic state.
4. Return the first minimum-cost closing path only when the queue ordering proves it minimal.
5. Return machine-readable `null` for minimum cost plus an explicit `"infinity"` classification only after the fixed-`R` frontier is empty.
6. Prove by canonical identity/fingerprint and object reuse that both primary runs used the same instance, initial state, policy, action costs, and transition relation.

Thus `kappa_Pi_fixR(I) = infinity` will be a proof by complete finite-state exhaustion under the restricted policy class on canonical `I`, never a timeout, depth cutoff, missing result, or altered transition system. Human-readable documentation may use `infinity`; JSON will not use non-standard numeric `Infinity`. Exhaustion of `I_minus` may be reported only as corroborating ablation evidence.

### 2.4 Required observability

Each result will report:

- closure status and finite/infinite classification;
- minimum closing cost;
- initial and final represented alternative sets/counts;
- deterministic optimal path and step count;
- new environmental evidence acquisitions;
- representation repairs;
- reachable and explored state counts;
- exhaustion status;
- canonical-instance identity/fingerprint for both primary evaluator runs;
- evaluator policy class and admitted/excluded action counts for each primary run;
- secondary ablation structural diff and exactly-one-difference result;
- pre-intervention invariant checks for evidence/history, evidence action definitions and outcomes, controller, authority, policies (`Pi`, `Pi_eff`, `Pi_epi`, and terminal rule), world/target function, initial representation, and costs;
- assertions that `e_star` was already admitted and valid, `R0` aliases the relevant distinction, and `R1` reads admitted history only.

## 3. Phase plan

The workload is intentionally compact and is divided into four phases. Phase completion requires all listed gates; a phase is not complete merely because its files exist.

### Phase 1 — Define the canonical instance and evaluator policy classes

**Scope**

Translate the finite PC contract into strict Python validation, designate `instance_plus.json` as canonical `I`, and define full-PC versus fixed-`R` action admissibility on that same immutable instance. Preserve `instance_minus.json` only as the matched transition-deletion ablation. Establish these semantics without implementing search yet.

**Files created**

- `instance_plus.json` — canonical theorem instance `I`, with the legal repair transition.
- `instance_minus.json` — secondary transition-deletion ablation input, not the fixed-`R` theorem evaluator input.
- `checker.py` — initial schema types, evaluator policy-class type, loaders, canonicalization, validators, same-instance action admissibility, representation projection, policy/alternative evaluation, and ablation structural comparison.
- `tests/test_checker.py` — deterministic schema, same-instance policy restriction, closure-semantics, and secondary ablation-contract tests using only the Python standard library.

**Code and method**

- Use `dataclasses`, `Enum`, and typed unions to separate `EvidenceAction` from `RepresentationAction`.
- Load JSON into validated immutable domain objects rather than passing mutable dictionaries through the search.
- Define one canonical finite world and target-label function, one `h0`, one `E0`, one controller/authority, one complete policy bundle, one transition relation, and one evidence action/outcome/cost table.
- Implement `R0` as a projection that withholds/aliases the target-bearing field from certificate evaluation while preserving `e_star` in admitted history.
- Implement `R1` as a projection over that same admitted history that exposes the target field. It must have no code path to acquire or synthesize environmental evidence.
- Define explicit `FULL_PC` and `FIXED_R` evaluator policy classes. On the same canonical instance and current representation, derive full-PC legal actions from the instance transition relation, then derive fixed-`R` actions by filtering out any action whose successor representation differs from initial `R0`.
- Prove in Phase 1 tests that canonical `I` is not copied or mutated to implement fixed `R`; both action projections receive the same instance object, and canonical raw/domain fingerprints remain unchanged.
- Recursively canonicalize and compare canonical `I` with the secondary ablation. The expected ablation diff set will contain exactly `representation_actions[0].enabled`, with no ignored fields.
- Validate that `e_star` is in initial history, belongs to `E0`, is valid, is target-bearing, and exists identically in both inputs.
- Assert initial `R0`, `|A_Pi(C^R0)| > 1`, and, by pure evaluation of the legal repair target, `|A_Pi(C^R1)| = 1`.

**Verification and exit gates**

- Canonical `I` and the secondary ablation both parse and pass strict validation.
- On canonical `I`, full PC admits the legal repair action while fixed `R` excludes it solely because its successor representation is `R1`; both policy classes admit legal representation-preserving evidence actions.
- The same canonical object, initial state, policy, costs, and transition relation are unchanged before and after both policy projections.
- A mutation test in `tests/test_checker.py` changes each protected ablation field in turn and confirms the structural contract rejects it.
- A test confirms the secondary ablation pair has exactly one diff.
- A test confirms `R0` is non-closing and `R1` closes using unchanged `history` and `E`.
- JSON round trips preserve canonical equality and input files remain unmodified by loading.

### Phase 2 — Implement exhaustive minimum-cost closure evaluation

**Scope**

Build the finite ranked state graph once from canonical `I` and prove the minimum finite cost under full PC and exhaustive non-closure under the fixed-`R` policy class. Run the transition-deletion instance only as a secondary ablation.

**Files modified**

- `checker.py` — legal successor generation, uniform-cost traversal, predecessor/path reconstruction, finite exhaustion accounting, and theorem assertions.
- `tests/test_checker.py` — search minimality, action separation, exhaustion, cycle/deduplication, and determinism tests.

**Code and method**

- Generate evidence and representation successors through separate functions and action types.
- In canonical `I`, keep `R0 -> R1` legal in the underlying transition relation for both primary runs. The transition costs exactly `1`, increments rank/depth, preserves world/history/admitted evidence/controller/authority/policy, and records one representation repair.
- Apply evaluator policy admissibility at successor generation: full PC may take every legal canonical action; fixed `R` may take only legal canonical actions satisfying `R(T(sigma, a)) = R0`.
- Keep the exact same evidence operations, outcomes, costs, and transition definitions in both primary runs. They remain in the graph and are traversed where legal so fixed-`R` non-closure is genuinely exhaustive.
- Use a heap ordered by `(cost, deterministic_tiebreaker)` and best-cost map. Reject negative costs and stale queue entries. Deduplicate semantic states while retaining sufficient counters to report reachable versus expanded states.
- Compute closure from represented alternatives at every node. Do not special-case canonical `I` or hard-code the expected answer into the closure evaluator.
- For the fixed-`R` run on canonical `I`, continue until no legal unvisited fixed-`R` state remains; then mark the result exhausted and infinite.
- Reconstruct action, cost, evidence-acquisition, representation-repair, and closure details for the optimal full-PC path.
- Separately evaluate `instance_minus.json` under full PC as the transition-deletion ablation; never substitute this result for `kappa_Pi_fixR(I)`.

**Verification and exit gates**

- Assert and test `kappa_Pi(I) == 1`.
- Assert that the full-PC and fixed-`R` computations receive the same canonical instance identity/fingerprint and initial state.
- Assert and test the optimal path has one representation repair and zero new environmental evidence acquisitions.
- Assert and test closure occurs after `R0 -> R1`.
- Assert and test `kappa_Pi_fixR(I) == infinity`: canonical `I` has no closing state reachable under the fixed-`R` action filter, its restricted frontier is exhausted, and its cost classification is infinite.
- Assert separately that full-PC evaluation of the transition-deletion ablation is non-closing; label this result as secondary corroboration.
- Add synthetic small-graph tests where a longer/more expensive closing route is encountered before a cheaper one, proving true minimum-cost behavior.
- Add a test where a reachable cycle is safely deduplicated and exhaustion still terminates.
- Repeated runs must produce byte-identical normalized result objects.

### Phase 3 — Produce the reproducible artifact and machine-readable proof

**Scope**

Create the one-command interface, final result artifact, causal-invariant log, and concise interpretation required by the source document.

**Files created or modified**

- `checker.py` — command-line entry point and deterministic JSON writer.
- `result.json` — checked-in machine-readable result containing both run results and pairwise invariant evidence.
- `README.md` — exact reproduction command and a 5–8 sentence interpretation.
- `tests/test_checker.py` — CLI, emitted schema, and checked-in artifact consistency tests.

**Code and method**

- Support a repository-root command such as `python checker.py` with stable default input/output paths and nonzero exit status on any failed contract or theorem assertion.
- Validate and log all pre-intervention causal invariants before search.
- Emit sorted, indented UTF-8 JSON with no timestamps, machine-specific paths, random identifiers, or non-standard numbers.
- Include closure, minimum cost, path/steps, evidence acquisitions, repairs, state counts, exhaustion, canonical-instance identity, evaluator policy class, secondary ablation structural diff, and all invariant checks.
- Regenerate `result.json` atomically only after both primary same-instance runs, the separately labeled ablation run, and every acceptance assertion pass.
- State in the README that this is an executable matched theorem witness, not statistical validation, prevalence evidence, or deployment evidence.

**Verification and exit gates**

- A clean `python checker.py` invocation succeeds from the repository root.
- Running it twice leaves `result.json` byte-for-byte unchanged.
- Independently parse `result.json` in tests and re-assert every required acceptance value rather than trusting console text.
- Delete or corrupt an input in a temporary test fixture and confirm the command fails closed without presenting a successful theorem result.
- Confirm the README interpretation is 5–8 sentences and gives the exact one-command reproduction path.

### Phase 4 — Independent acceptance audit and traceability closeout

**Scope**

Verify that nothing in the source specification was omitted, that the implementation did not widen the claim, and that `Path.md` accurately records the implementation.

**Files modified**

- `tests/test_checker.py` — any final acceptance regression checks discovered by audit.
- `WorkPlan.md` — only if implementation evidence requires an explicitly documented, justified plan correction.
- `Path.md` — phase-by-phase actual implementation details, deviations, commands, outputs, and final requirement matrix.
- `result.json` and `README.md` — regenerated/updated only if audit identifies an acceptance defect.

**Code and method**

- Run the full standard-library suite with `python -m unittest discover -s tests -v`.
- Run `python checker.py`, save the artifact, rerun it, and verify no diff.
- Independently enumerate reachable states in test code or an independently structured test oracle for this tiny witness. Compare closing-state existence, minimum cost, exhaustion, and reachable counts for both `FULL_PC(I)` and `FIXED_R(I)` on canonical `I`; separately compare the labeled full-PC transition-deletion ablation result. This oracle must remain independent from production search logic.
- Audit every source-document sentence against the requirement matrix below and the actual artifact.
- Check that no environment read occurs during representation repair, the two primary runs share an identical canonical object/serialization, fixed `R` is enforced only by evaluator filtering, the secondary ablation has no unapproved diff, and infinity is tied to exhausted finite traversal.
- Record every implementation decision and any deviation in `Path.md`; unresolved or unjustified deviations fail the phase.

**Verification and exit gates**

- All tests pass from a clean checkout using the documented command(s).
- The independent oracle agrees with both canonical evaluator runs, `FULL_PC(I)` and `FIXED_R(I)`, and separately agrees with the labeled transition-deletion ablation.
- `result.json` proves all acceptance criteria and is deterministic.
- The final traceability matrix has no `Not implemented`, `Unverified`, or unexplained `Deviated` item.
- No model-training, statistical-validation, benchmark, prevalence, or deployment claim appears in the artifact.

## 4. Verification strategy (non-ML)

Because there is no learned component, "overfitting" in the model-training sense cannot occur. The analogous implementation risks are hard-coding the expected pair, testing the evaluator with itself, and silently bounding a supposedly exhaustive search. The plan controls these risks as follows:

- **Semantic tests:** independently check `R0` ambiguity and `R1` closure from admitted `e_star`.
- **Policy-class separation tests:** project both action sets from one immutable canonical object and prove fixed `R` filters representation-changing successors without changing instance legality.
- **Ablation contract mutation tests:** alter protected fields and require rejection, preventing an accidentally unmatched secondary pair.
- **Algorithm tests on different fixtures:** exercise cheaper-versus-costlier paths, non-closing finite graphs, and cycles. These fixtures are structurally different from the canonical theorem witness and ensure the search is not specialized to it.
- **Independent tiny-state oracle:** enumerate the canonical finite graph through independently structured test code and compare outcomes/counts.
- **No timeout inference:** infinity requires an empty frontier and an explicit exhaustion flag.
- **Reproducibility:** fixed ordering, canonical serialization, no randomness, and byte-identical reruns.
- **Fail-closed execution:** malformed inputs, invariant failures, or acceptance failures produce nonzero status and no successful result.

These are correctness fixtures, not research benchmarks, and will not be described as evidence beyond the theorem witness.

## 5. Source-to-deliverable traceability matrix

| Source requirement | Planned realization | Primary verification |
| --- | --- | --- |
| One deterministic finite checker | `checker.py`, finite domains, deterministic traversal/serialization | Repeat-run byte comparison |
| Canonical `I` enables `R0 -> R1` | `instance_plus.json` transition relation | Canonical validation and full-PC action projection |
| Fixed `R` preserves `R0` | Evaluator policy-class filter over canonical successors | Same-instance action-set and exhaustive fixed-`R` tests |
| Same world and target function in both primary runs | Same canonical object | Instance identity/fingerprint assertion |
| Same initial history containing `e_star` | Same canonical `h0` | Admission/validity and identity assertions |
| Same admitted evidence | Same canonical `E0` | Set/object identity |
| Same controller and authority | Same canonical initial state | Object equality/identity |
| Same full policy and terminal rule | Same canonical policy | Object equality/identity |
| Same actions, outcomes, costs, transition relation | Same canonical instance | Fingerprint before/after both runs |
| Same initial `R0` | Same canonical initial state | Initial-state identity assertion |
| Secondary ablation has exactly one modeled difference | Recursive full structural diff | Expected singleton ablation diff assertion |
| `R0` remains non-closing | Representation projection aliases target distinction | Alternative count `> 1` |
| `R1` closes from admitted history | Projection exposes `e_star` target label | Alternative count `== 1`; unchanged `E/history` |
| `kappa_Pi(I) = 1` | Full-PC uniform-cost evaluator on canonical `I` | Theorem assertion and independent oracle |
| Zero new evidence on closing path | Typed path counters | `evidence_acquisitions == 0` |
| `kappa_Pi_fixR(I) = infinity` | Fixed-`R` evaluator on the same canonical `I` | `exhausted == true`, no closing state, same fingerprint |
| Transition-deletion destroys closure | Full-PC run on `instance_minus.json` | Separately labeled ablation result |
| Log causal invariants | Pairwise checks in `result.json` | All invariant values true |
| Machine-readable report | Deterministic `result.json` | Schema/value tests |
| One-command reproducibility | `python checker.py` in `README.md` | Clean invocation test |
| 5–8 sentence interpretation | Focused README interpretation | Sentence-count audit |
| Narrow paper wording | Explicit witness-only language | Scope audit |

## 6. `Path.md` maintenance rule

`Path.md` is the implementation ledger and must be updated as each phase is executed, not reconstructed only at the end. For every phase it will record:

1. planned scope and acceptance gates;
2. exact files created/modified;
3. actual code and algorithmic decisions;
4. commands run and observed results;
5. evidence for each acceptance gate;
6. whether work followed this plan;
7. every deviation, its reason, impact, and corrective action;
8. remaining risks or blockers;
9. the next authorized phase.

An item may be marked `Complete` only with evidence. If implementation changes this plan, `Path.md` will identify the deviation explicitly and `WorkPlan.md` will be updated only where necessary to keep the intended and actual designs auditable.
