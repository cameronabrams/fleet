# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**0.x means the command-line surface may still change between minor versions.**
The tools are run by hand and by agent sessions rather than imported as a
library, so "public API" here means a tool's arguments, its exit codes, and the
shape of its `--json`.

## Which number to bump

Decided against that surface, not by how large the change feels:

- **Minor** (`0.1.x` -> `0.2.0`) if any tool's **arguments**, **exit codes**,
  **`--json` shape**, or **where it writes** changed — including a value a caller
  could reasonably branch on, and including a removal.
- **Patch** otherwise: fixes, added output, new tests, documentation, and new
  optional arguments that change nothing for an existing caller.

Two things this rule is meant to stop. "It is 0.x, so anything may move" is an
argument for ignoring the rule rather than an application of it. And a number this
project *reports* — an amplification factor, a token count — is part of the surface
when someone has quoted it: a reader needs a version boundary to say which figure
they meant.

Releases are cut with `scripts/release.sh <version>`, which prints the pending
entries and makes you confirm the bump against this list.

## [Unreleased]

## [0.4.0] - 2026-10-27

### Added

- **`fleetboard`'s top line names the fleet**: `FLEET abrams  2026-10-13 10:34 EDT
  …`. A host can run more than one — the reason `@fleet` exists at all — and the
  header said only `FLEET`. Re-read on each draw, like the parked list, so a
  rename reaches a `--watch` board without a restart; the header and the
  membership filtering now take it from one helper rather than reading the name
  two ways. An unnamed fleet draws `(unnamed)` and a `fleet.toml` that will not
  load draws `(name unreadable)`: the two filter identically, since
  `fleet.panes.belongs` gets `None` either way, so the screen is the only place
  the difference can appear. Requested by Cameron.

- **`fleetnudge` leaves undelivered results on disk, and `fleetboard` says so.**
  The tool had two delivery channels and no durable one: when the pane would not
  take the keystrokes *and* the phone push was muted, the result existed only in
  `nudges.log` — and the caller holding it had already exited, because a detached
  watcher's last act *is* the nudge, so exiting non-zero tells a caller that is
  gone. Every give-up in one fleet's log that exhausted its wait window, three for
  three, had the push muted as well; the longest sat finished and unreported for
  7h47m and surfaced only because a human asked, and one of the three was inbound
  cross-fleet mail. **A give-up now writes the content to
  `<state>/pending/<session>__<job>.md`**, addressed to the session that was owed
  it and holding the text rather than a pointer to it. `fleetboard` draws a line
  above the updates count while any exist, and **`fleetnudge --pending [SESSION]`**
  prints them. Cleared by delivery or by the existing `--delivered`, which already
  means "this reached its reader" and already makes the caller say how it knows.
  Nothing is written when the news was not lost. An unreadable directory is
  `UNKNOWN` on both the board and `--pending`, never zero, and an unparsable file
  is counted rather than skipped. The positionals are now optional so `--pending`
  can stand alone; a plain misuse still names what is missing. Reported by a
  watcher that had been working around it per-caller. New module `fleet.pending`.

- **`fleetboard` says when the updates document has been overtaken by events.**
  It printed `updates: 47 updates -> 20261021` for nearly seven hours after those
  47 were installed: the age beside the line was honest, the count was about a
  machine that no longer existed. Now:

      updates: 47 updates were pending 6h ago -- SUPERSEDED, this machine is
               on 20261021 now; the check has not re-run

  No hook into the package manager and no change to the producer. The machine
  already says which snapshot it is on (`/etc/os-release` `VERSION_ID`) and the
  document already says which one it was aiming at; new `fleet.snapshot` compares
  them.

  The test is narrow on purpose: superseded means the machine reached the
  `target_snapshot` **the document itself named**, not that the two ids differ.
  On a release distribution `VERSION_ID` is something like `15.5` while a
  producer may record a date, so "differ" would hold for ever and the board would
  report supersession permanently. Unknown — unreadable `/etc/os-release`, no
  `VERSION_ID`, no target in the document — leaves the line exactly as it was.

- **`fleetroll NAME` rolls one named session onto a target binary**, read-only
  until `--go`. It does not pick the session, decide target policy, consult the
  soak or lag gates, or write to `autoroll.log` — those stay with the caller, so
  it is equally usable by hand.

  Two reasons, and the second is the larger. The keystroke sequence was
  hand-copied runbook prose, and prose is what failed: a coordinator read a
  resumed pane's **replayed** `/exit` farewells as five live failed exits and
  refused to roll a healthy session on nine consecutive fires. A tool that owns
  the sequence cannot make that mistake, because it reads the input line and
  never above it.

  And under auto mode an agent's raw `tmux send-keys` is denied, while the rule
  that unblocks it — `Bash(tmux send-keys:*)` — is a **prefix** rule that cannot
  constrain which keys reach which pane. `Bash(fleetroll:*)` permits one verified
  sequence against one named session. **The tool is what makes the grant narrow.**
  Granting it is the fleet owner's decision and nothing here asks for it.

  Eligibility is re-derived from `fleetupgrade --eligible --json` every run and
  never taken from the caller; if that cannot be read the roll is **refused**,
  because a roll that proceeded past an unreadable gate is a roll with no gate.
  It refuses a session that is the one asking (tested on process ancestry, not on
  the name), one already on target, one with no `--resume` uuid, a target with no
  binary in the store, and a busy pane or any dialog — **it never answers a
  dialog**. It never kills: a session that will not exit is holding something.
  It relaunches from the versioned path, never a bare `claude`, and accepts the
  session as back only when `claude agents` names it *and* its version equals the
  target exactly. Exit codes `0`/`2`/`3`/`4`/`5` name the state it stopped in.

- **The adoption log records `kind=`** — `roll`, `spawn`, `unpark`, `restore` or
  `adopt` — and `fleet.versions` gains `adoptions()`, `is_roll()`, `rolled_on()`
  and `rolled_today()` to read it.

  This exists because a proposed daily cap on the auto-roll could not be
  implemented against the log as written. The proposal — sample the gates hourly,
  act at most once per calendar day, the cap being "`autoroll.log` already has a
  `rolled=` line dated today" — is right, and the log could not answer it: of the
  six `rolled=` lines then present, **one** was a roll. Two were a restore
  converging the fleet, one an unpark, two were spawns. The cap would have
  blocked the roll on two separate days for reasons unrelated to rolling, and
  worst on the day after a reboot, which is already when the ladder is stalled.

  A refusal is not a roll either: the driver writes `kind=roll rolled=none` when
  a gate closes, and counting those would have the mechanism cap itself on the
  days it decided to do nothing. Lines written before the field existed have
  their kind inferred from the note, conservatively, in the direction that
  suppresses a roll rather than permitting a second one.

- **`fleetwatch` records when the cluster was last readable**, so a failed query
  carries a duration: `unreachable for 1h 20m -- last good 2026-10-22 10:00 EDT`.
  It computed `cluster_ok` every run and recorded nothing, so a two-minute blip, a
  two-day maintenance window and a cluster that was never reachable all printed
  the same sentence. Stamped on every run in `<state>/cluster-reach.json` —
  only a success moves `last_good`, but `last_checked` moving either way is what
  distinguishes "down since 08:35" from "nobody has looked since 08:35".

  A cluster with **no** recorded good read says so rather than reporting an outage
  of zero length, which would date the outage to the creation of the state file.
  Also in `--json` as `cluster_down_for_s`, and `fleetboard` puts it in its
  failure note. Raised by coord after the cluster was down for maintenance on the
  morning of 2026-10-22 and nothing in the fleet could say when it had started.

- **The SLURM reservation table is recorded, as an experiment, not parsed.** The
  same ssh round trip now runs `scontrol show reservation` and appends its output
  to `<state>/cluster-reservations.log` when it **changes**.

  SLURM holds planned maintenance as a reservation readable while the cluster is
  still up — exactly when a warning would help — but whether this site creates
  them is unknown. `scontrol show reservation` said `No reservations in the
  system` when the cluster returned, and a completed `MAINT` reservation is removed,
  so that is what an empty table looks like whether or not the site uses them.
  One look after the fact cannot tell the two cases apart, so nothing interprets
  the text. If a `MAINT` entry ever appears ahead of an outage the mechanism is
  real; if months pass with nothing, that is the answer too. It costs one extra
  line in a round trip that was already happening, and it sits before the
  `--END--` marker so a cluster without `scontrol` still reports its jobs.

- **`fleetspawn --brief-stdin` writes the brief, so nobody copies a template and
  fills it in.** Every session still needs a brief — it is the session's identity:
  role, scope, territory, who it answers to. What changed is who writes it. By the
  time anyone asks for a session they have already said what it is for, so writing
  it down is transcription rather than authorship, and answering with
  `cp examples/brief.example.md` asked them to redo the part already done.

      fleetspawn alpha ~/Git/x --window x --color blue --brief-stdin --go <<'MD'
      # alpha — repo session for x
      **Kind:** repo.  **Territory:** `~/Git/x` only.
      MD

  Three refusals, each a quieter failure than itself: nothing on stdin (a session
  told its role is nothing), the shipped example **verbatim** (a session told its
  role is to fill itself in, which then behaves plausibly and owns nothing in
  particular), and a brief that already exists. An *edited* example is accepted.

  `fleetinit`'s closing instructions and the `fleet-bootstrap` skill both stopped
  telling anyone to `cp` a template: the skill now says an agent writes the brief
  from what the human already told it, says it back in a sentence for correction,
  and does not interview for fields nobody mentioned.

- **`fleetinit --go` now sets the machine up, not just the configuration.** It
  writes `fleet.toml` and `briefs/` as before, places the `conventions.md` that
  `fleet.toml` points at, and runs `install --go`. One command instead of four.
  `--no-link` writes the configuration without touching `~/bin`. It still shows
  the plan and changes nothing without `--go`, and the plan names the symlinks.

  What it deliberately will not do is start a tmux server: which server a human
  is attached to is theirs to choose. That, a brief and the spawn are what is
  left, and it prints them.

  An existing `conventions.md` is never replaced — it holds a fleet's accumulated
  lessons once it has any. A failing `install` fails the whole setup rather than
  being reported over.

- **`fleetinit --from <host>` reads another machine's configuration over ssh**
  (`ssh <host> cat ~/.config/fleet/fleet.toml`), so the fleet.toml that already
  exists somewhere does not first have to be fetched by hand — keeping a copy to
  point at is itself a step to remember. `host:/other/path` names a different
  file. A local path still works and is tried first: a file that **exists** is
  never treated as a hostname, and a spec containing `/` or ending `.toml` is
  reported as a missing file rather than as an unreachable host, because the two
  send a reader to entirely different places to look. An unreachable host fails
  in seconds rather than hanging, and whatever `ssh` said is quoted back. An
  empty remote file is refused rather than built on.

- **`fleetboard` flags a pending kernel reboot itself, live.** New
  `fleet.kernels` compares the running kernel against the newest installed one on
  every draw, from the filesystem, with no subprocess and nothing installed. The
  header gains the releases and the wait:
  `REBOOT NEEDED (kernel 7.2.11 -> 7.2.14, waiting 72h)` — trimmed to the part
  that differs, since the shared `-1-default` tail carries nothing and the header
  already runs long enough to wrap a narrow pane. A differing *flavor* prints in
  full, because then it is the point of the line.

  The board already showed `REBOOT NEEDED` from the machine's update document, but
  that document is written by a **daily timer** while this fact flips the moment a
  `zypper dup` unpacks a kernel — measured on this machine, a kernel landed at
  08:42 with the next check due 06:21 the following morning, twenty-two hours of
  silence. It is also the direction a stale document gets wrong in the reassuring
  sense once the reboot happens, and an alarm nothing can clear is how a true one
  gets missed. The document's flag still counts, for the reasons a kernel
  comparison cannot see.

  An installed kernel is a `/lib/modules` directory that **contains a kernel
  image**; the directory alone is not enough, because a leftover owned by no
  package is a real thing on this machine and a leftover *newer* than the running
  kernel would warn for ever about a reboot that would change nothing. A running
  kernel that is no longer installed reads as pending. Unreadable renders
  `kernel: ?`, never silence.

- **`docs.yml` builds the documentation with `-W`** on every push to `main`, every
  pull request and every tag, mirroring `.readthedocs.yaml` (same Python, same
  requirements, same `conf.py`). `release.yaml` grows a matching `docs` job that
  `publish` depends on, so a tag cannot ship documentation that will not build.
  This is the one workflow that installs packages; the tools and their tests stay
  stdlib-only.

### Changed

- **`fleetnudge` can reach a session that is holding a background shell.** It
  could not, for that shell's whole life — which is the session a watcher nudge is
  most often aimed at. `claude agents` reports "at the prompt with a shell
  running" and "mid-turn" identically (`pid`, `kind` and `status` all agree, and a
  mid-turn `Bash` call and a detached shell are both a `bash` child), so an idle
  pane plus a `busy` status was refused as mid-turn. `fleetnudge` already held the
  rule that covers it — at the prompt while holding runtime is typeable — but keyed
  it on the statuses `shell` and `monitor`, which this version does not emit for
  that condition. The count now comes off the status bar, where the two differ, via
  new `fleet.panes.shells_running`; **`fleet.panes.reconcile` takes a third
  argument**, defaulting to `None` so an untaught caller keeps the refusing answer.
  The marker still wins: the screen is only `idle` when `esc to interrupt` appears
  nowhere, so mid-turn-and-holding-a-shell resolves to busy before the count is
  read. A grant is recorded on the delivery record (`shells`, `why_typeable`) and
  printed, because it is the one case where a line is typed into a session the
  status called busy. `fleetcontext` reports the same reconciliation; roll
  eligibility is untouched, since `fleetupgrade` reads `claude agents` itself and
  still sees `busy`.

- **`fleetwatch` runs with no cluster configured.** It raised `ConfigError` at
  import, exit 1, when `fleet.toml` had no `[cluster.<name>]`. Every caller read
  that as "runtime unknown": `fleetupgrade` (and so `fleetroll`) refused every
  session on such a machine, and `fleetboard` drew `?` in every work cell. Now no
  ssh is attempted and the report says there is no cluster work, with the
  watcher, nudge-delivery and client sections intact. **`--json` gains
  `cluster_configured`**, and `cluster_ok` is `true` in this case because the
  empty job list can be trusted. Exit status 0 where it was 1. Several clusters
  with none named is still an error.

- **`fleetboard` puts everything time-sensitive directly under the header**, and
  counts parked sessions instead of listing them (`fleetboard --parked` lists
  them). Pending updates, the cluster/context stamp, every `!` warning and any
  foreign pane now precede the live roster; the parked count comes last.

  Measured rather than guessed: the board was 36 lines and eight of this fleet's
  seventeen panes are under 40 rows. Fourteen of those lines were the parked list
  — durable, declared in a file, identical tomorrow — and three were the footer
  carrying the updates count, the cluster stamp and every red warning. The largest
  block was sessions that are not running; the smallest was everything a glance is
  for, and the parked block grows every time a session is parked, pushing the
  footer further down. The default draw is 23 lines now.

  The rule that outlives this layout: **anything that can scroll off should be the
  thing that does not change.** A true alarm printed below the fold is the same end
  state as a false one printed above it.

  `ALSO RUNNING` survives the collapse as its own `!` line. It is the one parked
  fact that is not durable — a session declared parked and running at once is a
  human's decision disagreeing with the machine — and a count must not swallow a
  contradiction.

- **The quiet kernel case says so.** A board that printed nothing when the running
  kernel was the newest was indistinguishable from a board that does not check:
  found by a reader going to look for the warning the day after it landed, not by
  a test. The header carries a dim `kernel <release>` when there is nothing to
  report.

- **An unlabeled pane is no longer assumed to be ours.** `fleet.panes.belongs`
  shipped permissive on purpose: zero panes carried `@fleet` when it landed, so
  excluding the unlabeled would have emptied every tool at once. Every pane is
  stamped now, so the exclusion is strict. The precondition was checked against
  the **configured** name, not against the panes alone — 15 of 15 labeled, 0
  unlabeled, and `[fleet].name` equal to the label they all carried, because panes
  that agree unanimously still vanish if the configuration disagrees with all of
  them. With no name of its own a fleet still counts everything as its own; that
  branch is reachable only before `fleetinit` has run.

- **Every tool that ACTS now asks whose fleet a pane is in.** `belongs` was wired
  into `fleetboard` and nowhere else, so the rule was correct in the one place
  where being wrong costs nothing, while `fleetsnap`, `fleetupgrade`,
  `fleetretire`, `fleetcontext`, `fleetnudge`, `fleetwatch`, `fleetwaiting` and
  `fleetrestore` all still gated on `@agent` alone. New
  `fleet.panes.ours_agent_pane` asks both questions in one place. Each tool
  reports what it excluded and **which label was missing**, since a pane with no
  `@agent` is not a session while a pane with no `@fleet` may be one of ours
  stamped by a tool too old to say so.

### Fixed

- **A screen/status disagreement named the wrong cause, and named it as the only
  one.** When the pane reads idle but `claude agents` reports `busy`,
  `fleet.panes.reconcile` said "the busy marker may have moved" — a guess that
  sent two sessions after a stale TUI marker for eleven days. Measured across
  every labeled pane on 2026-10-26 (2.1.302 and 2.1.308): the marker was present
  in every pane that was genuinely mid-turn, and the panes reporting `busy` with
  an idle screen were exactly those holding a live background shell. `claude
  agents` reports "at the prompt with a background shell" and "mid-turn"
  identically, and nothing else in its JSON separates them. The sentence now
  names both possibilities. **Behavior is unchanged** — both directions still
  resolve to busy, because never typing is the safe error — but the consequence
  is not cosmetic: a session whose work *is* a long background shell reports
  `busy` for that shell's whole life, so a nudge to it can never be delivered,
  and two of the three delivery give-ups in this fleet's log are that case.
  `fleetnudge` already holds the rule that would cover it (a session at its
  prompt holding runtime is typeable) but keys it on the statuses `shell` and
  `monitor`, which this version does not emit for it.

- **`fleetboard` read `kernel: ?` on every WSL2 machine, permanently.** Windows
  supplies the WSL2 kernel, so `/lib/modules` holds no image and `fleet.kernels`
  found nothing to compare. For a release ending in `-WSL2` it now compares the
  running kernel against the release in the boot header of the Windows-side image
  that `wsl --update` replaces. When they differ, the header says
  `(kernel A -> B, waiting 3d; wsl --shutdown)`, because a reboot of the
  distribution does not load the new kernel. An unreadable image is
  `kernel: ? (WSL kernel image unreadable)`. `/lib/modules` is no longer read
  under WSL2, because a distribution kernel package would sort above the
  Microsoft release and read as a reboot owed for ever. A custom `.wslconfig`
  kernel is not supported and reads as pending.

- **`fleetboard` showed `?` in every session's work column when no cluster was
  configured.** The column is now blank, and the stamp reads `context as of …;
  no [cluster] configured, so no cluster work`. A configured cluster that cannot
  be read is still `?`, and so is one whose `fleet.toml` cannot be **parsed**:
  `cluster_configured()` returns `None` there rather than raising. It is re-read
  on every draw so `--watch` picks up an edit, which is exactly when the file is
  most likely to be half-written, and the watch loop catches only
  `KeyboardInterrupt` — `parked` and `updates` already guarded this; it was the
  third sibling and the one that did not.

- **`fleetroll` refused every session `fleetspawn` had started.** It read the
  session's uuid only from `--resume` in argv, and `fleetspawn` launches with
  `--name X '<prompt>'`. The uuid now comes from `claude agents --json`, matched
  by pid, and only when that entry carries the same name. A different name is
  refused. argv `--resume` is the fallback; with neither source it refuses as
  before. The plan's `resume` line says which source it used. When the two
  disagree, as after a `/clear`, claude's answer wins and the plan says so.

  The name on that entry must agree with the session being rolled, and that
  check applies **whichever source supplies the uuid**. It was inside the
  branch that uses claude's answer, so it fired only when the entry happened
  to carry a `sessionId`: an entry naming the pid something else without one,
  or a pid listed twice, fell through to the argv fallback and was used --
  the wrong conversation under the right label, which is the outcome the
  check exists to prevent, reached by the path it did not cover.

- **A hand-written copy of `fleetinit`'s usage block in its docs page** had
  drifted within a day of the tool growing options. The page already renders the
  tool's own header via `tooldoc`, read from the script at build time; a second
  copy of something that cannot drift is only a place for it to.

- **`install` created `~/bin` but not `~/.claude/skills`**, so on a machine where
  Claude Code has never written a skill — precisely the fresh machine the script
  exists for — every skill link failed with `No such file or directory`. **And it
  still exited 0**: six errors on screen and a success to anything reading the
  status. It creates the directory now and exits 1 if any link could not be made.
  Found by walking the fresh-machine path end to end on a throwaway `HOME`; there
  were no tests for `install` at all, and there are now.

- **`install` created directories on a dry run.** `mkdir -p ~/bin` ran whether or
  not `--go` was given, which contradicts the read-only-by-default rule the rest
  of the tools follow. Both `mkdir`s are gated now.

- **`fleetspawn --color` contradicted itself on the first spawn of a new fleet.**
  It printed `would declare alpha = 'blue'` and then, three lines later,
  `BLOCKED: no color declared`. `fleetinit` ships `[colors]` empty, so every new
  fleet hits this on its very first spawn, with nothing else on screen to weigh
  the contradiction against. `--color` now satisfies its own precondition, the
  refusal names the flag that clears it, and the status line reads
  `blue (pending --go)` rather than `NOT DECLARED`.

- **The bootstrap skill's prerequisites predated `fleetinit`** — it told a
  coordinator to copy `fleet.example.toml` by hand, did not mention naming the
  fleet, and said to label a coordinator's pane with `@agent` alone, which since
  the strict-membership flip leaves that pane outside the fleet every tool can
  see. The README said the same about copying the example.

- **`fleetrestore` now stamps `@fleet`, which is what kept the flip from being an
  outage.** It stamped `@agent` alone. With membership strict, a restore after a
  power cycle would have rebuilt all 15 sessions correctly and left every one of
  them invisible to every tool — and it would have arrived at the worst possible
  moment, looking like the reboot had eaten the fleet. The flip was checked
  against the panes that exist; this is the path that creates new ones.

- **A trailing empty `@fleet` was eaten by `.strip()`.** `@fleet` is the last
  column and an unset pane option renders as an empty field, so the last row of
  `list-panes` output ends in a tab. `.strip()` removed it, that row came up one
  field short, failed its arity guard and was dropped **in silence** — the one
  outcome the exclusion reporting exists to prevent, on exactly the pane that most
  needed reporting. Only the last pane was affected, which is why it would have
  been found by a human rather than by a test. Now `.strip("\n")`, in `fleetsnap`,
  `fleetupgrade` and `fleetwaiting`.

- **The test fixture had no fleet name**, so `fleet_name(cfg)` was `""` in every
  test, `belongs` took its include-everything branch and the exclusion never ran.
  The first version of this work went green against a fixture that could not
  reach the code it was testing. `tests/support.py` `BASE_TOML` declares
  `[fleet].name` now.

- **Two real session names in a public test fixture.** `tests/test_fleetupgrade.py`
  used live session names where the placeholder vocabulary belongs; replaced with
  `alpha`/`beta`/`delta`. Not named here, because naming them in the changelog
  puts them back in the repository the scrub was for.

- **`fleetinit` was the only tool in `bin/` with no `~/bin` symlink** — `install`
  globs `bin/*`, so it simply had not been re-run since the tool landed.

- **The documentation build, and the hole that let it break unnoticed.**
  `fleet.history.scan`'s docstring is a column-aligned key table; RST reads that
  as a definition list and warns three times, and Read the Docs sets
  `fail_on_warning`. It had never been parsed before, because autodoc reads a
  module's docstrings only once that module has an `api/` page — `fleet.history`
  got its first one in 0.3.0, so adding the API pages is what exposed it. The
  docstring is a literal block now, which renders as it already reads in source.

## [0.3.0] - 2026-10-20


### Added

- **`fleetrestore --go` records the adoption too, as the fleet's largest.** Every
  session comes up on whatever `claude` resolves to, which need not be what the
  manifest recorded — the same hole as an unpark with the whole fleet in it. Two
  lines: an **intent** line before anything launches, saying so in the line, and an
  outcome line after `verify`. Before is the right place for the first, because a
  line written after a run that never finishes does not exist, and the unfinished
  restore is the one worth a record.

  The outcome does not claim a version was adopted — `verify` compares pane labels
  and directories, not binaries — and a tmux that cannot be listed reads `COULD NOT
  CHECK` rather than being counted as one failed session, which would have logged
  *14 of 15 matched* for a check that matched nothing.

- **`fleet.versions.installed(ask_binary=False)`**, the form that will not run
  `claude --version`. Two callers must not: `fleetrestore` is the recovery path,
  where nothing may need anything else to work first, and `record_adoption` writes
  one log line, which is never worth an exec. Both were added calling the executing
  form on 2026-10-16 and the restore's end-to-end test caught it — its fake `claude`
  recorded a `--version` call that displaced a real launch.

- **A fleet can tell its own panes from another fleet's.** Membership was "a pane
  with `@agent` on the default tmux server", so two fleets sharing a machine were
  indistinguishable to every tool: `fleetsnap` demanded a brief and a color for a
  stranger's session and the roll would have offered to restart one. Raised
  2026-10-20 after exactly that happened.

  `[fleet].name` declares a fleet's own name — falling back to `[mail].fleet`,
  which has carried one since mail needed a namespace, so an established fleet
  needs no edit. `fleetspawn` stamps it on each pane it creates as `@fleet`, and
  `fleet.panes.belongs` is the one place that decides membership: our name belongs,
  **another name does not**, and an unlabeled pane belongs *for now* and is
  **counted and reported** rather than passing silently.

  Including the unlabeled is deliberate: zero panes carried `@fleet` when this
  landed, so excluding them would have emptied every tool at once. `fleetinit
  --label-panes` is the one-time step, and it refuses to touch a pane already
  carrying another fleet's name.

  `@fleet` held a different meaning before and was retired — it named a group
  *within* one fleet. Nothing carried the old value when the word was reused.

  `LABELS` is now two columns, which shifted the positional parse in seven tools;
  a derived configuration also drops `[mail].fleet`, since `[mail]` travels but the
  name inside it is an identity — found by a test, because `--keep` supplies no new
  name and so would never have corrected it.

- **`fleetspawn --socket`**, so a tool that creates panes and launches sessions can
  be tried somewhere other than the live fleet. `fleetrestore` has had it since it
  grew an end-to-end test; `fleetspawn` had not, so exercising `--go` by hand on
  2026-10-20 put two real sessions into the fleet, which every other tool then
  counted as members. `$TMUX` is no longer inherited either: a run from inside a
  pane could otherwise build on that pane's server.

- **`fleetinit`: create a configuration, so a fresh machine has something to run
  against.** `install` exits 2 without a `fleet.toml`, so this was the step that
  blocked every other step — built first for that reason rather than because it was
  smallest.

  **The repository ships the schema and the questions, never the answers.** Defaults
  travel from an existing configuration (`--from`), which copies how someone likes
  fleets to work — `[human]`, `[paths]`, `[spawn]`, `[context]`, `[notify]`,
  `[mail]`, every `[cluster.*]` — and leaves behind what belongs to one fleet.
  Measured on a live 313-line config: 99 lines travel. `[colors]` and `[owners]` are
  **emptied rather than deleted**, since every fleet has a roster; `[parked.*]`,
  `[retired.*]`, `[authority]` and `[updates]` are dropped. Prompts and CLI flags
  cover a machine with nothing personal to hand, and `--save-profile` writes the
  shareable subset out to keep.

  Copied as **text**: there is no comment-preserving TOML writer in the standard
  library, and the comments are why a configuration is worth reading. An existing
  `fleet.toml` is never overwritten.

- **`fleetspawn --color`, `--create-dir`, `--brief-from-example`** — the refusals
  preflight already names, turned into offers. `--color` appends the declaration
  through `fleet.config.declare`; `--brief-from-example` copies the template and
  **stops**, because a template brief is a session told its role is to fill itself
  in, which fails quietly where a missing brief fails loudly.

- **`fleet.config.declare` and `write_verified`** — a tool may append a declaration
  a human supplied; it may never regenerate, reorder or remove. The write is proved
  in a temporary file and only then `os.replace`d: a duplicate key raises
  `TOMLDecodeError` and stops every tool at once, so "write then re-parse" detects
  that correctly and prevents none of it.

- **`fleetnudge --delivered` clears a delivery hole that is no longer one.** A
  nudge that gave up stayed in `fleetwatch`'s report until it aged out of the
  seven-day window, even when the result had reached its session another way.
  `fleetmail` got both halves of this on 2026-10-15 — a record that the content
  arrived another way, and a retry — and nudges got neither.

  It appends, never edits, and carries who asserted it and why: weaker evidence
  than a delivery, stronger than the inference `fleetwatch` refuses to draw from a
  later nudge, so it suppresses where that only annotates. It refuses without a
  reason and refuses when there is nothing to clear; the dry run lists the records
  it would clear. `fleetwatch` counts them, dim rather than red.

  **The rule for "is this still a hole" moved into `fleet.nudgelog`**, shared by
  the tool that raises the alarm and the tool that clears it. The first version
  restated it and its dry run offered to clear thirty ordinary retry lines where
  the report flagged two.

  The retry half is deliberately not built: a nudge has no recurring driver, so
  "try again" has nowhere to live, and deciding whether nudges retry at all is a
  judgment about what the delivery section is for.

- **`fleetboard` shows this machine's pending software updates**, when an
  `[updates]` section points it at a file some other program derives them into.
  It reads and declares nothing, the same contract as its other sources. The path
  is configuration because it names a host. Requested by a peer session
  2026-10-19; the producer is that session's, not this repository's.

  **Nothing renders as "up to date" except a check that ran and found nothing.** A
  missing file, an unparseable one, an unknown `schema`, `ok: false`, or no
  readable timestamp all read as a problem; a check older than `stale_hours`
  (default 36, for a daily producer) shows its numbers marked `STALE` in words
  rather than leaving a reader to do arithmetic on an age. A file with no `schema`
  key is read as schema 1 — the contract the first producer was written to, and
  treating its absence as a mismatch would break the feature on arrival.

  `reboot_needed` is flagged in the header beside the clock: it is the one fact
  here that is true *now* and about the fleet rather than a package list, since a
  reboot ends every session. It is raised **even when the check failed** — the
  producer derives it outside the branch that can fail, so that it survives one,
  and withholding it would hide a fleet-ending fact at exactly the moment the
  other half of the check broke. Only an unknown source withholds it.

- **`fleetspawn --go` logs the adoption, because every launch is one.** There is no
  version argument and none is wanted, so a spawn — and an **unpark** — puts a
  session onto whatever `claude` resolves to. That was invisible, and it was not a
  rare path: the fleet's entire version spread was unparks rather than rolls, and
  the auto-roll log said `rolled=none skipped=15` at 09:50 on 2026-10-16 while a
  session went onto an 18-hour-old release at 09:51. Reported by coord, from
  the fleet's owner asking where the new binary was soaking.

  One line into `<state>/autoroll.log`, which is the auto-roll's own log and not a
  new one: a second file would have said `rolled=none` twice. `to` is read from the
  running process rather than from what was installed when the command was
  composed, since a session takes up to `--wait` seconds to come up. **Recorded,
  not gated** — a park and unpark is a human act with its own reasons — and a log
  that cannot be written is printed without failing the spawn.

- **`fleetmail timer` warns when it is about to point a timer at a working tree.**
  It bakes in the path of the copy it is run from, which is what makes a deployed
  checkout work — and the same property that let a 15-minute timer run the
  directory this repository is developed in. On 2026-10-15 two ticks landed inside
  an editing window while guards were being broken on purpose; both caught a
  coherent version by luck, and one of the breaks would have destroyed live
  delivery state. A dirty checkout is the one cheap, checkable symptom, and
  **unknown warns the same as dirty** — a copy git cannot speak for is not one to
  point a timer at. It warns; it does not refuse.

- **`fleetupgrade --eligible` stops calling the on-disk window a soak.** Nothing
  here exercises a release while it waits, so the word invited tuning it as if it
  were evidence-gathering. The flag keeps its name, because the driver's runbook
  uses it; the help text, the gate table and the per-session reason now say *on
  disk* and say plainly what the delay buys. Raised by coord, 2026-10-16.

- **`fleetupgrade --eligible`** — who could be rolled onto a new binary right now,
  and, for everyone else, every reason they could not. The machine half of a roll
  that nobody has to trigger; acting on it stays with the `fleet-upgrade` skill,
  because deciding to restart needs asking a session what it has running that its
  ledger does not name, and asking needs an agent. Built from coord's auto-roll
  spec of 2026-10-15.

  **Every gate is a refusal, and a gate that cannot be evaluated refuses.** An
  unreadable `claude agents`, a failed cluster query, an unreadable install time:
  each is a reason not to roll, never clearance. The direction matters more here
  than on a board — a board that fails toward reassurance shows a wrong color, a
  roll that fails toward reassurance restarts a session that was holding something.
  A refusal is not a failure, and the report says so: staying stale is the correct
  outcome of a skip.

  Gates: the hold file, the asking session itself (by uuid, never by name), soak
  (`--soak`, default 24h), lag (`--lag`, default 2 releases), no exit-blocking child
  — **skipped, never killed** — idle per `claude agents`, and no live cluster work
  without a re-arm ledger. Three more are not in the spec, and each is something the
  table already warns a human about while an unattended driver gets no warnings: a
  **backgrounded** session (resuming its old uuid would fork it), an **unresolved**
  resume handle, and a missing one.

  Lag is a patch distance within one `major.minor`; across a minor it is reported as
  uncountable, which satisfies any lag. Uncountable means *behind by more than this
  can count*, not *not behind* — reading it as zero would hold back exactly the roll
  most worth making.

  **An unidentifiable asker refuses everyone**, like every other failed source
  here. With `CLAUDE_CODE_SESSION_ID` unset nothing is self-excluded, and the gap
  is invisible from inside: the driving session's only remaining exclusion is
  `status is busy`, true merely because running the tool made it busy, so a driver
  reading about a session other than itself would see it eligible and roll the
  thing it is running in. `--json` carries `asking` at the top level — the uuid or
  `null` — so a driver can assert on it instead of searching its own row for a
  sentence, which it could only do by already knowing which row is its own.
  Reported by coord on 2026-10-15, from the JSON, where the text report's banner
  does not reach.

  It runs one command, `fleetwatch --json`, and that is pinned by a test on the
  parsed syntax rather than on the text: the first version grepped for `kill` and
  failed on four comments saying it never kills.

- **A hold file, `<config>/no-roll`** — a standing refusal in place of a per-roll
  decision. Present and empty holds everything; one version per line refuses those
  versions as targets; present but unreadable **holds**, because it was put there to
  stop something and a read error is not permission to proceed.

- **`fleetspawn --go` applies the declared color itself.** It required a `[colors]`
  entry, refused to spawn without one, printed the `/color` line — and then left it
  to be typed by hand, so the color was declared, validated and applied only if
  someone remembered. A session that misses it looks like somebody else's window on
  every board that reads the label.

  The old comment gave a real reason not to type it: keys sent into a session still
  working its first prompt arrive corrupted or land as prompt text (observed
  2026-09-07). That hazard is now solved rather than avoided. It waits for the pane
  to go idle by `fleet.panes.screen_state` — the same reader `fleetnudge` uses — and
  types through `fleet.panes.type_line`, which reads the input line back and confirms
  it holds exactly the intended text before Enter.

  **Success is the session's own `agent-color` record**, the one `fleetsnap` reads,
  not the keystrokes going out: sending keys cannot fail, and a check that cannot
  fail is not evidence. A color that will not apply is reported with the line to type
  and does **not** fail the spawn — the session is up and only its label is wrong,
  and a retry would respawn a live session. A session already carrying the color is
  not typed into. New flags: `--no-color` and `--color-wait`.

  Taken from `pkgyasi/fleet`, which made the argument and wrote it first.

- **`fleet.transcripts.registry_uuid(pid)`** — the session uuid a running session
  records for itself in `~/.claude/sessions/<pid>.json`.

  `uuid_from_descendants` needs a live child process, which a session has only while
  it is mid-tool-call — exactly what `apply_color` has just finished waiting for it
  not to be. Measured across 14 live sessions on 2026-10-13: the registry answered
  for all 14, the descendant walk for **one**, the only session doing work at that
  moment. The walk stays as the fallback, because it reads a path *handed* to the
  session and so is evidence of a different kind.

  The entry's own `pid` field is checked against the filename. Pids come round
  again, and a stale file left by a dead session whose number was reissued would
  otherwise hand back another session's transcript — a restore that reopens the
  wrong conversation.

- **`fleetcost` reports compliance with the 800-character rule, measured on the body
  and stated as the share that obeys.** Both halves of that are load-bearing, and
  both have been got wrong. Measured on the record the answer is 0% and always will
  be, because the envelope alone exceeds the ceiling: a rule about what a session
  writes, scored against something it does not write. And the first report of this
  figure gave the share that *breaks* the rule under the name compliance — 55% where
  **45% obey** — which reads as the convention working when it is the same number
  saying it is not.

  The line also prints the envelope's share of the re-read bill: **36%**, a floor no
  convention about what sessions write can reach. Capping every body at 800
  characters would bring the bill to 72% of what it is, so the rule's ceiling is a
  28% saving.

- **`fleetboard`'s header carries the date as well as the time.** The board is
  normally read on a long-lived `--watch` pane and glanced at in passing, where a
  bare `10:34` is consistent both with a redraw a minute ago and with a board that
  stopped redrawing yesterday at the same hour. The previous entry under *Fixed* is
  the case: a watcher 21h50m old presented a 22-hour-old reading as a live fact,
  and its clock looked right throughout. The stamp is taken on each draw, which is
  pinned by a test, because a value computed at import looks correct for as long as
  anyone tests it in a fresh process.


- **`fleetboard` shows each session's working directory, and lists parked sessions
  under a rule below the table.** Requested 2026-10-08.

  The directory comes from `claude agents`, the only source on this board that
  knows it. `$HOME` renders as `~`, and an over-long path is cut from the **left**,
  because paths are distinctive at their end — two sessions under one project
  directory agree in the first components and differ in the last, so a right-hand
  cut would make the column widest exactly where it stops telling them apart. The
  width follows the terminal between 14 and 42 characters, falling back to 80
  columns when stdout is not a terminal.

  Parked sessions come from `[parked.<name>]` in the configuration. Parked is a
  *declaration*, not an observation, which is why it can be shown for a session
  with no process and no pane — and why those rows sit under a rule instead of at
  the foot of the same list: they are a different kind of row, and without the rule
  they read as live sessions that happen to be quiet.

  A parked row carries no state, version, context or work. It has none, and
  printing `?` there would say they were unknown — this board's rule about `?`
  read backwards, since nothing failed. For the same reason the row gets its own
  narrow layout rather than borrowing the table's columns to leave them blank.
  **Retired** sessions are not listed: they are not coming back, and a board is
  about what might.

  A name both running and declared parked is marked `ALSO RUNNING`. That is two
  sources disagreeing, and drawing it in both places silently would let an
  undeclared unpark look like an ordinary board. A configuration that cannot be
  read says so rather than drawing an empty list, which would read as "nothing is
  parked".


- **`fleetboard` shows which `claude` each session is running.** The header states
  the installed version once; each row carries the version that session is actually
  on, colored when the two differ. A session keeps running the binary it started
  with, so upgrading `claude` changes nothing for a session already up — and there
  is no sign of that from inside the session. `fleetupgrade` plans the restart;
  the board only says who needs one.

  "Installed" is what `claude` would start now, by resolving `~/.local/bin/claude`
  — deliberately not the newest release published upstream, which needs the network
  against a tool whose contract is local sources (~0.2 s). A row matching the header
  means "running what a restart would give it", not "running the newest thing that
  exists", and the documentation says so rather than leaving the word to do it.

  An unknown version prints `?` and is not colored: coloring it would send someone
  to upgrade a session over a source that failed. An unreadable *installed* version
  leaves every comparison unknown rather than marking the whole fleet stale — the
  same error as marking it current, and the board's own rule one level down.


- `docs/checks-that-reassure.md`: **an exit code captured and not branched on.**
  Six `fleetnudge` refusals were each detected correctly, printed as `NOT
  DELIVERED`, and returned as exit 2 — and every caller discarded all three. Two
  independently written watchers kept the return code and branched on nothing;
  one logged `nudge sent (rc=2)`, which reads as success to anyone who reads the
  prose rather than the number beside it.

  The ROADMAP's notification-hook item is corrected with the same evidence. It
  cited three 2026-09-17 nudges as the case for the phone push; those pushes were
  *delivered*, and the same session hit the same class of failure again on
  2026-10-04. The push reaches the human and never the watcher that made the bad
  call, so unmuting it would not have closed this hole.

- **The `--json` shape of `fleetwatch` and `fleetcontext` is written down.** Both
  now have in-tree consumers — `fleetretire` and `fleetboard` read the first,
  `fleetboard` the second — so by this project's own rule their shape is part of
  the versioned surface. That rule could not be applied to a shape nobody had
  recorded.

  `cluster_ok` gets the emphasis it earns: the command prints a banner and **exits
  0** when its cluster query fails, so a caller that does not read that field
  concludes there is no work. Also documented rather than renamed: the
  `_why`/`_states`/`_file` keys on watcher rows, whose underscore keeps this
  tool's findings out of the registration file's own key namespace. `_states` is
  the only route by which a job that ended badly reaches a caller.

  A test binds the pages to the code in the direction that matters — a key the
  docs name and the tool does not emit is a caller sent to read a field that is
  not there. The reverse is deliberately not failed: forcing every incidental
  field into prose would make the page a transcript of the dict rather than a
  description of the contract. The check also asserts it found a real section,
  because a regex that matches nothing passes.

  Documentation of an interface is a second copy of something derivable, kept by
  hand, and rots for the same reason a ledger does. This is the mechanism the
  ledger rule was written without.

- **`fleetboard`** — one screen: every session, its window, busy or idle, context
  size, cluster work, and what is wrong. It renders state the fleet already
  derives; it declares nothing and registers no probe, which is the line that made
  it acceptable after that design was refused on 2026-10-03.

  Written outside this repository and moved in. It reads this app's state layout
  and calls two of its tools, and that coupling had no test across it: when
  `fleetsnap`'s housekeeping renamed its cache on 2026-10-03 the board went blind
  for an hour, and nothing could have caught it, because the dependency crossed a
  repository boundary and only one side had CI.

  **The move's real content was replacing three column parses with `--json`**, and
  one of them was a live defect rather than a latent one. `fleetwatch` prints a
  banner and exits `0` when its cluster query fails, so parsing its display table
  found no job rows and the board recorded an **empty** job list — drawing a blank
  work column for every session. An unreachable cluster rendered as a calm fleet,
  with nobody needing to change a column for it to be wrong. `cluster_ok` is a
  field in `--json`; a banner is not. A second parse was the only way a job that
  *ended badly* reached the screen at all.

  Its first run inside the repository was caught by the exhaustive label test for
  keeping its own copy of the membership rule, which is the argument for the move
  in miniature.

- When `fleetcontext` reports that a pane and a session disagree about being busy,
  it now prints the last line it actually captured. A disagreement is not
  diagnosable without the screen that produced it, and a capture taken by hand
  afterwards is of a pane that has moved on — which is exactly how one report on
  2026-09-30 could not be resolved either way.


- Every tool answers `--version` (and `-V`), reporting the one version written in
  `fleet/__init__.py`: `fleetwatch (fleet 0.2.0)`. There had been no way to ask a
  running fleet which version it was, which stopped being merely untidy once there
  were tags to point at. The flag was never the awkward part — five tools parse
  `sys.argv` by hand, nine use argparse, two are shell, and `fleetwatch` refuses an
  argument it does not recognize — so it is answered in one shared place before any
  tool parses anything, costing each tool a line and changing no exit code. The
  test is exhaustive over `bin/` rather than a sample, so a tool added later cannot
  quietly ship without it.

### Changed

- **`fleetspawn` imports `TRUST_MARKERS` instead of keeping its own copy.** The
  tuple was duplicated verbatim from `fleet/panes.py`. A marker with two homes is
  one that drifts — the two markers already in `panes.py` carry different
  last-checked versions because each was re-checked separately after moving — and
  the roadmap item about markers having no second source is about exactly this
  class.

- **A watcher part way through a set is no longer reported as a fault.** One
  watcher may poll several jobs, which the registry already models correctly as
  several rows sharing a pid. The stale check did not: it asked only "is this job
  in squeue", so the first job of a set to finish produced

      !! WATCHER ON WORK THAT IS NO LONGER LIVE -- the monitor will not exit
         if its completion test cannot close. Check it.

  while the watcher was alive and correctly polling the rest. **Both halves of the
  diagnosis were wrong**: the monitor will exit, and there is nothing to check.
  Reported 2026-10-06 from `sweep-session`, pid 645241 over 26433958/59/60.

  The advice was worse than the alarm. `fleetregister --clear` refuses while the
  pid is alive — correctly — and said *"stop the watcher first"*, which here would
  forfeit the nudge for the two jobs still running. The one remedy named was the
  one thing nobody should do, and it cost a round trip to find that out.

  `registered()` could not have known: it returned `session -> {jobs}` and dropped
  the pid, so "is this the same watcher" was not a question it was able to ask. It
  now also returns `(session, job) -> pid`, and `split_stale` separates the two
  cases. Keyed on the **pid**, not the session: two watchers in one session are two
  watchers, and letting a healthy one vouch for a dead-ended one would hide exactly
  the case the check exists for.

  `fleetregister`'s refusal now counts the other registrations held by that pid and
  says the row clears itself when the watcher exits. Behavior is unchanged — still
  refused, still exit 3; only the advice is different, and only when there is a set
  to forfeit.

  The test for the pid-keying passed against the bug on its first writing, because
  the second watcher it registered used a dead pid — which `registered()` drops
  before `split_stale` ever sees it. It asserted the right thing about a case that
  could not produce the failure.


- **`fleetwatch --json` gains `watchers_partway`, and `stale_watchers` narrows to
  match.** A registration whose job has finished while the same pid still watches
  live work moves out of `stale_watchers` into the new key, and both carry `pid`.
  Callers treating `stale_watchers` as an alarm — `fleetboard` draws a note from
  it — are no longer woken by a campaign finishing one job at a time. A caller that
  wants the old union reads both keys.


- **`fleet/versions.py` is the one derivation of "which claude".** `fleetupgrade`
  and `fleetsnap` each read it for themselves, and the two copies had already
  drifted in shape: a regex for the component after `versions/`, against
  `os.path.basename` of the resolved symlink. Both answer `2.1.292` today, because
  that is the last component of the current layout — **they agree for a reason
  nobody wrote down.** A layout one level deeper (`versions/2.1.292/bin/claude`)
  leaves the regex right and makes `basename` return `"claude"`.

  `fleetsnap`'s was the copy that mattered: its answer is `installed_claude` in the
  manifest a restore is rebuilt from, where it is read as a version number and
  nothing would question it. Adding the board as a third reader is what surfaced
  this; the feature was the occasion, not the reason.

  A test now refuses any tool in `bin/` that parses the version path itself,
  exhaustive over the directory rather than naming the three — a list of names is
  what let the second copy appear. Its first form convicted two innocent lines in
  `fleetupgrade` that ask whether a process is claude at all, and was narrowed to
  the actual signature: a capture group after `versions/`.

- **`fleetrestore` joins a window that is already open instead of opening a second
  one with the same name.** It templated a window per manifest group and asked only
  whether the tmux *session* existed — never whether the *window* did. So a partial
  restore built a new window and renamed it to a name already on screen.

  Found in the 2026-10-05 reboot by the coordinator: 19 of 20 panes came back, and
  the plan for the twentieth was to create a window and name it `site-repo` while a
  four-pane `site-repo` was already open. That pane was placed by hand.

  **The partial restore is the common case, not the edge one.** Liveness filtering
  turns every "one session died" into a partial restore, and the window that session
  lived in is still there holding its neighbors — so the path most likely to be
  used was the one that had never been built for. The whole-fleet path onto a bare
  server, which is the case the tool was written for and tested on, is the rarer
  one and was always correct.

  A group whose name matches **two** open windows is refused and both are named,
  rather than picking one: from the manifest both look equally right, and a wrong
  pick puts a session beside the wrong neighbors. That ambiguous state is what this
  bug produced, so the fix has to cope with its own wreckage.

  Windows named `claude` are never matched. `automatic-rename` writes that name over
  any window whose real name was lost, so it identifies nothing — and with the
  exclusion removed, every group in the test fleet collapsed into one window.

  A joined window is left otherwise untouched: not renamed, and not re-tiled. Its
  layout belongs to the sessions already living in it, and this restore is not
  responsible for them.

- **`fleetrestore --all` now names its replacement instead of letting argparse
  refuse it.** The flag was the documented power-cycle path until it was retired
  — it stood in for "everything is being rebuilt", which the bare command derives
  from the manifest instead. argparse answered it with `unrecognized arguments:
  --all` and a usage line: correct, and no help at all to a reader whose machine
  has just come back and who is typing the command they remember.

  Not hypothetical. On 2026-10-05, preparing a reboot, the coordinator sent
  nineteen sessions `fleetrestore --all --go` as the recovery path, carried
  forward from a drop written before the flag was removed. **A conclusion that was
  true when written, cited later without re-derivation — in the one line that had
  to work.** The documentation was never wrong; the removal is recorded here and
  the operative pages describe the bare form. The error message was the only place
  the correction could still arrive, and it was the one place that said nothing.

  Keyed on the flag and not the word, so a session *labeled* `all` is still an
  ordinary positional. `--brief` is a separate flag, which the new message says
  out loud: `--go` alone writes no briefs, and the reboot it was typed for was
  about to find that out too.

  The test for the word-versus-flag distinction was rewritten mid-change to report
  a line number rather than dump the whole file, and the rewrite silently stopped
  biting — it excluded any line containing the legitimate `"--all" in sys.argv`,
  and the natural broken form puts both tests on one line. Caught only by
  re-breaking the guard *after* editing the assertion. **An edit to a check is not
  covered by the proof taken before it.**

- **`fleetsnap` no longer sweeps the state directory.** The cleanup that cleared
  the per-fleet manifest residue globbed `<state>/*.json` and moved aside every
  file not named after a live fleet. Its docstring said "per-fleet manifests"; the
  glob said the whole namespace, and a file written by another tool is
  indistinguishable from a dead fleet's manifest. On 2026-10-03 it renamed another
  tool's cache. That tool rendered the missing values as *unknown*, which was
  correct and therefore raised nothing — **a value that used to be there is a
  different event from one that never arrived, and only the second is what
  "unknown" is designed to say.**

  Removed rather than narrowed. Nothing has written `<fleet>.json` since
  2026-10-01, so no residue can accumulate, and a migration that cannot have work
  left is only a blast radius. Narrowing it to files that parse as manifests would
  have kept a permanent sweep of a shared directory to catch a case that can no
  longer arise.

  Removed with it: `manifest_is_held`, which kept a parked fleet's manifest
  "because that manifest is how they come back". That stopped being true in the
  same release that retired `fleetrestore <fleet>` — the tool reads only
  `manifest.json` now, so the file it was protecting could no longer be read by
  anything. The real path for a parked session is its `fleet.toml` uuid and the
  resume recipe in its ledger, both of which exist. A guard outliving the thing it
  guarded, still stating the old reason.

  A tool needing its own files in the state directory should own a subdirectory,
  as the watcher registry does with `watchers/`. A test now refuses any sweep of
  the root — `glob`, `listdir`, f-string, concatenation or `os.path.join` — while
  allowing a subdirectory. Its first version looked only for a `*` and so missed
  `os.listdir(STATE)`: same blast radius, different spelling, reported clean. The
  forms it must catch and must not catch are now themselves a test.

- **A ledger may assert immutable facts, and not mutable ones.** Five hand-written
  re-arm ledgers were wrong at the moment they mattered on one day in 2026-10 —
  the moment a restarted session read one and acted on it. The `fleet-upgrade`
  skill now carries the rule and the distinction the five turn on: three were
  *facts or inventories* gone stale and are derivable later; two were
  *instructions* that were correct when written, and no probe or check reaches
  those. One of them would have spent hundreds of dollars of cluster time.

  The second distinction, from a ledger that had already diagnosed itself: **stale
  evidence and a stale conclusion are different failures.** Evidence is cured by
  re-deriving it, so the command that re-derives it goes beside the claim. A stale
  conclusion cannot be re-derived — the reader does not know what question it
  answered — so only an expiry cures it, or not writing it down.

  `fleetretire`'s generated ledger already complied with the first two parts
  without trying: a tool cannot help recording what it observed at the moment it
  observed it, so its runtime claim comes out stamped and past-tense. It now also
  does the third — marks that claim as evidence rather than a current fact, says
  the pid is expected to be dead on reading, and gives the reader `fleetwatch
  <name>`, which answers the same question from the registry instead of from the
  file. Hand-written ledgers fail precisely because they are written in the
  present tense.

  Said in the skill rather than left implied: this is prose, and prose erodes.
  This repository has the measurement — a convention with a local cost held at 0%
  violation for five days after it was read, then decayed past 90% as the reading
  receded, with no change to the rule. Nothing in the rule acts at the moment a
  ledger is written. What would act is named there, along with the part no
  mechanical check reaches, which is the expensive part.

- **`@repo` is unset on every pane.** The rename is finished: one option,
  `@agent`, set by `fleetspawn` and `fleetrestore` and read by everything.

  Two things outside this repository read the old option and had to move first,
  neither reachable from here. `~/.tmux.conf`'s `pane-border-format` fell back to
  `pane_title` without it, which is the Claude *topic* title and drifts — fourteen
  stable pane labels would have become fourteen changing ones. And
  `~/.config/fleet/bin/fleet-gather` used it as its membership test and dies `no
  agent panes found` when nothing carries it, so gather and scatter would both
  have stopped working. Checked by searching outside the repository rather than by
  reasoning about what might use it, which is the only way either would have been
  found.

  Verified after the unset, not before: every tool run against a fleet where the
  option does not exist, and each pane border rendered by asking tmux to evaluate
  the format in that pane's own context rather than reading the config and
  assuming.

- **The `@repo` fallback is gone. `@agent` is the only pane label read.** Every
  format string lost a field and every consumer moved with it — nine tools, each
  a format-and-unpack pair, which is the shape that produced three separate bugs
  during this rename. `agent_label` and `is_agent_pane` take one argument, and a
  caller still passing two now raises rather than being quietly ignored.

  One real hazard inside it: `fleetsnap`'s membership check took both the raw pane
  option and the resolved name, which hid which one it was really asking about.
  With one argument that choice becomes visible, and the raw option is the wrong
  one — a pane named only by `claude agents` carries no option, and checking it
  would drop exactly the sessions the check ordering exists to keep.

  The whole rename needed four steps because the label lives in tmux runtime
  state, not in this repository: code and panes cannot change at the same instant.
  Measured, not assumed — with the fallback removed before the panes were
  re-stamped, 0 of 14 sessions were recognized; with it, 14 of 14.

- **A pane's agent is `@agent`, and `@fleet` is retired.** Membership used to be a
  pair of tmux pane options: `@repo`, the session's name, and `@fleet`, a group.

  `@repo` named a session after a repository, which is wrong for every session that
  owns none — a coordinator, a writing session, a sweep. It is now `@agent`. Every
  tool reads `@agent` first and falls back to `@repo`, so panes carrying only the
  old option keep working; the fallback goes in a later release, once nothing
  carries it. Four tools read `@repo` *without* that fallback until now —
  `fleetrestore`, `fleetwaiting`, `fleetlog` and `fleetspawn`'s duplicate-name
  check — so a pane labeled the new way alone was invisible to them.

  `@fleet` named a subdivision that did not exist. There is one fleet. The groups
  appeared to name tmux windows and agreed with them only by accident: measured on
  the live fleet, seven of fourteen panes disagreed, six because one group had
  outgrown any single window. A group that cannot fit the thing it is named after
  was describing the screen, not the fleet. Gone with it: `fleetspawn --fleet`
  (now neither required nor accepted), the per-`<fleet>` manifests, and
  `fleetrestore <fleet>`.

- `fleetrestore` takes session names, not a fleet. Bare, it plans the whole fleet
  with each window's exact layout — what `--all` did, and what the bare command
  should always have done, since it previously *listed* the per-fleet manifests and
  planned nothing. `fleetrestore NAME...` rebuilds only those. A name the manifest
  does not hold is refused rather than skipped, because restoring the rest after a
  typo reads as a successful partial restore.

- `fleetrestore` decides on the exact layout from what it is rebuilding rather than
  from a flag. `--all` stood in for "everything is being rebuilt" and was not the
  same thing: `--all` with three sessions already live still applied a layout that
  no longer fit.

- One manifest: `manifest.json`. `fleetsnap` no longer writes `<fleet>.json`, no
  longer records a per-session `fleet`, and moves any leftover aside as
  `<name>.json.stale` — except a manifest whose sessions are parked, which is how
  they come back. `index.md` lists sessions rather than fleets.

- `fleetgantt` draws every live session in one lane group. A stopped role still
  keeps whatever `group` `fleet.toml` declares for it, which is declared rather
  than inferred; `fleetretire` no longer invents one from the pane's `@fleet`.

- `fleetretire`'s resume recipe no longer embeds `--fleet`. **Ledgers written
  before this carry a `fleetspawn ... --fleet <group>` line that no longer runs.**
  They live in the state directory, which nothing in this repository reaches, so
  that is a fix by hand.

- The test that every tool reads both labels is exhaustive over `bin/` instead of
  naming five tools. The hand-written list covered the five that decide
  *membership* and reached none of the four that read `@repo` to *identify* a
  session, which is why those four went the whole rename reading the old label
  alone. A list of names cannot catch the tool nobody added to the list. Two
  entries added to `docs/checks-that-reassure.md` from writing it: the first
  version of this guard reported clean with all four tools reverted, and a mocked
  tmux call left the tool's own format string untested.

- `fleetsnap` no longer carries a branch for a session it cannot name. It went
  dead when the membership check moved after `resolve_label` — a pane nothing can
  name is now reported as somebody else's window instead of recorded as a nameless
  row — and it outlived its reachability still telling the reader to set `@repo`,
  the option being retired. Every recorded session has a name by construction, and
  a test now says so.

### Fixed

- **`fleetrestore`'s adoption lines named a release the fleet never ran.** `to=`
  was `installed()` while the launch used `target()`, and those differ every day
  by design — so on 2026-10-19 both restore lines said `to=2.1.303` while all 16
  sessions came up on 2.1.302. Plausible, installed, and false, with nothing
  downstream able to detect it. Reported by coord, who had flagged this exact
  consequence when pinning was designed: `to=` stops being a readout and becomes a
  choice. `fleetspawn` handled it by reading the running process; this file did
  not.

  `claude_cmd()` now returns the version it resolved, so both lines log what was
  launched rather than deriving it again — the pinned release when pinned, and
  what bare `claude` gives when falling back, which really is `installed` in that
  branch. The outcome line says which release it launched on, beside its existing
  note that it did not verify versions.

- **Pinning launches made every session invisible to four tools, for two days.**
  `fleet.procs.claude_procs` identified a session by `basename(argv[0]) ==
  "claude"`. That held while every launch went through the installer's symlink and
  stopped holding when this fleet began pinning launches to a release by path
  (2026-10-17): `argv[0]` became `.../claude/versions/2.1.302`, whose basename is
  `2.1.302`.

  **Every failure was an empty result that reads as "nothing to do."**
  `fleetcontext` listed no sessions, `fleetnudge` and `fleetspawn` could find
  none, and `fleetretire --park` answered *"no claude process named 'site-repo' is
  running"* about a session sitting in a pane. All 16 were invisible. Surfaced by
  coord after a reboot restored the whole fleet on the pinned path; `fleetupgrade`
  and `fleetboard` were unaffected because they read panes and `claude agents`.

  A session is now identified by `/proc/<pid>/exe` — the binary actually
  executing, which a bare `claude` resolves *through* the symlink to and a pinned
  launch names directly — with `argv[0]` still accepted first and without a
  syscall. The two together fail toward **finding** a session: a false positive is
  a strange row somebody notices, a false negative is a fleet that reads as empty.

- **The soak gate could not open, and the log read as though it were waiting.**
  `--eligible` measured the age of the *newest* installed release against a 24-hour
  window, and releases land here about every 25 hours (median gap 25.2 h) — so each
  arrival reset the clock the gate was reading. Two fires, two days, zero sessions
  eligible. Reported by coord 2026-10-17, from the fleet's owner asking where the new binary
  was soaking.

  **The fleet now targets the newest release that has SOAKED, not the newest
  release.** The soak's intent — *do not be the first here to run a fresh binary* —
  is satisfied by some release every day. The gate opens daily, and when releases
  speed up the target falls further behind rather than the mechanism latching shut.

  Three things follow. `fleetspawn` and `fleetrestore` **launch the target by path**
  instead of bare `claude`, since otherwise nothing rolls to it; both fall back to
  bare `claude` when no release has soaked or the named one is gone, and say which
  they did — a session that will not start because a pinned release is missing is
  far worse than one that starts on a fresh binary. **Staleness is measured against
  the target**, because a session rolled exactly right is behind `installed` by
  design and comparing with `installed` would mark the whole fleet stale
  permanently. And `fleetboard`'s header and `fleetupgrade`'s report **print both
  numbers**, because one standing in for the other is what closed the gate.

- **`fleetnudge` sent a `not reached` phone push for a session that was reached.**
  The same lie as the delivery classifier, one channel along: when the tool runs
  inside the session it would type into, the in-session task already notifies it,
  and the `[notify]` push still went out saying nobody had been told. Latent since
  2026-09-14 only because the mute file has existed since then — so the test asserts
  `push` is not *called*, with the mute irrelevant, rather than reading the log
  string, which passes either way.

  **Both channels are decided by one value.** The push and the `notified_otherwise`
  field are the same claim to two audiences, so `give_up` converts `informed` once
  and reads the result twice. Two derivations of one fact agree until they do not,
  and this fact's first channel was the classifier fixed the same day.

  Every other refusal still pushes, which is what the fallback is for; the log
  records why there was no push rather than omitting the field, since `fleetwatch`
  reads an absent push result as "a human was not told".

- **`fleetwatch` reported declined nudges as delivery holes — 2 of the 3 rows then
  driving "a nudge never arrived and no push went out".** The classifier bucketed
  on `outcome` alone. `fleetnudge` declines when it is running *inside* the session
  it would type into, because the in-session task doing the running already
  notifies it: the content reaches its reader by another route and nothing is
  missing. Reported by coord 2026-10-15, who read the classifier rather than the
  symptom.

  **The exit code cannot carry the distinction, and is not used for it.** The
  decline is code 2, shared with caller errors that genuinely lose the news — a
  line over the 200-character limit (2026-09-30), a malformed job id (2026-10-04).
  Bucketing on the code would trade this defect for its mirror image, and the
  mirror image is the dangerous one: a real hole rendered as fine.

  So `fleetnudge` now records `notified_otherwise` on every undelivered record,
  **true and false alike** — an absent key cannot distinguish "predates the field"
  from "lost the news" — and `fleetwatch` reads the field. An absent field and an
  unrecognized reason are both read as a hole. Excluded from the older-than-window
  count as well as the hole lists, since that count is what a reader uses to decide
  whether a quiet window is quiet.

  One prose match remains and is labeled as one: records written before 2026-10-15
  carry only the sentence. It is pinned by a test that parses `fleetnudge` for the
  string it actually emits, so a reworded refusal fails loudly instead of silently
  turning benign rows back into holes. `NUDGE_DAYS` is 7, so it is dead on
  2026-10-22.

- **A failed `fleetmail` nudge was permanent, and nothing could clear it.** `fetch`
  keys on the message path, which is right for writing the file and wrong for telling
  the session: a message whose nudge failed was recorded as handled, so every later
  fetch skipped it. Delivery was attempted **once**. A message fetched 2026-10-05 read
  `needs a human` for ten days; the nudge had failed because the target pane's input
  line held text, and the pane was typeable for almost all of those ten days. Reported
  by coord 2026-10-15.

  Every `fetch` now re-nudges anything whose file was written and whose session was
  never told, **before** the `no new mail` check — where the old behavior hid, since
  the one pass that could revisit a delivery sat behind the one condition guaranteed
  to be true for it. No flag: a flag would reproduce the defect exactly, being
  something that only works when somebody thinks to look again.

  **The budget is the point.** `--nudge-wait` is tuned for *the session is busy*, which
  clears in minutes. What fired was *the input line holds text*, which lasts days and
  which nobody is coming to clear. A longer wait blocks the fetch and still gives up at
  the end; the new `--retry-wait` (45 s) asks only whether the pane is typeable now, and
  the patience lives in the repetition.

  **The documentation already promised this.** "The next tick will try again" was on the
  fleetmail page before it was true, which is a large part of why the gap went ten days
  unnoticed — a documented promise the code does not keep stops anyone from looking.

- **`fleetmail ack` mailed the sender and changed nothing locally**, so a message the
  recipient had demonstrably read still showed `needs a human`, with no tool able to
  clear it and hand-editing the state file forbidden by that directory's own rules. It
  now marks the record `acked`, but only when the send succeeds — amending first would
  let a failed ack mark a message answered while nothing left the machine. The state
  distinguishes how it was resolved (`delivered (by ack; the nudge never landed)`)
  rather than collapsing it into a bare `delivered`.

  The first version of this fix did nothing at all: `do_send` ends in `sys.exit`, so the
  amend written after the call was unreachable — the same shape as the bug, where `ack`
  looked like it resolved the record and did not. Its own test caught it.

- **Nothing could read a version on an npm install, and the staleness check could
  not fail.** `npm install -g @anthropic-ai/claude-code` keeps one binary under
  `node_modules/@anthropic-ai/claude-code/bin/` and upgrades it **in place**; the
  native installer keeps versions side by side under `.../versions/<v>/`. Everything
  here read the path alone, so on an npm machine `fleetsnap` recorded the installed
  claude as `claude`, every session's version as `claude.exe`, and `fleetupgrade`
  compared `None` against `None` for every session — a check that could not fail,
  on the tool whose whole job is to find sessions running an old binary.

  `fleet.versions` now reads both layouts: the path, else the `package.json` of the
  package the binary sits in, checked **by name** so a stray manifest further up the
  tree cannot pass its version off as Claude Code's. A binary that answers neither
  way is asked directly, cached against its own size and mtime — one `stat` per
  `fleetboard --watch` redraw instead of one process launch, and an in-place upgrade
  still invalidates it, because it changes both.

  **`installed()` searches** rather than resolving one hardcoded path: `shutil.which`
  first, then the native default. There is no `~/.local/bin/claude` at all on an npm
  install, and `fleetupgrade` passed that path explicitly. The first candidate that
  **exists** decides, known or unknown — falling through would report the version of
  a binary no new session would launch, which is a confident number in place of an
  absent one.

  **A binary replaced under a running session reads `?`.** `/proc/<pid>/exe` ends in
  ` (deleted)` and the package beside it now describes the *new* binary, so reading
  it would mark a straggler as already upgraded — the one error an upgrade roll must
  not make. The native layout is unaffected and still names its version when deleted.

  Found and fixed first in `pkgyasi/fleet`, a fork that hit it on its own machine;
  this is the same defect ported onto `fleet.versions`, which did not exist when
  they wrote it.

- **`fleetcost`'s two example costs were understated ~1.9x: they read the character
  count as the whole record, and the record is not the message.** Every arrival
  carries a near-constant envelope the receiver re-reads exactly like the body — a
  line of prose, the `<cross-session-message ...>` tag naming the sender's socket,
  name and mode, the close tag, and a paragraph of handling advice after it. Measured
  over 2,419 arrivals: **722 mean, 723 median**, of which 543 is the trailing advice
  alone. Reported 2026-10-13 by a session recounting the figure for a talk.

  `scan()` always counted it, because it measures the whole record. The two printed
  examples did not, and they are the lines anyone quotes, because they are stated in
  terms of the 800-character convention from `comms.md` — which governs the **body**.
  A message written to that rule was quoted at `~55,600 tok` where it costs
  `~106,000`; a 4,000-character body costs `~328,000`, not `~278,000`. The examples
  now name the body and print the measured envelope beside it.

  **`AMPLIFICATION` does not move and is unchanged.** The envelope is in both of its
  sums and divides out — the same reason the ratio survived the duplicate-transcript
  bug that moved every count. Figures quoted for amplification stand; figures quoted
  from the two example lines before this are low.

- **`fleetboard --watch` held the configuration it started with, so an unparked
  session never left the parked list.** `CFG` was read at import. A watcher left up
  for 21h50m was still listing `site-repo` under `parked (10)` hours after it was
  unparked — correctly drawn in the live table at the same time, because names come
  from tmux and `claude agents` on every draw and only the declaration was frozen.
  Reported 2026-10-09.

  **It flagged the session `ALSO RUNNING`** — the marker added the day before for a
  session running while declared parked. The disagreement was real and both sides
  of it were this board's: a live reading of tmux against a 22-hour-old reading of
  a file. A check that reports its own staleness as the fleet's is worse than no
  check, because it looks like evidence about something else.

  The configuration is now re-read on every draw. The two slow sources stay cached
  and stamped with their age, which is deliberate; a small TOML file is neither slow
  nor observed, and reading it costs nothing beside the `claude agents` call each
  draw already makes. A file caught half-saved reads as unreadable and says so,
  rather than exiting on a parse error and taking a watched screen down with it.

- **`fleetcost` counted three sessions twice, and every figure it prints was
  inflated.** A working directory rename leaves one session's transcript in two
  project directories — `~/notes/oldname` became `~/notes/newname` on 2026-10-02 —
  and `scan()` globbed and summed per file. Reported 2026-10-08 by a session
  recounting a published figure.

  Measured on this fleet, before and after:

  | | before | after |
  | :--- | ---: | ---: |
  | transcripts | 101 | 98 |
  | assistant turns | 94,028 | 89,398 |
  | tokens read | 33.66 G | 31.66 G |
  | peer messages | 2,528 | 2,353 |
  | amplification | 367x | **365x** |

  **The counts move ~7%; the ratio moves 2x.** Amplification is a quotient whose
  numerator and denominator inflate together, so it is the robust figure here and
  the message counts are not — the opposite of what "a ratio of two affected sums"
  suggests, and worth stating because the ratio is the quoted number.

  Figures measured before 2026-10-02 are unaffected: the duplicates did not exist.
  A deck quoting 355x from 30 September is sound, and the drift from 355x to 365x
  is real growth rather than this artifact.

- **`fleetlog sessions` listed a duplicated transcript once per project
  directory** — 81 rows where there are 79, two of them `notes-session`'s. Its *edges*
  were already right, because two identical copies yield identical edges and
  `dedupe(edges)` collapses them; measured invariant at 3,007 either way. **Safe by
  a route that would not survive the two copies differing is not the same as
  safe**, so the scan now dedupes rather than relying on it.

- `fleet.transcripts.dedupe_paths` is the one place that collapses them. A file is
  named `<session uuid>.jsonl` and a uuid is unique to a session, so the basename
  is the identity. The larger copy wins — a session that continued under the new
  path left the old one short — and an equal-size tie falls back to the path, so
  the answer cannot depend on the order the glob happened to walk. An unreadable
  path is kept and loses its tie: it may be the only copy, and dropping it would
  undercount, which is the direction nobody checks.

  **How it was caught is the reusable part, and it was not inspection.** A recount
  disagreed with a figure already published for a week that had already finished.
  A completed week whose count moves between two runs is the symptom; the earlier
  number is the control; and deduping returning it to the published value exactly
  is what confirmed the diagnosis.


- **`fleetgantt --all` drew three sessions twice.** A transcript uuid is a
  session — `fleet/identity.py` says so in those words — so two rows for one uuid
  draw one session living two lives side by side. `--all` produced 100 segments
  from 97 uuids; the default view produced 89 from 89 and hid it, because a project
  directory no role owns is dropped before anything is drawn.

  The cause is a **renamed working directory**: Claude Code opens a project
  directory for the new path and the old one keeps its copy of the transcript, so
  both are scanned. `~/notes/oldname` became `~/notes/newname`, and three
  transcripts existed under both slugs — byte-identical, identical mtimes,
  different inodes.

  Rows are now collapsed by uuid, keeping the copy under a directory a role owns,
  which is the live one and the one that attributes correctly. The remaining
  tie-breaks are for determinism rather than judgement, because a chart that
  redraws differently on each run is its own bug. Found while answering a report
  about something else, and narrowed to `--all` by its reporter.

- **`fleetgantt`'s unplaced lane no longer claims its occupants never held a
  role.** The heading read `NOT A ROLE`. Reported 2026-10-07: four transcripts
  named `oldname` and two named `notebook` sit there, and those are the earlier
  names of `notes-session` and `web-repo`. **Every placement decision under
  that heading was right; the heading was the only thing making a claim, and the
  claim was false.**

  The lane holds transcripts the chart *declined to place*, which is not the same
  as transcripts that held no role. A session's earlier name lands there whenever
  no single transcript records the change — rule 2 requires *this* transcript to
  have recorded both names, because a lane states an identity and cross-transcript
  evidence cannot tell a real rename from two sessions that shared a name
  (2026-09-22). `fleetlog` keeps such a mapping, labeled *from another
  transcript*, because a message graph has no lane to mislabel.

  The reported cause — `rename_map` called with an empty `dir_owner` where
  `fleetlog` passes the real one — is a real asymmetry, and **measured against the
  live fleet it moves nothing**: zero segments change lane, and all six keep the
  identical `how`. A corroborated rename is already learned from lineage, and an
  uncorroborated one is refused downstream, so the argument only fills a table
  nothing then acts on. The operative gate is `place_named=False`, two steps
  further on.

  Two attempts to label these honestly were built and abandoned, each killed by a
  test. Taking the candidate from the rename table maps *every* non-current name
  in a role's directory to that role, so a genuine one-off is labeled that role's
  earlier name — the 2026-09-22 guess wearing a label instead of a lane. Taking it
  from the directory is no better: a transcript's project directory is where its
  *file* sits, not where it ran, and one of the six records
  `~/Git/oldname-mirror` while its transcript lives under
  `-home-u-repos-proj`. Neither is sound, so the chart says nothing about
  these beyond declining to place them — and now says that, instead of the
  opposite.

- **`fleetupgrade`'s stuck-session detector told a human to kill working
  sessions, and missed the one session that was actually stuck.** Both in a single
  roll on 2026-10-07, in opposite directions, from one cause.

  The structural test — a child in its own process session, which `/exit` cannot
  signal — is correct and is true of **every** Claude Code Bash command, so it
  discriminates nothing. The entire discriminator was `immortal()`: does the
  command contain a `sleep`. That is a syntactic proxy for a temporal property,
  and the two are unrelated.

  - **False positive.** The fleet's documented way of waiting for a detached job
    is `until ! kill -0 $J; do sleep 30; done`. The one thing a sleep test matches
    is therefore the house style for waiting correctly. Two sessions mid-task were
    printed with `kill` lines under *"Not a busy session: a stuck one."* Both were
    `busy`, their shells minutes old, their leaf a live `sleep`. One went idle
    shortly after and its flagged child simply vanished — a stuck loop does not do
    that. The same false positive was reproducible here while writing the fix.
  - **False negative.** A 22-hour-old `eza` — an aliased `ls` that never returned —
    held `sim-study`'s `/exit` open and was never flagged, because it has no
    sleep in it. Another session hit the identical hang the day before. A poll loop
    is one way to block an exit, not the definition.

  `blocks_exit()` now names the structural fact and `immortal()` is demoted to
  what it can honestly report: the shape of the command. Every exit-blocking child
  is listed with its **age**, the session's `claude agents` **status**, and whether
  it polls — the three things that separate a three-minute waiter from a
  twenty-two-hour hang, none of which the signature carries.

  The headline no longer asserts a conclusion the tool cannot reach. It says
  `/exit WILL NOT COMPLETE while these run`, which is true, instead of
  *"Not a busy session: a stuck one"*, which was not — and it no longer leads with
  a `kill` command.

  Blockers are now filtered to sessions the roll will actually `/exit` and sorted
  oldest first. A session already on the installed version was being warned about
  although nothing was going to touch it.

  The displayed command is the one a human can read. Every Claude Code Bash
  command arrives wrapped in a shell-snapshot preamble, so truncating the raw
  cmdline printed boilerplate and cut off before the command — under text saying
  "read each command before killing anything". Advice the output makes impossible
  to follow is how a warning becomes something people click past.

- **`fleetspawn --go` reported `TIMED OUT` on sessions that had started
  correctly.** Readiness was gated on the version banner being on the pane. The
  banner is drawn **once**, and the session's own first output scrolls it away — so
  the signal is destroyed by the very event it reports, and a session that comes up
  and gets to work *faster* is more likely to be reported as never having come up.

  A fresh spawn usually wins that race, sitting idle while its first prompt is
  read. A `--resume` always loses it: replaying the conversation fills the pane
  before the first poll. Reported 2026-10-07 — five unparks in one day plus two the
  day before, every one reported timed out, every one actually up, correct and
  labeled. **Raising `--wait` could not help; 180 s failed where 60 s had
  succeeded**, which is the tell that duration was never the variable.

  The reported cause was `[spawn].first_prompt` firing on a resume. It is not:
  `launch_cmd` returns early for `--resume` and sends no prompt. The symptom
  pointed the right way and the mechanism did not.

  A session listed by `claude agents` now also counts as up — the structured
  source, which keeps saying so, and the one `fleet.panes.reconcile` already
  prefers over a parse of a moving TUI. The banner is kept: it still means what it
  meant, and it is the fallback when `claude agents` cannot be read, so the fix
  does not trade one unreachable readiness state for another. The folder-trust and
  resume-mode prompts are still checked first, because they are what the structured
  source cannot see.

  A timeout that happens anyway now says whether `claude agents` lists the name,
  so a false timeout is legible as one. **This mattered more than the alarm**: the
  natural responses to it — relaunch, or retire and retry — are the damaging ones.

  The test for the directory check passed against a deliberately broken version,
  because it drove the case through an empty process list that rejected it anyway.
  Narrowing it found that the directory was being checked twice; the `claude
  agents` copy was removed, since an extra condition can only withhold readiness,
  which is the failure being fixed.


- `docs/source/tools/fleetrestore.rst` described pane addressing as using tmux's
  `pane-base-index`. That mechanism was removed because reading it *was* the
  2026-09-30 failure — queried before the first `new-session`, it returned nothing
  on a machine with no server and fell back to `0` while the config sets `1`, and
  every session came up one pane to the left. The tool has addressed panes by `%N`
  id since, and the tests assert the reader is gone; only the documentation still
  recommended the thing that broke. Found while correcting the `--all` message on
  the same page.

- `fleetlog` no longer states a rename it cannot know about. `fleetlog sessions` is
  a table headed *identity*, and five of its rows claimed one — including the same
  transcript that was wrong in `fleetgantt` before `v0.1.0`: a session started by
  hand in a role's directory, which had only ever recorded the auto-generated
  display name it happened to be given. The rename table is keyed by bare name
  across every transcript, and `name_map`'s own docstring says why that is
  dangerous — *"a name is not an identity, a TRANSCRIPT is"* — while this caller
  applied it across transcripts anyway.

  **The answer is kept; the claim is not.** Cross-transcript lineage is right as
  often as it is wrong — a session resumed elsewhere and renamed there has its old
  transcript here — and the two cases are indistinguishable from the data. So a
  mapping this transcript does not corroborate now reads
  `'X' -> 'Y', from another transcript` instead of `renamed: 'X' became 'Y'`, and
  a caller that treats the answer as an identity rather than an edge — a lane on a
  chart — still keeps it apart, which is the `v0.1.0` behavior and is now tested
  so that it survives.

  A mapping that came from the directory branch was also being called a rename.
  Nothing there was ever renamed, and it no longer says so.

## [0.2.0] - 2026-09-30


### Added

- An end-to-end test that builds a fleet on a throwaway tmux server with
  `pane-base-index 1` and checks where every session landed. This is what was missing
  when a restore put every session one pane to the left: everything about the tool
  was tested except whether it worked. It is safe to run because of the three things
  that did not exist before — `--socket`, a fake `claude` earlier on `PATH`, and a
  temporary `HOME` so tmux reads a test config rather than the owner's. Reintroducing
  the original defect fails it.

### Fixed

- `fleetregister --clear` no longer abandons the whole clear on meeting a live
  registration. It exited from inside the loop, so every dead file sorting after
  the live one survived — and the glob is lexical on the pid string, so whether a
  clear worked depended on which pid happened to sort first. It bit exactly the
  re-armed case, a dead old pid beside a live new one, which is what every restart
  produces. Dead entries are now cleared and live ones skipped with the warning
  kept. A run that skipped something exits 3 and says what it cleared and what it
  did not: 1 still means no registration matched, and the two used to be
  indistinguishable, so a caller could not tell nothing-to-do from nothing-cleared.

- `fleetrestore` builds on a tmux server it chooses, not the caller's. `$TMUX` is
  set inside any pane, so a restore run from one would have built the fleet on that
  pane's server; the variable is now cleared for every tmux call and `--socket NAME`
  names a server explicitly. All nineteen invocations go through one place, so the
  choice is made once.

- `fleetsnap` no longer snapshots panes that are not the fleet's. It read `@repo`
  only as a source for a session's NAME and fell back to the tmux session name for
  the fleet, so a personal tmux session was captured **as a fleet** and given its own
  manifest offering to restore it. Membership is now the same `@repo`/`@fleet` label
  the other tools use, and excluded panes are reported — a fleet pane that lost its
  labels is missing from the snapshot, which means missing from recovery.

- `fleetsnap` retires per-fleet manifests for fleets that no longer exist. It wrote
  one per snapshot and never removed any, so `fleetrestore` offered to rebuild fleets
  that had not existed for weeks. They are moved to `<name>.json.stale` rather than
  deleted, which is the rule `install` already follows. A manifest is kept when its
  sessions are parked or retired — that manifest is how they come back — or when it
  cannot be read, and the reason is stated rather than assumed.


- `fleetrestore` no longer computes which pane to type into. Targets were built as
  `<window>.<index + pane-base-index>`, and the base index was read from tmux
  **before the first `new-session`** — so with no server running the query returned
  nothing and the code fell back to 0, while the config sets 1. After a power cycle
  every session went one pane to the left: five never started and seven launched in
  another session's working directory. The function that read the setting had been
  added to fix that exact class of failure after an earlier restore, and could not
  hold in the one case the tool exists for. Pane ids are now captured from
  `new-session` and `split-window` as each pane is made, so there is no index to be
  off by and renumbering cannot matter either.

- `fleetrestore` checks before it types and after it builds. A tmux failure never
  stopped the run, so seven `claude --resume` lines went into the wrong panes: it
  now compares each pane's directory to the manifest first and skips a mismatch
  rather than launching into it, refuses to type into a pane it cannot name, and
  ends by comparing every pane's `@repo` label and directory against the manifest
  instead of telling the operator to go and check.

- `fleetrestore --brief` no longer writes its recovery brief into a session's
  working directory. For a repo session that is the repo root, so the brief landed
  untracked and un-ignored in a work tree — a public one in at least one case, and
  the tree feeding a manuscript in another — where `git add -A` would have swept
  fleet tooling output into a commit. Raised independently by four sessions within
  minutes of a power cycle, which is the argument for fixing it rather than
  circulating a convention about it. Briefs now go to `<state>/recovery/<session>.md`,
  beside the ledgers and watcher registrations, and the restore prints the path.

- `fleetcost` reported about half the tokens actually read, and called the figure an
  over-count. One stale constant did both: a 200k-token window applied as a sliding
  byte cap, from when that was the whole context. It truncated the bill — 88% of
  turns exceeded it — and it cut message survival off at the same boundary, which
  put **amplification at roughly a third** of what the compaction records in the same
  transcripts show. The bill now comes from `message.usage`, which every assistant
  turn carries, so it is read rather than estimated and needs no characters-per-token
  assumption; survival now ends at a compaction boundary, which is what actually
  evicts a message. On this fleet the amplification figure moves from ~110x to ~356x.
  Reported by a session that had the old number on a public slide.

- `fleetcost` has tests. It had none, which is how a number wrong by half, labeled
  wrong in the other direction, survived in the figure the messaging convention rests
  on.

- The pane and the session no longer disagree in silence about whether a session
  is busy. Whether a pane is idle was decided by parsing a captured terminal —
  a TUI whose markers move — and `claude agents` answers the same question
  structurally. The two are now reconciled in one place: the structured status
  decides busy-vs-idle, the screen decides what only it can see (a trust prompt, a
  dialog, a draft), and a **disagreement is reported rather than resolved quietly**
  — a pane reading idle while the session reports busy is what a moved busy marker
  looks like. Both directions still resolve to busy, so no tool becomes more
  willing to type; what changes is that the moved marker stops being invisible.
  `fleetnudge` names it on the refusal, `fleetcontext` in its report.

- `fleetnudge` and `fleetcontext` had each rolled their own version of that
  override and disagreed: one counted a `waiting` session as busy and the other did
  not. They now share the safer definition.

## [0.1.1] - 2026-09-26


### Added

- `fleetwatch` refuses an argument it does not recognize instead of answering it.
  An invented subcommand was taken as a session filter, matched nothing, and
  printed "no live cluster work" with exit 0 while a live array was running — on
  the `--json` path too, where `fleetretire` reads it to decide whether a session
  owns cluster work. Unknown options and a second session name are refused as
  well, and an empty filtered report now names the session rather than the
  cluster account.

- `fleetwatch` reports who is attached to the tmux server: every client, where it
  came from, and how long it has been idle, with an alarm on the second one.
  Attaching hands a person every pane in the fleet — sessions already past the
  folder-trust prompt, with peers that treat a line from one of them as a
  teammate's request. It reports rather than guards, and the documentation says
  why: whoever can attach can read the same credentials without tmux, so the
  boundary is the account, not the fleet.

- `concepts` documents the two channels a line reaches a session by, side by
  side: a peer message, whose origin carries the sender's verified process
  identity, and a line typed into a pane, which is recorded as human and is
  indistinguishable from the owner's own typing. The `[watcher:]` and `[mail:]`
  tags are convention, not mechanism — a label on the envelope, never a
  signature — and files carried by either channel are secured by neither.

- A loopback test for `fleetmail`: two fleets, two state directories, one real
  bare repository, and `git` actually running. Every other test in that file
  stubs `pull` and `push`, so the transport had no coverage at all — breaking the
  push fails all four of these and none of the seventeen others.

### Fixed

- The tools no longer treat every `claude` on the machine as part of the fleet.
  `tmux list-panes -a` crosses tmux *sessions*, so it returns the human's own
  windows too. `fleetupgrade` counted one in its stale total and printed a restart
  plan for it with the managed-agent environment prepended — which would not have
  restored what was running but changed what it was. `fleetcontext`, which
  compacts sessions, had the same reach. Membership is now the `@repo`/`@fleet`
  label `fleetspawn` stamps and `fleetsnap` already read, applied in
  `fleetupgrade`, `fleetcontext`, `fleetnudge` (which types into panes) and
  `fleetwatch`. Excluded panes are **reported**, not dropped in silence: a fleet
  pane that lost its labels must not vanish from a roll without a word.

## [0.1.0] - 2026-09-23

First tagged release. The tools had been in daily use by a fleet of thirteen
sessions since 2026-08-27; this is the point at which the repository became
something a stranger could pin.


### Added

- **Recovery.** `fleetsnap` records which pane resumes which transcript while the
  fleet is healthy; `fleetrestore` rebuilds tmux, labels and sessions after a
  power cycle.
- **Upgrades.** `fleetupgrade` finds sessions on a stale binary and who would lose
  runtime state on restart. `fleetcontext` measures what each session carries and
  compacts one at a time, on the human's word.
- **Watched cluster work.** `fleetwatch` derives which scheduler jobs have a live
  watcher from the scheduler and `/proc` rather than from notes; `fleetregister`
  is how a watcher registers `{pid, starttime, job}` at arm time.
- **Sessions.** `fleetspawn` brings one new session in — pane, labels, launch,
  verification — and never answers the folder-trust prompt; `fleetretire` parks or
  retires one, recording how to resume it first.
- **Messages.** `fleetnudge` lets a detached watcher wake its idle session with one
  tagged line, falling back to a phone push. `fleetmail` carries messages between
  fleets owned by different people through a git mailbox.
- **Visibility.** `fleetlog`, `fleetcost`, `fleetwaiting` and `fleetgantt`
  reconstruct who talks to whom, what it costs, who is blocked on the human, and
  every session's life as a Gantt chart.
- **Skills.** `fleet-bootstrap`, `fleet-upgrade`, `fleet-snapshot`, `waiting` and a
  site-independent `slurm` skill.
- **Documentation** at <https://fleet-of-agents.readthedocs.io>, including
  `docs/checks-that-reassure.md` — the catalog of checks whose wrong answer is
  the reassuring one, which is the design rule the rest of this follows.
- **Continuous integration** running the suite on Python 3.11, 3.12 and 3.13, with
  a step that refuses to report a pass on an empty or shrunken suite.

### Fixed

- `fleetwatch` now reports nudges that never reached a session. With the
  `[notify]` push muted, an undelivered line left no trace anyone looked at, while
  the job it concerned read as watched.
- `fleetnudge` delivers mail addressed to a coordinator. The refusal exists for
  watcher nudges, whose results go to the human; relayed mail was caught by it, so
  a message was written to a drop and never handed over — and `<fleet>/coord` is
  the example address in fleetmail's own documentation.
- `fleetnudge` records `mail_from` on a failed delivery as well as a successful
  one, so an undelivered piece of mail is identifiable as mail.
- `fleetgantt` no longer reports a rename it cannot know about. The rename table
  is keyed by bare name across every transcript, and auto-generated display names
  are not unique, so one transcript's history was applied to another and stated as
  a fact.
- `fleetupgrade` flags a session whose polling child is in its own process
  session. "Exit and stop tasks" cannot reach it, so `/exit` never completes: a
  roll that will fail rather than a session that is busy.

