# fleet

[![Tests](https://github.com/cameronabrams/fleet/actions/workflows/tests.yml/badge.svg)](https://github.com/cameronabrams/fleet/actions/workflows/tests.yml)
[![Documentation Status](https://readthedocs.org/projects/fleet-of-agents/badge/?version=latest)](https://fleet-of-agents.readthedocs.io/en/latest/)
[![License: MIT](https://img.shields.io/github/license/cameronabrams/fleet)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://fleet-of-agents.readthedocs.io/en/latest/installation.html#requirements)
[![No dependencies](https://img.shields.io/badge/dependencies-none-brightgreen)](https://fleet-of-agents.readthedocs.io/en/latest/installation.html#requirements)
[![Platform: Linux](https://img.shields.io/badge/platform-linux-lightgrey)](https://fleet-of-agents.readthedocs.io/en/latest/installation.html#requirements)

Tools and skills for running a fleet of long-lived Claude Code sessions, each
owning a repository or a compute campaign, and coordinating between them.

## Three layers, kept apart on purpose

| layer | where | contents | versioned |
| :--- | :--- | :--- | :--- |
| **application** | this repo | `bin/` tools, `fleet/` loader, `skills/`, `docs/` | here, shareable |
| **configuration** | `~/.config/fleet/` (or `$FLEET_CONFIG`) | `fleet.toml`, site skills | privately, never here |
| **state** | `[paths].state`, default `~/.local/state/fleet/` | manifests, watcher registry, ledgers | never |

Configuration is what a human **declares** — hosts, accounts, which working
directory belongs to which session. State is what the tools **observe** at
runtime. Keeping them apart is not tidiness: a record of observed state kept by
hand is the specific thing that rots. See `docs/checks-that-reassure.md`.

## Install

    cp examples/fleet.example.toml ~/.config/fleet/fleet.toml   # then edit
    ./install          # shows the plan, changes nothing
    ./install --go     # symlinks tools into ~/bin and skills into ~/.claude/skills

Symlinks, not copies, so an edit here is live at once. Nothing real is ever
overwritten silently; displaced files are moved aside, not deleted.

There is no package to install and no build step, so a release here names a
commit rather than an artifact: `git pull` is the update path, and the tag is how
you say which fleet you are running. Versions and what changed in each are in
[CHANGELOG.md](CHANGELOG.md); `git checkout v0.1.0` pins one. `0.x` means a
tool's arguments, exit codes and `--json` shape may still change between minor
versions.

Configuration is read with the stdlib `tomllib` (Python 3.11+) and nothing else,
because these tools are the recovery path after a disk loss — a recovery tool
that needs a package installed before it can read its own config fails exactly
when you need it.

## Tools

| tool | does |
| :--- | :--- |
| `fleetupgrade` | which sessions run a stale binary; ordered restart plan |
| `fleetsnap` / `fleetrestore` | snapshot the fleet; rebuild it after a power cycle |
| `fleetwatch` | DERIVE which cluster work has a live watcher, and which does not |
| `fleetregister` | a watcher registers `{pid, starttime, job}` at arm time |
| `fleetlog` | reconstruct the cross-session message graph |
| `fleetcost` | measure what inter-session messages cost in re-read tokens |
| `fleetwaiting` | which sessions are blocked waiting on a human |
| `fleetgantt` | every session's life as a Gantt chart (standalone HTML) |
| `fleetspawn` | bring one new session in, or a parked one back (plan by default) |
| `fleetretire` | park or retire one session: checks, resume recipe, `/exit` (plan by default) |
| `fleetnudge` | a detached watcher wakes its idle session with one tagged line; phone push if it cannot (plan by default) |
| `fleetmail` | messages between fleets owned by different people, through a git mailbox (plan by default) |
| `fleetcontext` | context size per session and what to trim; `/compact` or `/color` one (plan by default) |

## Skills

- `fleet-bootstrap` — found a fleet from a coordinator, or add / park / retire one
  session: role design, briefs, `fleetspawn`, verification. Templates in
  `examples/brief.example.md` and `examples/conventions.example.md`.
- `fleet-upgrade`, `fleet-snapshot` — rolling a binary upgrade without losing
  monitors; snapshotting for recovery.
- `waiting` — who is blocked on the human and what each is asking, reconciled
  from `ListAgents`, `fleetwaiting` and the sessions themselves.
- `slurm` — SLURM mechanics and the traps that give confident wrong answers.
  Site-independent; pair with a **site skill** in your configuration for hosts,
  accounts, partitions and rates.

## Documentation

Full documentation: https://fleet-of-agents.readthedocs.io (sources in `docs/`, built
by Read the Docs from `.readthedocs.yaml`). To build locally: `pip install -r docs/requirements.txt`, then
`cd docs && make html`.

## Tests

    python3 -m unittest discover -s tests -t .

Stdlib only, like the tools. No test touches the real configuration, state
directory or tmux server.

## Nothing personal in here

Configuration and site skills live outside the repository (`~/.config/fleet`), and
the working tree names no person, host or project session: the incidents recorded in
comments, skills and `docs/checks-that-reassure.md` keep their dates, with roles in
place of names. That is what makes this shareable, and it is a rule for every change
rather than a scrub that happened once.

The history starts at the first commit of 2026-09-13 for the same reason. Earlier
commits still carried the names the scrub removed, so this was published from a
fresh history rather than by making the existing repository public; the commits
before that date are kept privately and are not part of this repository.
