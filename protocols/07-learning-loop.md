# Turn corrections into reviewed engineering memory

Observe a real failure, preserve a minimal reproducible example, classify the failure, improve the relevant skill or executable rule, then replay known and held-out cases. Do not train the harness to memorize one incident's expected output.

Incident record fields: date, task, bad assumption, evidence that disproved it, first failing gate, record witness, mechanism, countermeasure, affected skill/rule, regression case, false-positive risk, reviewer and version.

Promote through draft → shadow → reviewed → active. An active rule needs a positive and negative example, a stable rule ID, a clear remediation, known limitations and a rollback version. Run a candidate policy side by side with the current policy; compare new blocks, misses and unnecessary escalations. Never let the agent edit its own policy or expected evaluation results simply to pass the task under review.

Measure deterministic rule precision on labeled cases separately from model/agent performance. Real Claude evaluation requires recorded prompts, model and tool versions, environment snapshots, outcomes and independent grading. This repository includes a runnable deterministic regression suite and a manual agent-evaluation set; it does not claim that Claude has achieved a benchmark score.

Preserve contextual lineage: source version → observation → finding → model decision → patch → verification → review outcome. This adapts the observation-loop idea to data engineering while keeping actions bounded by existing development and release authority.
