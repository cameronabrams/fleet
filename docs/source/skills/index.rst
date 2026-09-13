.. _skills:

Skills
======

A Claude Code *skill* is a packaged set of instructions a session loads when a task
matches its description. The tools do the mechanical work; the skills carry the
judgement — the sequence, the checks, and the failures each step exists to prevent.
``install`` links each one into ``~/.claude/skills``.

The pages below are the skills themselves, rendered from ``skills/<name>/SKILL.md``.

:doc:`fleet-bootstrap`
   Found a fleet from a coordinator, or add or retire one session: role design,
   briefs, :doc:`../tools/fleetspawn`, verification.

:doc:`fleet-snapshot`
   Capture, verify and restore the recovery snapshot, and check a restore that came
   back wrong.

:doc:`fleet-upgrade`
   Roll sessions onto a newer claude binary without losing their context or silently
   killing their monitors.

:doc:`slurm`
   SLURM mechanics and the traps that give confident wrong answers. Site-independent:
   pair it with a *site skill* in your configuration for hosts, accounts, partitions
   and rates.

.. toctree::
   :maxdepth: 1
   :hidden:

   fleet-bootstrap
   fleet-snapshot
   fleet-upgrade
   slurm
