---
name: slurm
description: General SLURM mechanics and the traps that produce confident wrong answers - job arrays, chunked resumable runs, sacct accounting (-X/-D), requeues and NODE_FAIL, costing jobs from AllocTRES billing, and monitoring without silent failures. Site-independent; pair it with the site skill for concrete hosts, accounts, partitions and rates. Use when writing or fixing an sbatch script, costing a job or campaign, deciding whether to resubmit a failed task, building a job monitor, or interpreting sacct output. Triggers on "sbatch", "sacct", "squeue", "scancel", "slurm", "job array", "requeue", "NODE_FAIL", "TIMEOUT", "resubmit", "how much did that cost", "SU", "AllocTRES", "billing".
---

# SLURM: mechanics and traps

**Site-independent.** Concrete names — login host, user, accounts, partitions,
walltime caps, storage tiers, module names, rates — live in the **site skill**
for your cluster. This file is what holds true on any SLURM system, and nearly
every entry is a trap that produced a wrong answer once, with the evidence.

A theme runs through all of it: **each of these checks, when wrong, says
"fine".** None fails toward "something is broken", which is why they are
expensive — the wrong answer is the one that ends the investigation.

## Structuring work

**No hand-rolled job control inside a job.** A `for` loop running program after
program in one allocation is a scheduler-within-a-job; many sites prohibit it
outright. Use a **job array**: it parallelizes instead of serializing, and a
single failure can be requeued without rerunning everything.

**Do not invent tools.** `seff`, `sstat` and `sprio` are frequently not
installed. Check before relying on one; `sacct` is always there.

**SLURM snapshots the batch script at submit time.** It stores its own copy, so
the file on disk is thereafter a different object:

- editing a `.sbatch` **cannot repair** a queued or running job — `scancel` and
  resubmit;
- editing it **cannot break one either** — safe while jobs from it are in flight.

`scontrol write batch_script <jobid> -` recovers what a job **actually** ran,
the only reliable answer once the file has changed under you.

**Per-job scratch may not survive an `srun` step.** On at least one site,
launching an `srun` step deleted `$TMPDIR` and the parallel-scratch dir at the
moment the step started — a marker written just before `srun` was gone just
after, and `srun ... > run.log` left no `run.log`, so the run looked as though it
never happened. **Verify on your site before putting an MPI run in per-job
scratch**; the site skill records what was found there.

## Chunked resumable work: verify the checkpoint, not the log

A campaign longer than the walltime cap runs in chunks and must resume. **The
progress log and the resumable state are different files, and the progress log
runs ahead.** Anything reading "how far did I get?" from a log rather than the
checkpoint resumes into a hole.

**And a checkpoint's COUNTER can lie too.** Verify the **scope** of a counter,
not just its source — a per-segment count reads as cumulative.

Worked case (namdcph constant-pH, 2026-09): with `cphRestartFreq` unset,
resumable state was written only at exit. Two tasks hit TIMEOUT with `cphlog`
showing 2691 and 1995 cycles and **no restart file at all** — 95 h wall,
3.96 node-days, unrecoverable. After that fix, the second trap: namdcph restarts
its numbering per resume and replaces the trajectory behind a single-generation
`.BAK`, so each chunk silently overwrote the last. 19 segments were rescued one
boundary ahead of the overwrite.

**Before submitting anything that will be chunked:**

1. The checkpoint interval is **SET**, and much shorter than the walltime. An
   unset interval often means "never", not "default".
2. A restart file **exists on disk** after the first interval — `ls` it, do not
   infer it from log progress.
3. Each segment is **preserved to its own directory** before the next starts,
   verified by checksum.

The TIMEOUT is not the failure — the design expected it. The failure is being
survivable in the design and not in the configuration.

## sacct: which flags, for which question

**`-X` and `-D` are both required for accounting, for opposite reasons.** `-X`
suppresses `.batch`/`.extern` step double-counting. `-D` (`--duplicates`)
restores earlier runs of **requeued** jobs, which sacct hides by default.

**But `-D` is right for two questions and WRONG for a third:**

| question | `-D`? | why |
| :--- | :--- | :--- |
| what did this cost? | **yes** | requeued runs are billed; omitting it under-counts silently |
| should I resubmit this failure? | **yes** | SLURM may already have requeued it |
| is the job finished? | **no** | superseded NODE_FAIL rows read as permanent failures forever |

**A NODE_FAIL row does not mean resubmit.** Observed: without `-D`, 8 rows all
RUNNING; with `-D`, 11 — three tasks each carrying a NODE_FAIL **plus** a live
requeue SLURM made on its own. A session resubmitted three such tasks; had the
duplicates started, two jobs would have written the same outputs and **the
corruption would have looked like ordinary results**. Always `sacct -D` before
resubmitting, and look for a live requeue, not just a failure.

**Omitting `-D` under-counts unevenly** — only for users whose jobs get
requeued — so it reads as a per-user billing quirk rather than a query bug.
Against one monthly statement: without `-D` the total was -4.11% and one user
-8.8%; with it, three of four users matched **to the SU**.

**NODE_FAIL runs are billed — do not filter them out.** "A node crash is not the
user's fault" sounds right and moved a reconciliation further from the invoice.

**`sacct` COLLAPSES pending array tasks into one row:**

    12345_0      RUNNING
    12345_1      RUNNING
    12345_[2-7]  PENDING      <- one row, six tasks

So a row count is not a task count. **Never compare rows to the expected task
count** — the monitor fires early or never terminates. Count TERMINAL states
(`done + bad >= NTASK`); terminal tasks are always individual rows.

**`sacct` defaults to today.** Without `-S`, a month-old array returns nothing
and the honest-looking answer is zero.

## Costing a job

**`AllocTRES` already carries `billing=N`** — SLURM has applied the partition's
`TRESBillingWeights`. Use it:

    SU = billing x elapsed_hours          cost = SU x <site rate>

Read the weights off the cluster, not from memory:

    scontrol show partition <name> | tr ' ' '\n' | grep -i tresbilling

**Never derive cost from core-hours.** GPU partitions commonly weight `CPU=0`, so
core-hours give an answer that is self-consistent, plausibly sized, and wrong by
~3.6x. Worked case: 1,691 core-hours read as USD 16.91; the job actually cost
USD 60.59 — 140.91 GPU-hours at 43 SU each — because the 12 CPUs beside the GPU
billed at zero.

**`billing=` is not an invoice flag. Never use it to scope an account.** The two
failures are mirror images:

| | `billing=` present | absent |
| :--- | :--- | :--- |
| **charged** | the normal case | never |
| **NOT charged** | free-tier QOS rows carry it anyway | retired no-cost partitions |

**Absent is not missing data — keep the row.** `if not m: continue` silently
deletes real work from job counts and hour totals. Parse as
`b = billing if present else 0.0`. Do not impute a rate: that would invent
charges never billed. **Present is not charged either** — scope with
`-A <account>`, then trust the account.

**More traps, each a confident wrong number:**

- **Billing is on ACTUAL elapsed**, not requested walltime. Over-requesting
  costs nothing; never pad an estimate by the request.
- **Split on `Account`, not partition.** A free-tier account is zero regardless.
- **Job-name filtering is the whole ballgame on a shared account.** Classify
  explicitly and **print the unclassified remainder** — in one case it held
  5,319 SU from an adjacent project, which would have inflated the answer 15x.
- **Cost each account separately.** A campaign split across two funds costed as
  one gives a right total against the wrong invoices.

**Sanity check: recompute one job by hand.** 507,277 s = 140.91 h; x 43 =
6,059 SU. If the script disagrees, the script is wrong.

## Monitoring without silent failure

**Never verify a cluster command through `| tail`.** `$?` after a pipeline is
the LAST command's, and errors print at the TOP where tail cuts — so the
evidence and the status are both gone. Redirect, then read:

    ssh <host> "sacct ..." > out 2>&1; echo "exit=$?"

**Require the accounting to CLOSE; never infer completion from absence.** A
monitor that decides "done" because no RUNNING rows came back will announce
completion over a live array the moment ssh returns a banner instead of job
rows. Anchor the row count to the job id so a banner scores zero and the poll is
SKIPPED rather than believed.

**Emit on every terminal state** — `COMPLETED|FAILED|TIMEOUT|CANCELLED|OUT_OF_MEMORY|NODE_FAIL`
— not just success. A filter matching only COMPLETED is silent through a crash
and indistinguishable from "still running".

**Wait on a PID, never a pattern.** `until ! pgrep -f "<pattern>"` matches its
own `bash -c` command line and never exits; one ran five days. Use
`until ! kill -0 <pid> 2>/dev/null`. And note `kill -0` **succeeds on a zombie**,
so where it matters check `/proc/<pid>/stat` state too.

**Do not report success because a job left the queue.** Read its final state.

**Know how long the watcher itself lives.** A Claude Code Monitor armed `persistent`
expired after 30 minutes on 2.1.272 (verified 2026-09-15). A job that runs for hours
outlives it, and a dead watcher reports nothing. Watch long jobs from a process
outside the session (`setsid` loop, or `systemd-run --user` with output to a file),
or plan to re-arm at expiry; re-check on each new binary. A `systemd-run --user` unit
runs with the user manager's PATH, not your shell's (after a reboot, no `~/bin`), so use
absolute paths or set `PATH` inside the unit's script. In-session background tasks
are no safer: Claude Code has killed them on a "low on memory" alarm while page cache
was merely full (verified 2026-09-17). A detached watcher should register its own pid
(`$$` inside the script), not the `$!` of whatever launched it.

## Skill-file hygiene

**Never write a bare dollar sign before a digit in a skill file.** When a skill
is invoked with arguments, a dollar sign followed by a digit is substituted with
that numbered argument, and figures silently corrupt. Write `USD 12.34`.

## Reporting

State the job ID, partition, account, walltime requested and working directory.
If a job failed, **quote the actual error line** from `.err`/`.out` rather than
paraphrasing it. For anything billed that ran more than a few GPU-hours, give the
cost alongside the result and name the account it hit.
