# fleet

[![Documentation Status](https://readthedocs.org/projects/fleet-of-agents/badge/?version=latest)](https://fleet-of-agents.readthedocs.io/en/latest/)

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
| `fleetspawn` | bring one new session in, or a parked one back (plan by default) |
| `fleetretire` | park or retire one session: checks, resume recipe, `/exit` (plan by default) |

## Skills

- `fleet-bootstrap` — found a fleet from a coordinator, or add / park / retire one
  session: role design, briefs, `fleetspawn`, verification. Templates in
  `examples/brief.example.md` and `examples/conventions.example.md`.
- `fleet-upgrade`, `fleet-snapshot` — rolling a binary upgrade without losing
  monitors; snapshotting for recovery.
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

## Before making this public

Configuration and site skills live outside the repo, and the working tree names no
person, host or project session (scrubbed 2026-09-13; incidents keep their dates,
with roles in place of names). **The git history still does**: earlier commits
carry the names the scrub removed. Publish from a fresh history, or rewrite it,
rather than flipping the existing repository to public.
