# 1. Ship a feature with parallel agents

A coordinator and two workers add a health endpoint and its documentation. The
human supplies decisions that repository evidence cannot settle. Read the
[outline conventions](README.md) before using these examples.

## Prepare the goal

Install the skill, configure executable project gates and join the coordinator.
Open the goal and answer every required field returned by the goal workflow.

```bash
hivewire join --as lead --kind codex
hivewire goal new health "Ship a health endpoint operators can rely on" --as lead
hivewire goal answer health --as lead --set FIELD="REPOSITORY_BACKED_ANSWER"
hivewire goal outcome health "GET /health includes the running version" --check "Assert status and version" --as lead
hivewire goal check health 1 --command '["python","checks/health.py"]' --as lead
hivewire goal task health H-api "Add the endpoint" --serves 1 --done-when "endpoint check passes" --scope src/,checks/ --as lead
hivewire goal task health H-docs "Document it" --serves 1 --done-when "docs describe the tested endpoint" --scope docs/ --as lead
hivewire goal architecture health --template --as lead
```

Record **all** fields of the completed architecture template, citing real files,
before approving. High-risk approval requires the human. Then review and commit
the goal. With workers joined, `--assign` may route eligible tasks to them.

```bash
hivewire goal architecture health --set FIELD="DESIGN_DECISION" --evidence src/app.py --risk low --as lead
hivewire goal architecture health --approve --as lead
hivewire goal review health --as lead
hivewire goal commit health --assign --as lead
```

## Deliver each task

Each worker joins, obtains a task if not already assigned, and follows its printed
worktree and next action. Run `next` only when free. Printing a plan template does
not record a plan: complete its fields and ordered steps, resolve critical
questions, then start. See [SKILL.md](../skills/agents-collaboration/SKILL.md).

```bash
hivewire join --as ann --kind claude
hivewire next --as ann
hivewire plan --as ann --template
hivewire plan --as ann --set FIELD="EVIDENCE_BACKED_ANSWER" --step "IMPLEMENTATION_STEP"
hivewire start --as ann
```

In the assigned worktree, implement and test each planned step. Record every step
in order with actual evidence, commit the changes in Git, then submit and merge.
The example step below represents one step of the completed plan.

```bash
hivewire step 1 --as ann --evidence "ACTUAL_CHECK_RESULT"
hivewire submit --as ann --evidence "COMMIT_AND_CHECK_RESULTS"
hivewire merge --as ann
```

A successful merge frees the worker; the worker requests its next task. Claims
are atomic. Declared scope and locks catch conflicts, while gates and a target
compare-and-swap check integration. Undeclared overlap and arbitrary shell edits
remain possible. A failing gate or rebase conflict prevents that merge advancing
the target; inspect any preserved work before retrying.

## Establish completion

After every task lands, verify the current target and close the goal:

```bash
hivewire goal verify health --key health-final --as lead
hivewire goal close health --as lead
hivewire status --all
```

Success means landed task commits plus a matching passed closure receipt. A board
status or a worker's "tests pass" assertion alone does not establish acceptance.
