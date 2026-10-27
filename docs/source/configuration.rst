.. _configuration:

Configuration
=============

All configuration lives in one TOML file, ``fleet.toml``, in the configuration
directory: ``$FLEET_CONFIG`` if set, otherwise ``~/.config/fleet``. It holds what a
human **declares**. Anything the tools observe at runtime lives in the state
directory instead (:ref:`concepts`).

The same directory holds:

``briefs/<name>.md``
   One brief per session, required — it is the session's identity: role, scope,
   territory, who it answers to. :doc:`tools/fleetspawn` refuses to launch a
   session without one; :doc:`tools/fleetsnap` flags a member that lacks one.

   **It is written, not filled in.** ``fleetspawn --brief-stdin`` takes the brief
   on stdin in the same command that spawns, because whoever asked for the
   session has already described it. :doc:`templates` is a shape to follow, not a
   form to send someone away with.

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

``[fleet]``
^^^^^^^^^^^

``name`` is this fleet's own short name::

   [fleet]
   name = "myfleet"

:doc:`tools/fleetspawn` stamps it on every pane it creates, as the ``@fleet``
option beside ``@agent``, and :doc:`tools/fleetboard` and the membership rule in
``fleet.panes.belongs`` read it back. **Two fleets can share a machine**, and
until this existed nothing could tell them apart: membership was "a pane with
``@agent`` on the default tmux server", so one fleet's tools counted the other's
sessions as members — demanding a brief and a color for a stranger's session,
and offering to restart it.

``fleet.config.fleet_name`` falls back to ``[mail].fleet`` when this is unset, so
a fleet that was named for mail before this section existed is already
recognizable. :doc:`tools/fleetinit` writes both and keeps them equal: one
identity with two readers, and a fleet called one thing by its panes and another
by its mail is worse than one with no name.

A fleet with no name counts every pane as its own, because it cannot say which
are not — and guessing in the excluding direction would hide real members.
Existing panes are labeled once with ``fleetinit --label-panes``.

``[updates]``
^^^^^^^^^^^^^

Where some other program derives this machine's pending software updates::

   [updates]
   status = "/var/lib/<host>-updates/status.json"
   stale_hours = 36     # a daily producer may miss one day and no more

:doc:`tools/fleetboard` **reads** this and declares nothing, the same contract it
holds for every other source. The path lives in configuration because it names a
host, and the application may not. Absent, the board says nothing about updates —
which is silence by choice, and distinguishable from a configured source that
could not be read.

``[backup]``
^^^^^^^^^^^^

Files some other program writes about this machine's backups::

   [backup]
   label         = "borg"
   last_archive  = "~/.local/state/borg/last-archive.json"
   last_run      = "~/.local/state/borg/last-run.json"   # optional, detail only
   stale_after_h = 26    # a nightly producer may run late, but not miss a night

Same contract as ``[updates]``: :doc:`tools/fleetboard` reads these and declares
nothing, and absent configuration means the board says nothing about backups.

``last_archive`` is the only file that decides anything, and the board asks it one
question: **how old is the newest archive that actually landed.** The producer must
therefore write it only after confirming the archive exists — not after a
successful return. A producer that rewrites it on every attempt turns the check
into "did the job run", which is the question that was already being answered and
not the one worth asking. The board reads ``time`` (ISO 8601, with an offset),
``archive``, ``nfiles`` and ``deduplicated_bytes``.

``last_run`` describes the latest *attempt*, whatever became of it. It is read
only once the alarm is already up, and supplies ``outcome`` and ``reason`` for the
detail. It never decides the color, because a run that skipped and exited cleanly
writes a benign outcome while no archive was made.

**No exit code is read, from either file.** A good night exits 1 routinely — "file
changed while we backed it up" is a warning — so a board that colored on ``rc``
would be red most mornings and ignored on the one that mattered.

``stale_after_h`` wants slack a day does not have: a slow night (a new disk, so
every inode is new and the file cache misses) lands the archive hours late, and a
24-hour window cries wolf the next morning.

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

``[context]``
~~~~~~~~~~~~~

Optional. When :doc:`tools/fleetcontext` recommends trimming a session, and what
the ``/compact`` it types asks the summary to keep. Each key has a default; an
unknown key is an error.

``compact_above``
   Tokens of context above which an idle session is a compaction candidate.
   Default ``250000``.
``clear_above``
   Tokens above which a repo or writing session with a clean tree and no runtime
   is also a *clear candidate*, for the human to decide on. Not below
   ``compact_above``. Default ``500000``.
``idle_minutes``
   A session active more recently than this is left for later. Default ``10``.
``compact_focus``
   One line appended to every ``/compact``. Default
   ``"keep job ids, file paths, open decisions and commitments"``.

``[notify]``
~~~~~~~~~~~~

Optional. Where :doc:`tools/fleetnudge` sends a phone push (`ntfy <https://ntfy.sh>`_)
when it could not deliver a watcher's line. Without it, nothing is pushed; the tool
still exits non-zero and logs the failure.

``ntfy_topic_file``
   Required in the section. A file holding the topic: either the topic alone, or a shell
   script with a ``TOPIC="..."`` line. An existing notification hook can then stay the
   one place the topic is written; it never needs to be copied into configuration.
``ntfy_server``
   Default ``"https://ntfy.sh"``.
``mute_file``
   Optional. While this file exists, no push is sent.

``[mail]``
~~~~~~~~~~

Optional. This fleet's identity in a shared mailbox, for :doc:`tools/fleetmail`.

``fleet``
   Required in the section. This fleet's name in addresses (``abrams`` in
   ``abrams/coord``). Short and lowercase.
``repo``
   Required in the section. The mailbox: any git URL or path.
``clone``
   Optional. The working copy, ``<state>/mailbox`` by default. It is observed state,
   not a declaration, so it belongs under the state directory.
``poll_minutes``
   Optional, default 5. How often the timer printed by ``fleetmail timer`` fetches.
   A poll interval is the latency floor for mail.

Who may correspond, and any extra guarded wording, are declared in the mailbox's own
``fleets.toml`` rather than here: both fleets must agree on them.

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
