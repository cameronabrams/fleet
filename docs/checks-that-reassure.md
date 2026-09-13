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
