fleetwatch
==========

.. tooldoc:: fleetwatch

Needs a ``[cluster.<name>]`` section and non-interactive ssh to it
(:doc:`../configuration`).

How it decides
--------------

**Live work** comes from one ssh round trip: ``squeue`` rows per array parent
(tasks, states, pending reasons) and each job's working directory from ``sacct``.
The remote command ends with a marker line; without it the query counts as
**failed**, never as "no work" — an ssh banner and an empty queue otherwise look
the same.

**Owner** is the first ``[owners]`` fragment found in the working directory, else
``UNATTRIBUTED``.

**How long the cluster has been unreachable** is recorded every run, success or
failure, in ``<state>/cluster-reach.json`` — only a success moves ``last_good``,
but ``last_checked`` moving either way is what tells "down since 08:35" from
"nobody has looked since 08:35". A failed query then reads

.. code-block:: text

   !! CLUSTER QUERY FAILED (ssh <host>) -- no job table. ...
      unreachable for 1h 20m -- last good 2026-10-22 10:00 EDT

The sentence alone was honest and carried no duration, so a two-minute blip, a
two-day maintenance window and a cluster that was never reachable all printed the
same words. A cluster with **no** recorded good read says exactly that rather than
reporting an outage of zero length, which would date the outage to the creation of
the state file. The absolute time is in the human's own zone and labeled; the
duration is also in ``--json`` as ``cluster_down_for_s``, and :doc:`fleetboard`
puts it in its failure note.

**The reservation table is recorded, not interpreted.** The same ssh round trip
runs ``scontrol show reservation`` and appends its output to
``<state>/cluster-reservations.log`` **when it changes**, and nothing parses it.

This is an experiment, and it is phrased as one on purpose. SLURM holds planned
maintenance as a reservation that is readable *while the cluster is still up* —
exactly when a warning would be worth having — but whether this site creates them
is unknown. ``scontrol show reservation`` answered ``No reservations in the
system`` when the cluster returned from a maintenance window, and that is weaker
evidence than it looks: a completed ``MAINT`` reservation is removed, so an empty
table just after a window is what you would see whether or not the site uses them.
One look after the fact cannot tell the two cases apart, and a parser written
against that guess would answer the question with its own assumptions.

So the log keeps what the table said and waits. If a ``MAINT`` entry ever appears
*ahead* of an outage, the mechanism is real and advance warning can be built on
evidence. If months pass with nothing, that is the answer too, and it cost one
extra line in a round trip that was already happening.

**Held** work — pending only for a reason in ``held_reasons`` — needs no watcher: it
cannot produce anything to observe. The moment the reason changes, it needs one.

**Watched** means a registration in ``<state>/watchers/`` whose process is alive:
same pid *and* same start time, and not a zombie (see :doc:`fleetregister`).
Command lines are only advisory — a child of a session counts as a *possible*
watcher only if it names the job id *and* shows a poll loop (``sleep <n>``), and the
tool's own process tree is excluded.

Report sections
---------------

``LIVE WORK WITH NO WATCHER``
   live, not held, no live registration
``WATCHER ON WORK THAT IS NO LONGER LIVE``
   a live registration for a job not in the queue
``looks like a watcher but is NOT REGISTERED``
   advisory inference, with the ``fleetregister`` command to fix it
``REGISTERED WATCHER IS DEAD``
   the registered process is gone while its job is still live, or ``sacct`` cannot
   show that the job ended
``finished``
   the registered process is gone and ``sacct`` shows only terminal states — the
   normal end of a watcher; clear it with ``fleetregister --clear``
``WorkDir not in [owners]``
   add a row to configuration
``held``
   nothing to watch

``fleetwatch <session>`` limits the report to work that session owns or watches.

**An unrecognized argument is refused, not answered** (exit 2), and the message lists
the session names that exist. ``fleetwatch list`` — an invented subcommand — was
previously taken as a session filter: it matched nothing, and the tool printed
"no live cluster work", which reads as a quiet cluster rather than a typo. The same
applied to ``--json``, where the caller saw a clean empty result. Unknown options and
a second session name are refused for the same reason. A filter that matches nothing
is the tool's own signature failure: a false all-clear that nobody investigates.

Who can see the fleet
---------------------

Attaching to the tmux server hands a person every pane: sessions already past the
folder-trust prompt, weeks of context, and peers that treat a line from one of them
as a teammate's request. So the report ends by naming every attached client, where
it came from (from ``who``), and how long it has been idle.

``MORE THAN ONE CLIENT IS ATTACHED``
   normal is one. A second is not proof of anything — a second terminal of your own
   looks identical — but it is the one thing worth seeing without being asked.
``COULD NOT LIST TMUX CLIENTS``
   a failed query and an unattached server both produce no rows, and only one of
   them means what an empty list looks like.

**This reports; it does not guard, and a lock here would be close to theater.**
Whoever can attach can equally read the Claude credentials, the ``gh`` token and the
ssh key — they sit in the same account and need no tmux — so authenticating this one
door defends nothing that is not already open. The boundary is the account, not the
fleet. What a second client genuinely changes is that the panes are *already*
trusted and *already* full of context, so the useful control is noticing, and then
tmux's own ``lock-after-time`` with a ``lock-command`` that actually exists on the
machine. Check that one by hand: a lock whose command is missing fails toward
unlocked.

Times are shown in the zone from ``[human]`` (:doc:`../configuration`) and labeled,
because an unlabeled time in the wrong zone reads as right.

Did the result reach the session?
---------------------------------

Watching is half the question. A watcher can run perfectly and its *result* still
never arrive: :doc:`fleetnudge` types the line into the session's pane, and when it
cannot, it falls back to the ``[notify]`` phone push — which ``mute_file``, when the
file exists, silences by design. Nobody is then told by any channel, and
``<state>/nudges.log`` is the only trace, while the job above reads as **watched**.
That is the reassuring direction, so the log is read here.

``NUDGE NEVER ARRIVED AND NO PUSH WENT OUT``
   the session was not told and neither was the phone. A record whose push result
   is anything but a 2xx counts here, and so does one with no push result at all:
   unknown is read as *not told*.
``not delivered, but the phone push did go out``
   a human was told out of band; the session still never got the line.
``FLEETNUDGE STOPPED MID-RETRY``
   the log ends on ``waiting`` for that session and job. ``fleetnudge`` always exits
   through an outcome, so it was killed before it could deliver, give up or push,
   and nothing else recorded the attempt. Only counted once the entry is older than
   two hours — a retry loop still running looks exactly the same.

**"Not delivered" is not the same as "nobody was told."** ``fleetnudge`` declines
when it is running *inside* the session it would type into: the in-session task
doing the running already notifies it, so the content reaches its reader by
another route and nothing is missing. Those rows are excluded — from the hole
lists and from the older-than-the-window count alike. On 2026-10-15 two of the
three rows driving this section were exactly that, and a board that invents holes
gets read past, which costs the real ones.

The exit code **cannot** carry that distinction and is not used for it. The
decline is code 2, which it shares with caller errors that genuinely lose the news
— a line over the 200-character limit, a malformed job id. Bucketing on the code
would trade one defect for its mirror image, and the mirror image is the one that
matters: a real hole rendered as fine. So ``fleetnudge`` records
``notified_otherwise`` on every undelivered record, true *and* false, and this
reads the field. An absent field and an unrecognized reason are both read as a
hole.

**A hole here cannot be cleared by any tool, only by ageing out of the window.**
There is no ack and no retry: a session that learned the result by another route
has no way to say so, and nothing re-attempts a nudge that gave up. Both exist for
undelivered *mail* (`notified_otherwise`, and a retry on every `fleetmail fetch`)
and neither was built here, because a nudge has no recurring driver to retry from
and no verb for the recipient to answer with. Until that changes, a red line can
outlive the problem it reports — which is worth knowing when reading this section,
since a permanent alarm is read past and a real one then arrives somewhere nobody
looks.

One exception, marked as such in the code: records written before 2026-10-15 carry
only the sentence, so that exact sentence is matched. It is a parse of prose, it is
pinned by a test against the string ``fleetnudge`` actually emits, and
``NUDGE_DAYS`` is 7 — so nothing in the window can predate the field after
2026-10-22 and the match can be deleted.

Undelivered mail is covered by the same rows: :doc:`fleetmail` delivers through
``fleetnudge``, and the sender travels with the failure as well as the success.
Mail that never *became* a nudge — quarantined, or written to a drop and never
handed over — cannot appear in that log, so it is **counted** here with a pointer to
``fleetmail status``, which owns those rows. An empty section must not be readable
as "everything got through".

A hole is listed even when a later nudge to the same session and job did land: that
later line is named beside it, to be checked, because a different message about the
same job is not this message. The window is the last seven days; anything older is
counted, never dropped in silence. A **missing** log means no nudge was ever sent —
``fleetnudge`` creates it on first use — but an unreadable one, or a line that will
not parse, is reported as itself. "No rows" must never be something the check
produced by failing.

.. _fleetwatch-json:

``--json``
----------

Three tools in this repository read this output — :doc:`fleetretire`, before it
stops a session, :doc:`fleetboard`, and :doc:`fleetupgrade`, which refuses to restart
a session whose runtime it cannot see — so its shape is a public interface, and
this repository's rule makes "the shape of its ``--json``" part of the versioned
surface. It is written down here so that rule can be applied.

Top-level keys:

.. list-table::
   :widths: 24 76

   * - ``cluster_ok``
     - **false when the cluster query failed.** Everything else about live work is
       then meaningless, not empty. Read this first. **True** with no cluster
       configured: the job list is then empty and that emptiness can be trusted.
   * - ``cluster_configured``
     - false when ``fleet.toml`` declares no ``[cluster.<name>]``. For a caller
       that wants to say *why* there is no work; ``cluster_ok`` alone is enough to
       decide whether the job list can be believed.
   * - ``jobs``
     - live jobs: ``job``, ``tasks``, ``states``, ``workdir``, ``owner``,
       ``reasons``, ``held``, ``watched_by`` (a list — empty means nobody)
   * - ``stale_watchers``
     - ``session`` / ``job`` / ``pid`` for monitors pointing at jobs no longer
       live **and with nothing live left to watch**. A watcher part way through a
       set is not here; see ``watchers_partway``.
   * - ``watchers_partway``
     - ``session`` / ``job`` / ``pid`` / ``still_watching`` — a job that has
       finished whose watcher is the same process as one still polling live jobs.
       Not a fault, and not actionable: the registration goes when the watcher
       exits. Separated from ``stale_watchers`` on 2026-10-06, so a caller that
       treats that key as an alarm is not woken by a campaign finishing one job at
       a time.
   * - ``dead_watchers``
     - registrations whose process is gone while the job is not finished
   * - ``finished_watchers``
     - registrations whose process exited *because* the job ended — the normal end
       of a watcher, reported separately so that a campaign ending does not train
       everyone to ignore the dead list
   * - ``delivery``
     - undelivered-nudge rows; ``silent`` is the one that means a session was never
       told and no push went out
   * - ``clients``
     - ``attached`` (who can type into a pane) and ``error``

``cluster_ok`` is the field that is easy to skip and expensive to skip. The
command prints a banner and **exits 0** when its ssh query fails, so a caller
reading the display table instead finds no job rows and concludes there is no
work. :doc:`fleetboard` did exactly that until 2026-10-04 and drew an unreachable
cluster as a calm fleet.

No cluster configured
`````````````````````

A machine with no scheduler declares no ``[cluster.<name>]``, and then the answer
to "what is running on the cluster" is known: nothing. Until 2026-10-25 this tool
raised at import instead, and took the rest of the report with it — watcher
liveness, nudge delivery and attached clients, none of which needs a cluster.
Every caller read the traceback as *unknown*: :doc:`fleetupgrade` refused every
session on the machine ("fleetwatch could not read the cluster, so runtime is
unknown"), and the board drew ``?`` in every work cell.

Now no ssh is attempted, ``jobs`` is empty, ``cluster_ok`` is true,
``cluster_configured`` is false, and nothing is recorded as the cluster's
reachability. The display says ``no [cluster] configured in fleet.toml -- no
cluster work to watch.`` A registered watcher on such a machine stays in
``dead_watchers``, never ``finished_watchers``: there is no sacct to prove its
job ended. Several clusters with none named is still an error.

Why some keys begin with an underscore
``````````````````````````````````````

Rows in ``dead_watchers`` and ``finished_watchers`` are the watcher's own
registration file, loaded verbatim, with this tool's findings added to it:
``_why``, ``_states`` and ``_file``. The underscore keeps those out of the
registration's key namespace, so a field this tool computes can never be mistaken
for one the watcher wrote.

**They are part of this contract, not private.** ``_states`` is the only route by
which a job that ended badly reaches a caller — the job is over, so it holds no
watcher and appears in no live row.
