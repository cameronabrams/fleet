.. _configuration:

Configuration
=============

All configuration lives in one TOML file, ``fleet.toml``, in the configuration
directory: ``$FLEET_CONFIG`` if set, otherwise ``~/.config/fleet``. It holds what a
human **declares**. Anything the tools observe at runtime lives in the state
directory instead (:ref:`concepts`).

The same directory holds:

``briefs/<name>.md``
   One brief per session, required. :doc:`tools/fleetspawn` refuses to launch a
   session without one; :doc:`tools/fleetsnap` flags a member that lacks one.
   Template: :doc:`templates`.

``conventions.md``
   The fleet's working rules, which every brief points to.

``events.toml``
   Fleet events for :doc:`tools/fleetgantt` (optional).

``skills/<name>/``
   Site skills (hosts, accounts, partitions), linked by ``install`` alongside the
   application's skills.

A complete example is in ``examples/fleet.example.toml``:

.. literalinclude:: ../../examples/fleet.example.toml
   :language: toml

Sections
--------

``[human]``
~~~~~~~~~~~

``name``
   How sessions refer to the human they work for.
``aliases``
   Other words sessions use for the human, such as a role or a pronoun.

``timezone_file``
   A file holding the human's current time zone (e.g. ``America/New_York``), re-read
   on every run.
``timezone``
   A fixed zone, used when the file is absent or unusable.

``name`` and ``aliases`` are read by :doc:`tools/fleetwaiting`, which builds its
"blocked on the human" patterns from them; "the human" and "the user" always count.
Without a name it matches only those two, and says so. The zone settings are read by
:doc:`tools/fleetgantt`, which falls back to UTC and labels whichever it used.

``[paths]``
~~~~~~~~~~~

``state``
   The state directory. Default ``~/.local/state/fleet``. Manifests, watcher
   registrations (``watchers/``) and re-arm ledgers (``rearm/``) live here.
``conventions``
   Where the conventions file is. Declared for sessions and skills to find; no tool
   reads it.

``[spawn]``
~~~~~~~~~~~

``env``
   A table of environment variables set on every session launch, e.g.
   ``{ NOTIFY_AGENT = "1" }``. Used by :doc:`tools/fleetspawn`, by
   :doc:`tools/fleetrestore`, and in the relaunch commands
   :doc:`tools/fleetupgrade` prints, so a session comes back from a restore or an
   upgrade with the environment it was spawned with.
``first_prompt``
   The first prompt :doc:`tools/fleetspawn` gives a new session. ``{name}`` and
   ``{brief}`` are substituted. Default: ``You are a new fleet session named {name}.
   Read {brief} and follow it.``

``[colors]``
~~~~~~~~~~~~

``<session> = "<color>"`` for **every** member. Values must be ones ``/color``
accepts: ``red``, ``blue``, ``green``, ``yellow``, ``purple``, ``orange``,
``pink``, ``cyan``; anything else is a configuration error. Two sessions may share
a color.

A session's color is applied by the human typing ``/color <c>`` in its pane — there
is no launch flag, and a session cannot set its own. A ``/clear`` drops the live
color while keeping the name, which is why the declaration lives here:
:doc:`tools/fleetsnap` and :doc:`tools/fleetupgrade` compare the live color against
it and print the command to fix a difference.

``[cluster.<name>]``
~~~~~~~~~~~~~~~~~~~~

Required by :doc:`tools/fleetwatch`. With one cluster configured the name is
implied; with several, a tool must be told which.

``ssh_host``
   An ssh destination that works non-interactively.
``user``
   The scheduler user whose jobs are listed.
``job_id_re``
   A regular expression for the *shape* of a job id, e.g. ``"[0-9]{6,9}"``. Used to
   recognize job ids in watcher command lines.
``held_reasons``
   Scheduler pending reasons that need a human to release. A job pending only for
   these needs no watcher. Default ``["JobHeldUser", "JobHeldAdmin"]``.
``scheduler``, ``rate_usd_per_su``, ``[[cluster.<name>.accounts]]``
   Declared for skills and humans (costing, choosing an account); no tool reads
   them.

``[owners]``
~~~~~~~~~~~~

``"<WorkDir fragment>" = "<session>"``. :doc:`tools/fleetwatch` attributes each job
to the first session whose fragment appears in the job's working directory.
**First match wins**, so put specific fragments before general ones. A job matching
no fragment is reported ``UNATTRIBUTED``, never guessed.

``[parked.<name>]`` and ``[retired.<name>]``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Sessions stopped with :doc:`tools/fleetretire`, one table each:

``uuid``
   Required. The session's resume uuid — the transcript that must not be relaunched.
``since``
   Required. ``YYYY-MM-DD``.
``note``
   Optional.
``group``, ``cwd``
   Optional. The fleet group and working directory the session had, so
   :doc:`tools/fleetgantt` keeps its lane in its group and can place its unnamed
   transcripts. Neither is knowable once the process is gone.

:doc:`tools/fleetretire` prints the entry; the configuration owner adds it. A name
may not be both parked and retired, and ``uuid`` must be a full session uuid.

Entries are keyed by transcript: :doc:`tools/fleetrestore` refuses to relaunch a
listed uuid, and a new session that reuses the name is unaffected.
:doc:`tools/fleetspawn` refuses a retired name, and a parked one except with
``--resume`` and its uuid. :doc:`tools/fleetsnap` flags a live session whose
transcript is listed — remove the entry once a parked session is back.

``[authority]``
~~~~~~~~~~~~~~~

Optional, free-form. :doc:`tools/fleetsnap` copies it verbatim into every manifest.
If you record a grant of the human's authority here, record its current status
alongside it — a snapshot re-stamps whatever it copies with a fresh date, and a
lapsed grant stored alone reads as current.
