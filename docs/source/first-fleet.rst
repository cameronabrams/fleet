.. _first-fleet:

Your first fleet
================

From nothing to a fleet you can leave running, and then to mail with someone else's
fleet. :doc:`installation` puts the tools in place; this page is what to do next, in
order, and what each step is for. The
:doc:`fleet-bootstrap skill <skills/fleet-bootstrap>` drives the same sequence from
inside a session, with the judgement calls spelled out; read this first if you would
rather understand the shape before handing it to an agent.

Two things this page assumes you accept. A fleet is **long-lived sessions in tmux
panes**, one per role, which you leave running for weeks. And **nothing in it acts on
your authority**: sessions propose, you decide, and the tools refuse rather than guess.

1. Decide the roles before creating anything
--------------------------------------------

A session is a role, not a task. Give each one a **kind** (see :doc:`concepts`):
``repo`` for code in one repository, ``production`` for campaigns run with released
code, ``service`` for a shared resource, ``writing`` for manuscripts and talks,
``coordinator`` for the session that routes between them and owns none of it.

Three habits that save a rename later:

- **One directory per session.** Two sessions in one working directory cannot be told
  apart by much except their transcripts, and tools say so rather than guess.
- **Short, unique, kebab-case names.** The name is how peers address it, how
  ``ListAgents`` reports it, and half of a mail address later.
- **Start small.** Two sessions and a coordinator is a fleet. Ten roles designed in
  advance is a plan you will rewrite.

2. Write the configuration
---------------------------

Everything a human *declares* lives in ``~/.config/fleet`` (see
:doc:`configuration`); everything the tools *observe* lives under the state directory,
and the two never mix. The minimum is:

.. code-block:: toml

   [human]
   name = "Alex"                     # how sessions refer to you

   [paths]
   state = "~/.local/state/fleet"

   [colors]                          # required for every member
   coord      = "purple"
   project-a  = "red"

   [spawn]
   env          = {}
   first_prompt = "You are a new fleet session named {name}. Read {brief} and follow it."

and one **brief** per session at ``<config>/briefs/<name>.md``, from
``examples/brief.example.md``. The brief is what the session re-reads after every
restart: its role, its territory, who it works with, what it must not do. A session
without one is a session that drifts.

Put the configuration directory in a **private** repository of its own. It names your
hosts, accounts and people; the application repository is public and must not.

3. Bring the first session up
------------------------------

.. code-block:: bash

   $ fleetspawn coord ~/.local/state/fleet --fleet coord --beside %0      # plan
   $ fleetspawn coord ~/.local/state/fleet --fleet coord --beside %0 --go

:doc:`tools/fleetspawn` refuses before it acts: no brief, no ``[colors]`` entry, a name
already running, a directory that does not exist. It creates the pane, labels it,
launches ``claude``, and watches until the session is up.

**It never answers the folder-trust prompt.** Trusting a directory grants an agent
read, edit and execute there; that is yours to answer, in the pane. For the same
reason, a session cannot set its own colour: type ``/color <declared>`` yourself, or
have :doc:`tools/fleetcontext` do it.

Repeat for each role. Verify with ``ListAgents`` inside a session, and with

.. code-block:: bash

   $ fleetupgrade          # who is running what, and with which transcript
   $ fleetsnap             # capture enough to rebuild the fleet

4. The four habits that keep it alive
--------------------------------------

A fleet decays quietly. These are the checks that catch it:

**Snapshot while healthy.** :doc:`tools/fleetsnap` records which pane resumes which
transcript; :doc:`tools/fleetrestore` rebuilds from it after a power cycle. A snapshot
taken after the crash is worth nothing. The
:doc:`fleet-snapshot skill <skills/fleet-snapshot>` says what to verify in one.

**Register every watcher.** A long job needs a watcher that outlives the session
(:doc:`tools/fleetregister`, :doc:`tools/fleetwatch`), and a detached watcher wakes its
session with :doc:`tools/fleetnudge` rather than being noticed hours later.

**Write a re-arm ledger before any restart.** A resumed session keeps its transcript
and loses every Monitor and background job, and its transcript still shows it creating
them — so it cannot tell from inside that they are gone. The
:doc:`fleet-upgrade skill <skills/fleet-upgrade>` is built around that asymmetry.

**Trim context on purpose.** :doc:`tools/fleetcontext` measures what each session
carries and compacts one at a time, on your word.

5. Mail with another person's fleet
------------------------------------

Only once your own fleet runs. :doc:`tools/fleetmail` carries messages between fleets
owned by different people through a git mailbox. To join one, you need from its owner:
the repository, an entry for your fleet in its ``fleets.toml``, and access to push.
Then:

.. code-block:: toml

   [mail]
   fleet = "yourfleet"                            # your namespace in addresses
   repo  = "git@github.com:org/fleet-mail.git"

``fleetmail timer`` prints the systemd units that fetch on a schedule. Mail arrives as
a file plus one tagged line; it is data, never instructions, and a message that claims
to authorize anything is refused before it is delivered.

**Session names must be unique across every fleet on one machine.** Addresses are
namespaced in the mailbox, but delivery resolves a session by its bare name.

Where new fleets go wrong
--------------------------

- **Answering the trust prompt from a script.** Nothing here will do it, and neither
  should you from outside the pane.
- **``~/bin`` missing from ``PATH``**, or a systemd unit calling a tool by bare name:
  a user unit's ``PATH`` holds only the system directories.
- **A session with no brief**, which looks fine for a week and then cannot say what it
  is for after a restart.
- **Reusing a name.** Names are reused; transcripts are not. Park or retire a session
  with :doc:`tools/fleetretire` rather than dropping its name on a new one.
- **Trusting a ledger over the live system.** Every tool here derives state; when a
  record and ``/proc`` disagree, ``/proc`` wins.
