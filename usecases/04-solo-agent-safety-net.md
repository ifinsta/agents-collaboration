# 4. Solo agent with a safety net

One agent can use plans, questions, evidence and checked integration without any
parallel workers. It answers factual questions from repository evidence and asks
the human for unresolved consequential decisions. See the [outline conventions](README.md).

## Prepare and start

Configure executable gates and commit an approved goal with eligible tasks first,
as in [parallel delivery](01-parallel-feature-delivery.md). The single agent acts
as its own coordinator. Joining reports SOLO when no peers are available.

```bash
hivewire join --as codex-1 --kind codex
hivewire next --as codex-1
hivewire plan --as codex-1 --template
```

Fill every required template field and record the ordered steps. An unresolved
critical question blocks start; do not invent an answer to get past it.

```bash
hivewire plan --as codex-1 --set FIELD="EVIDENCE_BACKED_ANSWER" --step "IMPLEMENTATION_STEP"
hivewire questions
hivewire answer QUESTION_ID "ANSWER_WITH_SUPPORTING_EVIDENCE"
hivewire start --as codex-1
```

A coordinator or human may explicitly waive an eligible question with a recorded
reason. Waiver does not establish that an unknown fact is true.

## Finish, or stop with context

Implement each step in the assigned worktree and record actual evidence in order.
Commit the resulting changes in Git before submission.

```bash
hivewire step 1 --as codex-1 --evidence "ACTUAL_CHECK_RESULT"
hivewire submit --as codex-1 --evidence "COMMIT_AND_CHECK_RESULTS"
hivewire merge --as codex-1
```

If blocked, use `hivewire block "need the staging URL" --as codex-1` and resolve the
block before resuming through `start`. Alternatively, checkpoint and release with
a useful note. A released task must be claimed and started again before submission;
release is a separate recovery branch, not the next step before `submit`.

## Establish completion

The engine enforces critical-question, sequential-step and integration gates for
its own operations. It preserves uncommitted work when refusing unsafe checkout
operations, but it cannot stop arbitrary shell edits. After the goal's tasks land,
run goal verification and closure to record acceptance. A later second worker can
join the same board without rebuilding the task history.
