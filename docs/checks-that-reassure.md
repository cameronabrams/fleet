# Checks that fail toward the reassuring answer

Catalogue started by a study session (five instances, all in one project) and
extended by nine sessions of one fleet, 2026-08-27 .. 2026-09-12: study,
production, repo, website, oldname and coordinator roles.

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
  a session started by hand for one task inside a role's lane, labeled
  *"renamed: 'sim-8c' became 'sim-repo'"*. It was never renamed and
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
  symptom (directory attribution, which had been honest and labeled all along)
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

- **A test that passed because the machine it ran on had the thing it was meant
  to do without.** A new `fleetspawn` class called `load_tool` without a
  `FakeConfig`, so it read the author's real `~/.config/fleet/fleet.toml` --
  which exists here and nowhere else. It passed locally, four ways, and failed on
  the first push (2026-10-13). The rule it broke is written down in CLAUDE.md:
  no test may read the real configuration. **The environment that makes a rule
  worth having is the one the author does not have**, which is why the rule
  cannot be checked by running the suite in the usual place. Running it with
  `HOME` pointed at an empty directory reproduces CI in two seconds, and is the
  cheapest version of the discipline this whole document is about.

- **A green suite while the live system ran code no test had approved.** Proving a
  guard bites means deliberately breaking the tool, and `~/bin/fleet*` are symlinks
  into this working tree -- so for the second or two each break was on disk, the
  broken file *was* the installed tool. `fleetmail` is driven by a 15-minute
  systemd timer that sends real mail and types into live panes. Two ticks landed
  inside the editing window on 2026-10-15; both happened to catch a coherent
  version and behaved correctly. That is luck. One of the breaks replaced `amend`
  with `record` in the retry path, which would have **destroyed the `drop` path in
  a live delivery record** -- not odd behavior, lost state. Another re-offered
  quarantined mail; another set a 30-minute budget inside a 15-minute poll.

  Flagged by a peer reading the file mid-edit, not by the author, and not by any
  test: the suite was green throughout, because the suite is exactly what the
  breaks were being run against. **An edit to a tool on a live PATH is a
  deployment, and a deliberate break is a deliberate deployment of broken code.**

  The practice, which costs one command: break it where the trigger cannot reach.

      git ls-files -z --cached --others --exclude-standard \
        | tar --null -T - -cf - | tar -x -C <scratch>/breakroom

  The suite runs entirely inside that copy -- `tests/support.py` resolves `bin/`
  from the repository root it is invoked from -- so the live symlink never points
  at a broken file. Verified end to end on 2026-10-15: the full suite passes in the
  copy, a break there fails, and the live tool is untouched.

  **This command has been wrong twice, the same way both times.** It was first
  written as `git archive HEAD`, which ships the committed tree when the change
  being proved is the uncommitted one. Corrected to `git ls-files -z`, which
  lists only TRACKED files -- so on 2026-10-19 a brand-new test file was missing
  from the copy and the suite could not import it. Each version copied everything
  except the thing under test.

  The failure is loud both times, which is the good outcome; the bad one is a
  guard that appears to bite against code that is not the code you wrote. **A
  rule written down is not a rule that has been run**, and a rule corrected once
  is not a rule that is now right.

- **A test that read a wrapped terminal.** The end-to-end proof that a restore
  launches the pinned release searched `capture-pane` output for the binary's
  path. `capture-pane` wraps at the terminal width, so on CI -- whose temporary
  paths are a few characters longer -- the path arrived split across a newline and
  the test failed (2026-10-17). It had passed here, repeatedly, for no better
  reason than a shorter `$TMPDIR`.

  The repair is the same one as the rest of this file: assert on something the
  environment cannot reformat. Each versioned fake binary now writes its own name
  into a log, so the check is `RAN 2.1.301` and not a path in a rendered pane.
  **Screen text is a rendering, not a fact**, and a test that reads one has a
  dependency on the window it ran in.

- **Four tools silently found nothing, and nothing looked wrong.** Pinning
  launches to a release by path (2026-10-17) changed every session's `argv[0]`
  from `claude` to `.../claude/versions/2.1.302`, and `fleet.procs.claude_procs`
  identified a session by `basename(argv[0]) == "claude"`. It returned an empty
  list for two days. `fleetcontext` listed no sessions, `fleetnudge` and
  `fleetspawn` could find none, and `fleetretire --park` answered *"no claude
  process named 'site-repo' is running"* about a session sitting in a pane.

  **Every one of those is an empty result that reads as "nothing to do."** The
  suite was green throughout: every test of the four callers supplied
  `claude_procs`'s output as a fixture, so the one assumption they all rested on
  was the one none of them checked. A shared helper mocked by everybody who uses
  it is a helper nothing tests.

  The missing test launches a REAL process with a real binary at a pinned path
  and asks whether the fleet can see it. Writing it took three attempts: the
  first set `argv[0]` to a pinned path while the process was really `python`, so
  `/proc/<pid>/exe` said python and the test failed against the fix; a shell
  script does not work either, because for `#!/bin/sh` the exe is the
  interpreter. **A fixture for a process-identity bug has to get the process's
  identity right.**

- **A rule I re-read the same morning I broke it.** This repository is public and
  its own `CLAUDE.md` says *"Nothing personal in this repo: no people, hosts,
  accounts or project sessions."* Over several days I put real session names into
  CHANGELOG entries, a docs example and three test docstrings -- each time because
  the real name made a failure concrete, which is exactly the trade the rule
  forbids. A standing grant to push meant nothing paused to ask, and the names
  reached a public remote (2026-10-19, found by the owner asking "you pushed
  this?").

  **It is the one fault in this file that no test can catch**, because the check
  would need the list of real names and the repository must not contain it. The
  guard has to be a habit at the only point where the information exists: read
  the diff before pushing, and ask of every proper noun whether it is the
  project's or somebody's.

- **An alarm that nothing can clear, which is how a true one gets missed.** The
  delivery section of `fleetwatch` has carried two red lines since 2026-10-15: a
  nudge that gave up after 1800 s, and a second attempt killed mid-retry. The news
  reached that session anyway — it wrote the report about the episode and said so
  the same hour — but `nudges.log` still records *never arrived*, and no tool can
  say otherwise. They clear only by ageing out of the seven-day window.

  **This is the same gap closed for mail on 2026-10-15 and not for nudges.**
  `fleetmail` got `notified_otherwise`, so a record can say the content arrived by
  another route, and `retry_undelivered`, so a transient failure is attempted
  again. `fleetnudge` got the first *only for the case it can detect itself* — the
  in-session decline — and never got the second.

  It is not quite an oversight, and the difference is the useful part. **Mail's
  retry had a driver and nudges have none**: `fleetmail fetch` already runs on a
  timer, so "try again" had somewhere to live, while a nudge is invoked once by a
  watcher and nothing comes back to it. **Mail's ack had an actor and nudges have
  no verb**: a session that read a message runs `fleetmail ack`, and there is no
  equivalent for a session that learned a result some other way.

  The direction matters less than it looks. A check that cannot be cleared is not
  safe merely because it errs toward alarm — a section with permanent red in it
  gets read past, and then a real hole arrives into a place nobody looks. That is
  the same end state as a check that fails toward reassurance, reached from the
  other side, which is why it belongs in this file.

  **Built on 2026-10-19**, the same day it was written down, because the owner's
  answer to "they expire on their own" was *"I don't like looking at them and I
  don't like not resolving them"* -- which is the whole argument above, from the
  person the alarm is for. `fleetnudge --delivered SESSION JOB "how you know"`
  appends an assertion that the result arrived another way; `fleetwatch` honours
  it and counts it. The retry half is still undecided and is the harder question:
  a nudge has no recurring driver, so "try again" has nowhere to live.

  One thing the building taught, which is the reason this entry is longer than the
  fix: the first version restated the hole-or-not rule inside the clearing tool,
  and its dry run offered to clear **thirty** ordinary retry lines where the report
  flagged two. A tool that silences an alarm and a tool that raises it cannot hold
  separate copies of what the alarm means. The rule now lives in `fleet.nudgelog`
  and both import it.

- **A check that was right and too late.** Designing a tool that appends one line
  to the human's `fleet.toml`, the proposed safeguard was "write it, then re-parse
  to confirm it is still valid". The check detects the damage correctly and
  prevents none of it: the broken file already exists while it runs, every tool
  parses that file at startup, and anything invoked in between simply dies. A
  duplicate key raises `TOMLDecodeError` and takes the whole fleet's tooling down
  at once, which was measured rather than assumed (2026-10-20).

  The correct form writes a temp file in the same directory, parses **that**, reads
  the value back from it, and only then `os.replace`. Same check, same code,
  different position in the sequence -- and the difference is between a failure
  made unreachable and a failure made legible after the fact.

  **Where a check sits is part of the check.** Nothing about its logic says whether
  it guards or merely reports, and "verify afterwards" reads exactly like
  "verify" right up until something is invoked in the window.

- **Testing the tool that changes things, by changing things.** Exercising
  `fleetspawn --go` by hand on 2026-10-20 spawned two real sessions onto the
  default tmux server. Every other tool then counted them as fleet members --
  `fleetsnap` asked for a brief and a colour for each, and the auto-roll would
  have offered to roll one, since nothing it reads says whose fleet a session
  belongs to.

  The tool had no way to be tried anywhere else: `fleetrestore` grew `--socket`
  when it got an end-to-end test, and `fleetspawn` never did. So the careless
  option was the only option, and `--go` previewing is no protection when the
  behaviour under test *is* what `--go` does.

  **A tool that changes the live system needs somewhere other than the live
  system to be tried.** Giving `fleetspawn` the same `--socket` was the actual
  fix; the discipline on its own would have held exactly as long as attention
  did.

- **An assertion whose two sides came from the same broken parser.** Tidying the
  changelog's duplicate heading blocks, the safeguard was "count the entries
  before, count them after, assert they match". The splitter recognised an entry
  by `- **`, and the released sections write theirs as plain `- ` — so it found
  none, the assertion compared **0 == 0**, and the rewrite emitted the headings
  with all 103 lines of `[0.2.0]` deleted beneath them. It passed (2026-10-20).

  The same blindness had already run over `[Unreleased]`, reporting 49 before and
  49 after while 13 plain entries would have gone. Both numbers were true about
  the parser and said nothing about the file.

  **A check and the thing it checks must not share a dependency.** The repair was
  to verify against something the splitter does not produce: the multiset of every
  non-heading, non-blank LINE, before and against after, per section and again
  over the whole file. A line is content the format cannot argue about, so a merge
  that preserves every one of them has preserved the entries whatever an entry
  turns out to be.

  Nothing was committed — the damage was found by reading the result rather than by
  the check. That is the part worth not repeating.

- **Thirty-one tests green in both places they were run, red where it counted.**
  The suite was run two ways -- in place, and with `HOME` pointed at an empty
  directory to keep it off the real configuration. The second is also how CI runs,
  and an empty `HOME` means an empty `~/.local/share/claude/versions`: so every
  test of the version pinning took the no-version-store fallback, expected bare
  `claude`, and passed. On a machine that actually has a version store, thirty-one
  of them fail.

  Nothing caught it until `scripts/release.sh` ran the suite **in the working
  tree** and refused to release (2026-10-20). CI could never have caught it: CI
  has no claude installed, so CI is permanently in the branch that passes.

  **An isolation measure is also a blindfold.** Emptying `HOME` is right for
  keeping tests off a real configuration and wrong as the only way the suite is
  ever run, because it empties everything else that lives there too. Run it both
  ways; and a test about which binary gets launched must SAY which it expects
  rather than inheriting whatever the host happens to have.

- **A green release gate over a red docs build.** `tests.yml` and `release.yaml`
  were both green on the v0.3.0 tag while the Read the Docs badge in the same
  README turned red (2026-10-20). Nothing in the repository builds the
  documentation, so the only thing that ever parses a docstring as RST runs after
  the push, on a service whose verdict reaches the author as a badge color.

  The broken docstring was old and until that day unreachable. `fleet.history.scan`
  documents its return value as a column-aligned key table, which RST reads as a
  definition list and then trips over the continuation lines. No check had ever
  objected, because no check had ever read it: autodoc parses a module's docstrings
  only once that module has an `api/` page, and `fleet.history` got its first page
  in that release. **Documentation coverage is also error coverage.** An
  undocumented module's docstrings are unchecked text, and the day they are finally
  covered is the day they break the build — so the release that adds API pages is
  exactly the one most likely to fail this way, and was.

  Fixed in two places: the docstring is a literal block now, and `docs.yml` builds
  with `-W`, the flag Read the Docs already sets, on every push and pull request.
  `release.yaml` has a `docs` job that `publish` needs, so the gate is red before
  the tag instead of after it. Confirmed reachable by restoring the old docstring
  in a scratch copy: three warnings, exit 1.

- **A membership rule wired into the one tool that only draws a screen.**
  `belongs` was written to tell this fleet's panes from another fleet's, tested
  three ways, and imported by `fleetboard` and nothing else (2026-10-20). Every
  tool that ACTS -- `fleetsnap`, `fleetupgrade`, `fleetretire`, `fleetcontext`,
  `fleetnudge`, `fleetwatch`, `fleetwaiting`, `fleetrestore` -- still gated on
  `@agent` alone. The rule was correct, the tests were real, and the auto-roll
  could still have restarted a stranger's session.

  It reads as closed because the hard part looks done. **Ask which callers a new
  rule has, not whether it is right**: a correct answer reachable from one display
  is a correct answer nothing acts on. Found by grepping for the importers before
  flipping the rule, not by any test -- a per-tool suite cannot notice a function
  its tool never calls.

- **A fixture that could not reach the branch under test.** The strict flip and
  all eight tools went green first time. `belongs` returns True for everything
  when the fleet has no name of its own, and `tests/support.py` `BASE_TOML`
  declared no `[fleet].name` -- so `fleet_name(cfg)` was `""` in every test, every
  pane passed, and the exclusion never ran once. The suite was exercising the
  include-everything branch and reporting a pass on the other one.

  The arity errors that *did* fail were the giveaway: fixtures were short a
  column, which proves the format changed and says nothing about the filter.
  **A test that fails for the shape of its input has not yet tested the logic.**
  Fixed by naming the fixture's fleet, which turned 0 failures into 20.

- **The flip was safe for the panes that existed and not for the ones to come.**
  Preconditions were measured honestly -- 15 of 15 labeled, 0 unlabeled, checked
  against the configured name rather than against each other, since unanimous
  panes still vanish if `[fleet].name` disagrees with all of them. All true, and
  all about the present tense. `fleetrestore` stamped `@agent` and not `@fleet`,
  so the next power cycle would have rebuilt every session correctly and left all
  15 invisible to every tool.

  **A precondition over current state does not cover the code that creates new
  state.** The failure would have arrived at a reboot, in the recovery path, and
  looked like the reboot had eaten the fleet. Caught by an end-to-end test that
  builds a real tmux fleet and then looks for it -- the only test in the suite
  that exercises creation and membership in the same run.

- **`.strip()` ate the field whose absence was the point.** `@fleet` is the last
  column, an unset pane option renders empty, so the last row of `list-panes`
  ends in a tab; `.strip()` removed it, the row came up one field short, failed
  its arity guard and was dropped in silence. The enumeration's whole purpose is
  that nothing vanishes without a word, and the pane it silently dropped was the
  one carrying no fleet label -- the single most interesting case. Only the LAST
  pane was affected, so it would have been found by a human noticing one missing
  session, not by a test. `.strip("\n")` now.

- **A board test answered by the host's own kernel.** The reboot-marker tests
  mocked the update document and left the new live kernel read unmocked, so every
  assertion about that marker was answered by whichever kernel the test machine
  happened to have booted. Green here. Green for the wrong reason on a machine
  with a pending kernel, and green on a third branch entirely in a container with
  no `/lib/modules` at all.

  The same shape as the version-store tests that were green in two places and red
  in the only one that mattered, and the same fix: **a test about what the machine
  has must SAY what it expects rather than inherit it.** The harness pins the
  kernel state now, and the four branches each have a test.

- **`age()` takes a timestamp, and was handed a duration.** One line, caught by
  reading the other callers rather than by the suite: `age(ts)` returns
  `now - ts`, so passing it `now - since` reconstructs an epoch in 1970 and prints
  a three-day wait as roughly half a million hours. It would not have crashed, and
  a reader seeing `waiting 497654h` would have doubted the feature rather than the
  arithmetic.

- **The board's most urgent line was the one that scrolled off.** Not a check
  that lied -- a check that was right, printed, and never reached the reader. The
  board was 36 lines; eight of the fleet's seventeen panes are under 40 rows.
  Fourteen of those lines were the parked list, every entry durable and identical
  tomorrow; three were the footer carrying pending updates, the cluster stamp and
  every `!` warning. The largest block was sessions that are **not running**, the
  smallest was everything that changes, and the parked block grew each time a
  session was parked, pushing the footer further down with use.

  Found by a reader, not by a test: the owner went looking for a kernel reboot
  warning and ran the comparison by hand instead. **Anything that can scroll off
  should be the thing that does not change.** A true alarm printed below the fold
  is the same end state as a false one printed above it -- the sibling of the
  permanent-red-line entry above, one step earlier, where the line never reaches
  the reader at all.

  Worth keeping separate from its diagnosis. The peer that raised this reported
  the reboot marker as being in the hidden footer; it is in the header, on the
  board's first line, and has been since it landed. The *finding* was right and
  the *explanation* was wrong, and acting on the explanation would have moved a
  line that was already where it needed to be. Re-measure a peer's reasoning as
  well as its conclusion.

- **A silent pass is indistinguishable from an absent feature.** The kernel check
  printed nothing when the running kernel was the newest -- correct, and the
  reason the owner could not tell whether the board had checked at all. The
  doctrine already covers the unreadable case, which renders `?`; this is the
  same rule from its other side, where the board *can* answer and the answer is
  good news. One dim field, and it costs nothing to say.

- **An installer that printed six errors and exited 0.** `install` creates
  `~/bin` and then links the shipped skills into `~/.claude/skills` -- a directory
  that does not exist on a machine where Claude Code has never written a skill,
  which is exactly the fresh machine the script is for. Every skill link failed,
  the `ln` errors went to the terminal, and the script exited 0 because nothing
  checked.

  **An installer may be wrong in many directions; this is the one it may not be
  wrong in.** A human watching the output would have seen it. A human running it
  from a setup script, or an agent reading the status, would have recorded a
  successful install of a tool that was not there. Found by walking the
  fresh-machine path end to end on a throwaway `HOME` -- there were no tests for
  `install` at all, which is how the one path it exists for went unexercised
  longest: the person who maintains it has had a fleet on their machine for
  months.

- **A flag that satisfied a precondition and a check that did not know.**
  `fleetspawn --color blue` printed `would declare alpha = 'blue'` and then
  `BLOCKED: no color declared` three lines later. Both statements were true --
  nothing is written in a preview -- and together they read as the flag having
  been ignored. `fleetinit` ships `[colors]` empty, so this is the FIRST thing a
  new fleet sees, with no other output to weigh it against.

  Not a wrong answer: a right answer in a place where it could only be
  misread. **A precondition should be checked against what the run will do, not
  only against what is already on disk.**

- **A refusal that sent the human to do the work they had already done.**
  `fleetspawn` refused to launch without a brief and pointed at
  `examples/brief.example.md` — correct about the requirement and wrong about who
  should satisfy it. Whoever asks for a session has just described it out loud;
  the brief was already spoken, and the tool answered by handing back a form.

  Not a false pass, which is this catalogue's usual shape, but the same root:
  **a check that is right about WHAT is missing can still be wrong about who is
  missing it.** When a refusal names a file, ask whether its content is already
  in the room.

  Mine, and worth recording separately: asked why the brief was necessary, I
  defended it; told the complaint was about copying and editing a file, I read it
  as "briefs are optional" and built that instead — removing the requirement from
  three places before being corrected. **The second reading of a short correction
  is worth more than the first implementation of it.** Reverted uncommitted;
  nothing shipped.

- **A true warning with no duration reads like any other.** `fleetwatch` said
  `CLUSTER QUERY FAILED -- live work is UNKNOWN, not none`, which is honest, and
  computed the fact every run while recording nothing. So a two-minute blip, a
  two-day maintenance window and a cluster that had never been reachable printed
  identical words, and a reader had no way to tell which they were looking at.
  The cluster was down for maintenance on 2026-10-22 and nothing in the fleet could
  say when it had started.

  Not a false answer -- an answer with a missing dimension, which is the same
  thing to whoever has to act on it. **A state worth reporting is usually worth
  timing**, and the stamp costs one file. The inverse mattered as much: a cluster
  with no recorded good read reports that, rather than an outage of zero length,
  which would date every first failure to the creation of the state file.

- **An empty table read after the fact proves nothing.** `scontrol show
  reservation` answered `No reservations in the system` when the cluster came
  back, and the tempting reading is "this site does not use MAINT reservations,
  so advance warning is impossible". A completed reservation is REMOVED, so an
  empty table just after a window is exactly what both cases look like. coord
  caught this in its own proposal and said so before anyone acted on it.

  The response is the part worth keeping: **build the recorder, not the parser.**
  Nothing interprets the text; it is kept when it changes. If a `MAINT` entry
  ever appears ahead of an outage the feature is real and can be built on
  evidence, and if none ever does, that is the answer too. A parser written now
  would have answered the open question with its own assumptions and then been
  believed.

- **A cap that counted the wrong lines, in a log that could not tell them
  apart.** A proposal to let the auto-roll sample its gates hourly while still
  acting once a day needed a cap the run could evaluate: "has `autoroll.log`
  already recorded a roll today?" Checked against the actual log before building
  it -- **of six `rolled=` lines, one was a roll.** Two were a restore converging
  the fleet, one an unpark, two were spawns from testing. The cap would have
  blocked the roll on two separate days, and hardest on the day after a reboot,
  which is exactly when the ladder is already stalled because the restore
  flattened every session onto one version.

  The log recorded *that* a session was put on a binary and never *what put it
  there*, and five different mechanisms wrote to it. **A field that several
  writers share has to say which writer it was**, or every reader invents its own
  rule for telling them apart. Found by running the proposed rule over the real
  log rather than over its description.

  A second one fell out while testing it: the roll driver writes `kind=roll` on
  its REFUSALS too, so an early version counted `rolled=none` as a roll and would
  have had the mechanism cap itself on the days it decided to do nothing -- which
  is most days. The test caught that, not the reading.

- **Three measurements of a rate, each adjacent to the rate the gate uses.** A
  design argument about the auto-roll turned on `v`, how fast the fleet falls
  behind. It was first measured from **install mtimes** on this machine -- wrong,
  as a peer caught: the updater takes the newest at each check, so releases
  landing between checks are skipped silently, and the store here jumps 2.1.304
  to 2.1.308. An install mtime is a lower bound on the release rate.

  The replacement was wrong too, in two further ways, and only re-running the
  measurement found them. **24 / the median gap is not a rate**: the median
  discarded a real 4.3-day stretch in which nothing shipped, and the reciprocal
  of the MEAN gap (0.85/day) agrees with count-over-span (0.86/day) while the
  median gives 1.06. And **publishes are not patch numbers**: `version_lag`
  returns `b[2] - a[2]`, 2.1.297 and .298 were never published at all, and the
  patch number advanced 1.00/day against 0.86 publishes/day.

  Three estimates -- 0.84, 1.06, 1.00 -- all plausible, all describing something
  real, and only the last describing the thing the gate subtracts. **Measure the
  quantity the code uses, not the one the English sentence suggests**, and when a
  peer corrects a number, re-derive it rather than adopting it: the correction
  here was right about the method and wrong about the answer.

## The rule that covers them all

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
