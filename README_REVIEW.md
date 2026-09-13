# Reviewer Guide — Same-Instance Representation-Freeze Witness

This is an anonymous reviewer snapshot of a deterministic executable same-instance representation-freeze witness retained as theorem-adjacent implementation evidence.

## Purpose

The artifact is a deterministic executable same-instance representation-freeze witness. It evaluates one canonical instance under two evaluator policy classes and reports a machine-readable result. Historical protocol files use an earlier manuscript numbering. Claim scope is narrow: not statistical validation, not prevalence evidence, not deployment evidence, not LLM evaluation.

## Reproduction

From the repository root, run:

```
python checker.py
```

This writes `result.json`.

## Tests

From the repository root, run:

```
python -m pytest -q
```

An alternative supported command is `python -m unittest discover -s tests -v`.

## Expected Outcome

- `artifact_kind` is `executable_matched_theorem_witness`.
- `acceptance.all_passed` is `true` and `acceptance.causal_invariants_all_passed` is `true`.
- Full PC: `closed` is `true`, minimum closure cost is `1`, representation repairs `1`, environmental evidence acquisitions `0`, steps `1`.
- Fixed-R on the same canonical instance: `closed` is `false`, cost classification is `infinity`, frontier is exhausted.
- `kappa_pi_I` is `1` and `kappa_pi_fix_r_I` is `infinity` (JSON `null` plus `infinity` classification).
- The same canonical instance is used for both primary computations.
- The target-bearing evidence is already admitted and valid before the intervention.
- The optimal closing action is `repair_R0_to_R1`.
- The secondary ablation is corroboration only and differs structurally by exactly `representation_actions[0].enabled`.
- All causal invariants pass.

## Notes

- Do not use any repository URL from prior versions; this snapshot is self-contained.
- No author identity is included in this snapshot.
