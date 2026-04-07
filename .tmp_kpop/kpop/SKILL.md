---
name: kpop
description: >
  Apply Karl Popper-style hypothesize-predict-falsify (KPOP) scientific debugging to any problem.
  Use this skill whenever the user types /kpop, asks to "falsify" a claim, wants to fix a difficult
  bug systematically, wants to optimize performance, or wants to build/tune a model or system
  iteratively. Also trigger when the user gives a "hypothesis budget" (e.g., "budget of 30 hypotheses")
  or asks you to "run an experiment". This skill enforces a rigorous loop: form one falsifiable
  hypothesis at a time, define what would disprove it, test it, and log everything — stopping only
  when the problem is solved or the budget is exhausted. Do NOT use vague trial-and-error; every
  action must correspond to a named hypothesis being tested.
---

# KPOP: Karl Popper Scientific Debugging

Named after Karl Popper, who described hypothesis-driven falsification as the engine of science.

---

## When to Apply

| User types | Action |
|---|---|
| `/kpop Falsify <claim>` | Immediately form a hypothesis that the claim is false and test it |
| `/kpop Fix this bug. Budget: N` | Run KPOP loop until fixed or N hypotheses exhausted |
| `/kpop Make <fn> faster. Budget: N` | Run KPOP loop targeting measurable speedup |
| `/kpop <open-ended goal>. Budget: N` | Decompose into falsifiable sub-hypotheses; iterate |

---

## The KPOP Loop

```
Restate the problem clearly.

do:
  HYPOTHESIZE: One falsifiable explanation of the cause.
  PREDICT:     What outcome would this test produce if the hypothesis were true?
  FALSIFY:     Run the minimal test. Observe outcome.
  LOG:         Record hypothesis, prediction, result, verdict (falsified / not falsified).
until: problem solved OR budget exhausted
```

**Key constraint:** Only one hypothesis per iteration. Do not batch hypotheses.

---

## Log File

Always log to a Markdown file:
- If the user specifies a path → use it.
- Otherwise → `_kpop/exp_log_{meaningful_name}.md` (invent a descriptive name).

### Log Entry Format

```markdown
## H{N}: <hypothesis title>

**Hypothesis:** <concise, falsifiable statement>
**Prediction:** <measurable outcome if true>
**Test:** <exact commands run / code changed / metrics checked>
**Result:** <observed outcome>
**Verdict:** FALSIFIED | NOT FALSIFIED | INCONCLUSIVE
**Notes:** <what this rules in or out; what to try next>
```

---

## Hypothesis Quality Rules

Apply the Claims vs Hypotheses framework throughout:

- Every hypothesis must be **falsifiable** — there must be a test that could prove it wrong.
- Every prediction must be **measurable** — a specific value, behavior, or output.
- Every test must be **minimal** — change one variable at a time.
- Label all statements: `[Hypothesis]` or `[Claim]` (see claims-vs-hypotheses skill).

---

## Budget Management

- Track `hypotheses used / budget` at the top of each log entry.
- At 80% of budget: pause, summarize what has been ruled out, propose the highest-leverage remaining hypothesis.
- At 100%: write a final summary — what was learned, what remains open, recommended next steps.

---

## Example Invocations

### Falsify a claim
```
/kpop Falsify: caching is what's making the API slow
```
→ Form H1: "Caching is NOT the cause — disabling it will not improve latency."
   Predict: p50 latency unchanged with cache disabled.
   Test: disable Redis, measure p50 over 100 requests.
   Result: p50 drops 40% → H1 FALSIFIED → caching IS causing slowness (Claim, with evidence).

### Fix a bug
```
/kpop Fix this bug. You have a budget of 30 hypotheses.
```
→ Restate bug. H1: most likely cause. Test. Log. Repeat.

### Optimize
```
/kpop Make `embed_batch()` faster. Budget: 20 hypotheses.
```
→ Baseline benchmark first (always). H1: bottleneck is I/O not compute. Test. Log. Repeat.

### Build/tune a model
```
/kpop Train a policy for Humanoid-v4. Get reward > 5000. Budget: 100 hypotheses.
```
→ Treat each architectural/hyperparameter change as a hypothesis. Log all runs.

---

## Final Summary Format

When done (solved or budget exhausted), write to the log:

```markdown
## Final Summary

**Problem:** <original restatement>
**Solved:** YES / NO
**Solution:** <what fixed it, or N/A>
**Hypotheses used:** N / budget
**Ruled out:** <list of falsified explanations>
**Open questions:** <what remains unknown>
**Recommended next steps:** <if not solved>
```
