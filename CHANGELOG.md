# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**0.x means the command-line surface may still change between minor versions.**
The tools are run by hand and by agent sessions rather than imported as a
library, so "public API" here means a tool's arguments, its exit codes, and the
shape of its `--json`.

Releases are cut with `scripts/release.sh <version>`.

## [Unreleased]

### Added

- `fleetwatch` refuses an argument it does not recognize instead of answering it.
  An invented subcommand was taken as a session filter, matched nothing, and
  printed "no live cluster work" with exit 0 while a live array was running — on
  the `--json` path too, where `fleetretire` reads it to decide whether a session
  owns cluster work. Unknown options and a second session name are refused as
  well, and an empty filtered report now names the session rather than the
  cluster account.

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
