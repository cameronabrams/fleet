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

### Fixed

- **A watcher part way through a set is no longer reported as a fault.** One
  watcher may poll several jobs, which the registry already models correctly as
  several rows sharing a pid. The stale check did not: it asked only "is this job
  in squeue", so the first job of a set to finish produced

      !! WATCHER ON WORK THAT IS NO LONGER LIVE -- the monitor will not exit
         if its completion test cannot close. Check it.

  while the watcher was alive and correctly polling the rest. **Both halves of the
  diagnosis were wrong**: the monitor will exit, and there is nothing to check.
  Reported 2026-10-06 from `pestifer-sweep`, pid 645241 over 26433958/59/60.

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
  says the row clears itself when the watcher exits. Behaviour is unchanged — still
  refused, still exit 3; only the advice is different, and only when there is a set
  to forfeit.

  The test for the pid-keying passed against the bug on its first writing, because
  the second watcher it registered used a dead pid — which `registered()` drops
  before `split_stale` ever sees it. It asserted the right thing about a case that
  could not produce the failure.

### Changed

- **`fleetwatch --json` gains `watchers_partway`, and `stale_watchers` narrows to
  match.** A registration whose job has finished while the same pid still watches
  live work moves out of `stale_watchers` into the new key, and both carry `pid`.
  Callers treating `stale_watchers` as an alarm — `fleetboard` draws a note from
  it — are no longer woken by a campaign finishing one job at a time. A caller that
  wants the old union reads both keys.

### Added

- **`fleetboard` shows which `claude` each session is running.** The header states
  the installed version once; each row carries the version that session is actually
  on, coloured when the two differ. A session keeps running the binary it started
  with, so upgrading `claude` changes nothing for a session already up — and there
  is no sign of that from inside the session. `fleetupgrade` plans the restart;
  the board only says who needs one.

  "Installed" is what `claude` would start now, by resolving `~/.local/bin/claude`
  — deliberately not the newest release published upstream, which needs the network
  against a tool whose contract is local sources (~0.2 s). A row matching the header
  means "running what a restart would give it", not "running the newest thing that
  exists", and the documentation says so rather than leaving the word to do it.

  An unknown version prints `?` and is not coloured: colouring it would send someone
  to upgrade a session over a source that failed. An unreadable *installed* version
  leaves every comparison unknown rather than marking the whole fleet stale — the
  same error as marking it current, and the board's own rule one level down.

### Changed

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
  the plan for the twentieth was to create a window and name it `drexiglas` while a
  four-pane `drexiglas` was already open. That pane was placed by hand.

  **The partial restore is the common case, not the edge one.** Liveness filtering
  turns every "one session died" into a partial restore, and the window that session
  lived in is still there holding its neighbours — so the path most likely to be
  used was the one that had never been built for. The whole-fleet path onto a bare
  server, which is the case the tool was written for and tested on, is the rarer
  one and was always correct.

  A group whose name matches **two** open windows is refused and both are named,
  rather than picking one: from the manifest both look equally right, and a wrong
  pick puts a session beside the wrong neighbours. That ambiguous state is what this
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

  Keyed on the flag and not the word, so a session *labelled* `all` is still an
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
  re-stamped, 0 of 14 sessions were recognised; with it, 14 of 14.

- **A pane's agent is `@agent`, and `@fleet` is retired.** Membership used to be a
  pair of tmux pane options: `@repo`, the session's name, and `@fleet`, a group.

  `@repo` named a session after a repository, which is wrong for every session that
  owns none — a coordinator, a writing session, a sweep. It is now `@agent`. Every
  tool reads `@agent` first and falls back to `@repo`, so panes carrying only the
  old option keep working; the fallback goes in a later release, once nothing
  carries it. Four tools read `@repo` *without* that fallback until now —
  `fleetrestore`, `fleetwaiting`, `fleetlog` and `fleetspawn`'s duplicate-name
  check — so a pane labelled the new way alone was invisible to them.

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

### Added

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
  argument it does not recognise — so it is answered in one shared place before any
  tool parses anything, costing each tool a line and changing no exit code. The
  test is exhaustive over `bin/` rather than a sample, so a tool added later cannot
  quietly ship without it.

### Fixed

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
  chart — still keeps it apart, which is the `v0.1.0` behaviour and is now tested
  so that it survives.

  A mapping that came from the directory branch was also being called a rename.
  Nothing there was ever renamed, and it no longer says so.

## [0.2.0] - 2026-09-30

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

### Added

- An end-to-end test that builds a fleet on a throwaway tmux server with
  `pane-base-index 1` and checks where every session landed. This is what was missing
  when a restore put every session one pane to the left: everything about the tool
  was tested except whether it worked. It is safe to run because of the three things
  that did not exist before — `--socket`, a fake `claude` earlier on `PATH`, and a
  temporary `HOME` so tmux reads a test config rather than the owner's. Reintroducing
  the original defect fails it.

### Fixed

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

- `fleetcost` has tests. It had none, which is how a number wrong by half, labelled
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
  `docs/checks-that-reassure.md` — the catalogue of checks whose wrong answer is
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
