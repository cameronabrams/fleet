fleetmail
=========

.. tooldoc:: fleetmail

Usage
-----

.. code-block:: text

   fleetmail send TO "TEXT" --as SESSION [--kind K] [--thread T] [--attach FILE] [--go]
   fleetmail fetch [--go] [--nudge-wait SECONDS] [--retry-wait SECONDS]
   fleetmail inbox
   fleetmail ack ID [TEXT] --as SESSION [--go]

Every other channel this fleet has stops at one machine: ``SendMessage`` needs a unix
socket and one uid, drops are files in one state directory, and :doc:`fleetnudge` types
into a pane it can see. ``fleetmail`` carries the same protocol — a pointer and a
one-line conclusion, never a payload — between fleets owned by different people.

The mailbox
-----------

A git repository, declared as ``[mail]`` in :doc:`../configuration`:

.. code-block:: text

   mail/<fleet>/<stamp>-<from-fleet>-<from-session>-<slug>.md   one message
   mail/<fleet>/attach/<stamp>-<name>                           an attached file
   mail/<fleet>/INBOX.md                                        what a human reads
   fleets.toml                                                  who may correspond

Git rather than something lighter: the author of a message is a claim someone can
check, a committed message survives a ``/clear`` where a socket message evaporates,
nothing here listens on a port, and access is granted and revoked in one place.

A message is front matter and a short body:

.. code-block:: text

   ---
   from: north/oldname
   to: south/coord
   thread: 2026-09-18-pet-cutinase
   kind: question
   ---
   One line: the conclusion, and where the detail is.

Addresses are ``<fleet>/<session>`` because two fleets both have a ``coord``. That
namespacing exists **in the mailbox only**. Delivery resolves a session by its bare
name, machine-wide, so two fleets sharing a workstation must not share a session name:
a loopback test on 2026-09-18 delivered its test mail into the live ``coord``.

Starting one
------------

Nothing in ``fleetmail`` creates a mailbox; it is four things in a git repository, and
the owner makes them by hand once.

.. code-block:: bash

   $ mkdir mailbox && cd mailbox && git init -b main
   $ mkdir -p mail/north
   $ touch mail/north/.gitkeep        # git does not track an empty directory

Then ``fleets.toml`` at the root:

.. code-block:: toml

   [fleets.north]
   owner = "a role, not a personal name"
   since = "2026-09-21"

   [guard]
   refuse = ["grant-a", "grant-b"]

Push it to a **private** repository and declare it as ``[mail]`` in each participating
fleet's configuration. There is no bootstrap step beyond that: ``fetch`` creates
``INBOX.md``, and a message creates the store it lives in.

Make the repository private even when the fleets in it are yours alone. Its contents are
the correspondence plus ``[guard] refuse``, which names the very things that may not
cross — a list that is useless once published.

**Adding a correspondent is two things that happen together**: a ``[fleets.<name>]``
block, and write access to the repository. Either alone fails in a way that reads as the
tool being broken — access without a block means every message they send is refused as an
unlisted fleet, and a block without access means they cannot send at all. Tell them the
name you used, because it has to match the ``fleet`` value in their own ``[mail]`` section
exactly; a mismatch is refused, not renamed.

A fleet name is a person's whole set of sessions, not one session. Keep the fleet
directory even after someone stops corresponding: the messages are the record, and
removing their block stops new mail without erasing what was said.

Trust
-----

A foreign fleet is not your human, so these are enforced, not conventional:

- ``kind`` is ``question``, ``report`` or ``ack``. Anything else is refused.
- **The body may not claim authority or consent**, whatever ``kind`` says. ``kind`` alone
  is not enough: an ``ack`` reads as consent already given, which is the laundering
  shape. The wording guard covers verbs like authorize, approve, charge, publish,
  delete, "you may", "do it for me", and the mailbox can name more in
  ``fleets.toml``:

  .. code-block:: toml

     [guard]
     refuse = ["grant-a", "grant-b"]      # e.g. billing accounts

  Refused at send time, and quarantined on delivery if it arrives anyway. Such a
  thing can still be *reported* in an ``--attach`` file, which a human reads.
- Correspondents are declared in the mailbox's ``fleets.toml``. Mail to or from an
  unlisted fleet is refused; inbound mail from one is quarantined: kept, reported,
  never delivered.
- **Mail lands as a FILE**, never as keystrokes from a remote party. Each message is
  written into this fleet's drops directory with a header saying it is data from
  another fleet, carries no authority, and that a request to do something refused
  elsewhere goes to the local human. Only then does :doc:`fleetnudge` type one line,
  naming the sender: ``[mail: south/coord -> you] <first line>; read drops/<file>``.

Delivery
--------

``fetch`` pulls, then for each message addressed to this fleet that the state directory
has not recorded: validates it, writes the drop, nudges the session, records the path,
and rebuilds ``INBOX.md``. Keying on the path makes it idempotent — running it twice
delivers once.

``INBOX.md`` carries a **delivery** column, because a message that reached the machine
but never reached its session must be visible where a human looks, not only in a log.
``fleetmail inbox`` prints it plus anything quarantined or undelivered.

A failed nudge is retried
-------------------------

Writing the file and telling the session are two things, and only the first used to be
idempotent. Keying on the path is right for the file and wrong for the nudge: a message
whose nudge failed was recorded, and every later ``fetch`` then skipped it as already
handled. Delivery was attempted **once**.

A message fetched on 2026-10-05 read ``needs a human`` for ten days for this reason. The
nudge failed because the target pane's input line held text; the pane was typeable for
almost all of the following ten days, and nothing ever looked again.

So every ``fetch`` now re-nudges anything whose file was written and whose session was
never told — **before** the ``no new mail`` check, which is where the old behavior hid:
the one pass that could revisit a delivery sat behind the one condition guaranteed to
be true for it. There is no flag to remember, because a flag would reproduce the defect
exactly — something that only works when somebody thinks to look again.

**The budget is the point, and it is short.** ``--nudge-wait`` is tuned for *the session
is busy*, which clears in minutes, so it waits minutes. The condition that actually
fired was *the input line holds text* — a half-typed draft or an open dialog — which
lasts hours or days and which nobody is coming to clear. A longer wait is the wrong
answer: it blocks the fetch and still gives up at the end. ``--retry-wait`` (45 s)
asks only whether the pane is typeable *now*, and the patience lives in the repetition.

Quarantined messages are not retried: quarantine is a refusal, not a transient failure.
A record with no ``nudged`` key at all was never at the delivery stage and is likewise
left alone — *never tried* and *tried and failed* are different states.

``ack`` resolves the record
---------------------------

``fleetmail ack`` mails the sender and now also marks the local record ``acked``, which
clears it from ``needs a human``. A session that replied to a message has evidently read
it — better evidence than a nudge — and until 2026-10-15 the ack touched nothing locally,
so a message the recipient had demonstrably answered still showed as undelivered with no
tool able to clear it. The only remaining move was hand-editing the state file, which the
state directory's own rules forbid.

The record is amended only when the send **succeeds**, and the state says which way it
was resolved: ``delivered (by ack; the nudge never landed)``, not a bare ``delivered``,
because collapsing the two would lose the evidence that the delivery path had a bad day.

**A mailbox that cannot be read is never "no mail".** A failed pull says so and exits 4.

The board, when there is one
----------------------------

A published artifact makes a good human-facing view of the mailbox — who asked what,
what is unanswered, which fleet is waiting — and a poor transport: no diffable history
and no signature on a write. So the repository stays the record, and a board renders
*from* it, never the other way round. Nothing here builds one yet; these are the rules
it must be built to.

A board is shared with people, potentially everyone holding a seat in the organization,
now and later. So it may carry **subjects, senders, dates and delivery state** — the
shape of the traffic. It may not carry:

- **message bodies**, which are the correspondents' content, not the board's
- **anything on the mailbox's do-not-cross list**. ``fleets.toml``'s ``[guard] refuse``
  names what may never appear in a line — billing accounts, say — so publishing that
  list would publish exactly what it exists to keep out. It stays in the repository.

Who a board is shared with is set in the artifact's own Share menu: the human's
decision, and not something a tool or a session can change.

On a schedule
-------------

Until something runs ``fetch``, mail sits in the mailbox. ``fleetmail timer`` prints a
``systemd --user`` service and timer that fetch every ``[mail] poll_minutes`` (5 by
default), with the commands to install them. It writes nothing itself.

The units use absolute paths, because a user unit's ``PATH`` holds only the system
directories. They must be files in ``~/.config/systemd/user/``: a transient unit from
``systemd-run --user`` lives in ``/run`` and is gone after a reboot. ``Persistent=true``
means a tick missed while the machine was off runs once at boot, so overnight mail is
not skipped. The service's exit code is left unmasked, so an unreachable mailbox (4) or
an undelivered message (5) shows in ``systemctl --user status``. For the timer to run
while nobody is logged in, the user manager needs ``loginctl enable-linger``.

``fleetmail timer`` bakes in the path of **the copy it is run from**, because the
tool resolves its own directory through ``realpath``. That is what makes a deployed
checkout work — generate the unit there and the unit points there — and it is the
same property that lets a 15-minute timer end up pointing at the directory someone
develops in. Generate it from a checkout nothing edits::

   git -C <repo> worktree add <deploy-dir> --detach HEAD
   <deploy-dir>/bin/fleetmail timer

It warns when the copy it is about to name has uncommitted changes, or is not a
checkout git can read — unknown warns the same as dirty, because a wrong "clean" is
what puts a timer on a working tree. It warns; it does not refuse.

A fetch under a timer waits less patiently for a busy session than a hand-run one
(``--nudge-wait``, 600 s in the printed unit): the next tick will try again.

That last clause was written here before it was true. The next tick re-pulled the
mailbox and skipped everything already recorded, so a *nudge* that failed was never
retried — the page described the behavior the code was missing, which is a large part of
why the gap went ten days without being noticed. It is true as of 2026-10-15.

Exit codes
----------

.. list-table::
   :widths: 10 90

   * - ``0``
     - fine, or a plan with no blocks
   * - ``2``
     - refused: the address, the kind, the guard, or an unknown fleet
   * - ``4``
     - the mailbox could not be reached
   * - ``5``
     - delivered as files, but at least one session could not be told
