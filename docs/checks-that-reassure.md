# Checks that fail toward the reassuring answer

Catalogue started by a study session (five instances, all in one project) and
extended by nine sessions of one fleet, 2026-08-27 .. 2026-09-12: study,
production, repo, website, literature and coordinator roles.

**The property they share is not a mechanism, it is a DIRECTION.** Each of these
is a check that can be wrong, and when it is wrong it says *fine*. None of them
ever failed toward "something is broken". That asymmetry is what makes them
expensive: the wrong answer is the one that ends the investigation.

Three mechanisms produce it.

## A. The check cannot distinguish itself from its target

- **`pgrep -f "<pattern>"` matches the waiter's own `bash -c` cmdline.** The
  loop waits on itself and never exits. Ran **5 days 5 hours** (2026-09-04); hit
  again 2026-09-12 in a *death*-detection branch, so the guard against silent
  death was itself defeated by silent death. Wait on a PID: `kill -0 <pid>`.
- **`ps -eo cmd | grep` TRUNCATES long cmdlines**, so a live process reads as
  dead (2026-09-09). `/proc/<pid>/cmdline` does not truncate; `ps -ww` also works.
- **`$?` after a pipeline is the LAST command's status.** `cmd | tail` reports
  tail's success whatever `cmd` did. Use `${PIPESTATUS[0]}` or redirect.

- **The tool written to catch this family committed a member of it.**
  `fleetwatch` decides who is watching a job by scanning claude children for the
  job id. On 2026-09-12 the coordinator ran a one-shot command containing a job id —
  and fleetwatch reported **the coordinator as a watcher**. A job would look watched
  because somebody merely *looked* at it, which fails toward "fine" exactly like
  everything else here. Fixed by requiring positive evidence of a poll LOOP
  (`sleep <n>` in the cmdline) and excluding the checking process's own tree.
  **A check that inspects processes is itself a process.**

## B. The proxy diverges from the thing it stands for

- **A progress log is not a checkpoint.** namdcph with `cphRestartFreq` unset
  wrote resumable state only at exit; `cphlog` showed 2691 and 1995 cycles while
  **no restart file existed**. Cost 3.96 node-days / USD 22.80 (2026-09-11).
  *Anything that reads "how far did I get" from a log rather than the checkpoint
  will resume into a hole.* — a production session
- **A checkpoint's COUNTER can lie even when the checkpoint is real.** The rule
  above ("read the checkpoint, not the log") is necessary and not sufficient:
  namdcph restarts its cycle numbering per resume, so a per-segment count reads
  as cumulative and each chunk overwrites the last behind a single-generation
  `.BAK`. Found 2026-09-12 by the production session, one boundary before 19 segments would
  have been destroyed. **Verify the SCOPE of a counter, not just its source.**
- **A 0-byte log is not an idle process.** Python block-buffers stdout when it is
  not a terminal, so a job doing 400 CPU-seconds of real work shows an empty log
  and reads as hung. The reflex — kill and re-run — destroys the work. Checked
  instead with `/proc/<pid>/stat` state and CPU time (2026-09-12).
- **A file written by an exit trap cannot warn you before exit.** A ring-geometry
  check read `diagnostics.log`, which the preserve trap writes on job EXIT, so it
  could not fire until the job it would have warned about was already over.
- **An ssh banner is not job state.** A monitor inferring completion from the
  ABSENCE of RUNNING rows announced "ALL TERMINAL: completed=0" over a live
  32-task array when ssh returned a banner (2026-09-08). Require the accounting
  to CLOSE (`done + bad >= NTASK`), never absence-of-negative.
- **A NAME is not an identity, once names are auto-generated.** `fleetgantt` drew
  a session started by hand for one task inside a role's lane, labelled
  *"renamed: 'htpolynet-8c' became 'htpolynet-repo'"*. It was never renamed and
  was never that role: the rename table is keyed by bare name across every
  transcript, and `<project>-<short id>` display names are not unique, so one
  transcript's real history was applied to another that merely ended up with the
  same auto name. The record printing that label carried `inferred: true` and
  `renames: []` in the same breath — **it contradicted itself and printed the
  confident half.** Found 2026-09-22 by the session putting the chart on a slide,
  not by the session that wrote the chart.

  Two things generalise. First, the direction: a chart with everything neatly
  attributed looks *more* correct than one with an unattached lane, so the wrong
  answer is the tidy one. Second, and worth more — **the bad inference disabled
  the guard that existed to catch it.** `fleetgantt` already passed
  `place_named=False` precisely to keep one-offs out of a role's lane, and the
  rename branch returned before that check was reached. Fixing the reported
  symptom (directory attribution, which had been honest and labelled all along)
  would have left the defect in place. When a guard did not fire, ask what ran
  before it, not only whether it is correct.

- **An exit code captured and not branched on.** A detached watcher ran
  `fleetnudge`, kept the return code, and logged `nudge sent (rc=2)`. The code was
  correct, the tool had printed `NOT DELIVERED: <reason>`, and the log line says
  *sent*. Whoever reads that line reads the prose, not the number beside it. Found
  2026-10-04 across six refusals and **two independently written watchers** — both
  authors reached the same root cause, and neither knew any nudge had ever failed.
  That makes it a property of a detached watcher rather than two mistakes: its
  stdout goes to a file nobody reads, so the only reader of the refusal is the
  script itself, and the script did not look.

- **`git log -S'<key>'` finds when a key APPEARED, not what it was set to.** Used
  on 2026-10-04 to date a configuration setting, then reasoned about with the
  file's *current* value — which made three delivered phone pushes look impossible
  against a mute switch that was "already configured". The switch had been
  configured, at a different path, to a file that never existed; it was merged
  with the one in use a day later. `-S` reports where an occurrence count changed.
  It cannot tell a key being added from a value being edited, and it says nothing
  about what the value was. `git log -p -- <file>` or `git show <rev>:<file>` says.

  The general form: **reading today's value onto a historical record.** The
  check — "was this configured then?" — came back yes and was answering a
  neighbouring question. It fails toward *inexplicable* rather than toward calm,
  which is the one mercy: the contradiction was at least visible, and got flagged
  as unresolved rather than given an invented cause. A peer resolved it in one
  look at `git show <rev>:fleet.toml`. The same day, that peer made the mirrored
  error in the other direction — generalizing six log entries from the three a
  tool had printed — so neither party's version of the record was the record.

## C. The check had only one possible outcome

- **A path nothing is ever written to.** `ls` on a repo-source dir "proved" a page
  was unpublished; publish writes elsewhere, so the check could not come out the
  other way (2026-09-03).
- **A tolerance wider than the error.** "Deployed differs from source by ~141
  bytes, so it is current" passes a stale deploy of *any* age. The exact test is
  built-vs-deployed, byte-identical.
- **A variable with no effect under test.** CONVERT vs LABEL timezone commands
  verified at offset 0, where both return the same string — a README with the two
  swapped passes identically (2026-09-05).
- **`sacct` COLLAPSES pending array tasks** into one row, so a row count is not a
  task count; and **without `-D` it hides requeued runs**, under-counting cost.
- **A guard that answers from the wrong part of the file.** A test meant to catch
  any tool still asking tmux for the old `@repo` label alone began
  `if "LABELS" not in src and ...`. Every one of those files imports `LABELS`, so
  the first clause was always true and the check never ran. Reverting all four
  tools to `@repo` alone produced **no failure at all** — the guard reported
  clean. Written while fixing the exact bug it was meant to catch, and caught
  only because the repository requires breaking a new guard to prove it can fail
  (2026-10-01). The fix: judge each format line, never the file.
- **A mock that answers a question the tool has stopped asking.** The same day, a
  test for `fleetrestore`'s verify step fed rows through a mocked `subprocess.run`
  and checked the parse. Narrowing the format string the tool hands tmux — the
  half that actually breaks — changed nothing, because the mock supplied the rows
  regardless. A mock makes the *response* a constant; whatever is in the
  **request** is then untested. Assert on the argv too.

## The rule that covers all three

**Before writing "verified", state the outcome that would have falsified it, and
confirm that outcome was reachable under the conditions you actually ran in.**
If you cannot name one, you have not tested anything.

And when a check *does* come back clean, ask which direction it fails in. If the
answer is "it would say fine", weight it accordingly.

## The part that is about people, not shells

Six of these were caught by a peer session, not by the author. The catches were
**ownership-driven**: whoever owned the pipeline found the error in claims made
about it. Not reviewer skill — proximity. The website session caught three of the
coordinator's because it owns publishing; a production session caught a
fabricated claim about its own awk; a repo session caught a test command shipped
without being run.

A single agent reviewing its own work catches roughly none of these, because the
error and the review share a blind spot. That is the strongest argument this
fleet has produced for being a fleet.
