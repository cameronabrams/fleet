fleetmail
=========

.. tooldoc:: fleetmail

Usage
-----

.. code-block:: text

   fleetmail send TO "TEXT" --as SESSION [--kind K] [--thread T] [--attach FILE] [--go]
   fleetmail fetch [--go] [--nudge-wait SECONDS]
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
   from: north/literature
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

A fetch under a timer waits less patiently for a busy session than a hand-run one
(``--nudge-wait``, 600 s in the printed unit): the next tick will try again.

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
