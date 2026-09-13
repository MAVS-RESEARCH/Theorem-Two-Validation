# For Reviewers

> **Start here.** This is a short map of the artifact: what it supports, where the final result is, and where to look if you want more detail.

## What this artifact is

This is a deterministic executable same-instance representation-freeze witness retained as theorem-adjacent implementation evidence for the Perceptive Closure submission. It runs a small finite checker on one canonical instance and writes a machine-readable result. Historical protocol documents in this artifact use an earlier manuscript numbering and refer to this witness as 'Theorem 2, Part I'; that label should not be read as referring to Theorem 2 in the submitted manuscript.

## `WorkPlan.md` and `Path.md`

**`WorkPlan.md` = what was supposed to happen.**

It is the experiment and design specification: planned phases, gates, requirements, and acceptance criteria. See it if you want the original protocol.

**`Path.md` = what actually happened.**

It is the execution ledger: implementation steps, tests, deviations, gate outcomes, and the path to the final state. See it if you want the execution history.

You do not need to read either file front-to-back. There are no separate supporting variants for this artifact.

## Main result

The authoritative result is `result.json`, with `acceptance.all_passed` true:

- Full PC closes at minimum cost `1` via `repair_R0_to_R1`, in `1` step with `1` repair and `0` new evidence acquisitions.
- Fixed-R on the same canonical instance does not close, with cost classification `infinity` after exhaustive frontier exhaustion.
- `kappa_pi_I` is `1`; `kappa_pi_fix_r_I` is `infinity`.
- Both primary runs use the same canonical instance, with target-bearing evidence already admitted before the intervention.
- The secondary ablation is corroboration only and differs by exactly `representation_actions[0].enabled`.

## Where to look

1. `result.json` — authoritative final witness to cite.
2. `checker.py` — deterministic checker that produces the result.
3. `instance_plus.json` — canonical instance used for both primary runs.
4. `instance_minus.json` — secondary ablation input, not the fixed-R computation.
5. `README_REVIEW.md` — short reproduction and expected outcome.
6. `WorkPlan.md` and `Path.md` — deeper protocol and execution history if needed.

## Quick verification

`python checker.py` requires Python. Running the optional test suite also requires `pytest`.

Run from the repository root:

```
python checker.py
python -m pytest -q
```

See `README_REVIEW.md` for the expected outcome.

## Scope / important interpretation

This is a deterministic same-instance witness, not statistical validation, prevalence evidence, deployment evidence, or model evaluation. It does not prove the current manuscript's Theorem 2. Do not read the secondary ablation as the fixed-R result: fixed-R is the same-instance policy restriction, while the ablation only shows that deleting the transition also destroys closure.

## Reviewer snapshot

This is an anonymous reviewer snapshot. Detailed reproduction information is in `README_REVIEW.md` and aggregate verification information is in `ANONYMIZATION_REPORT.json`.
