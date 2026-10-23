fleetroll
=========

.. tooldoc:: fleetroll

Why a tool, when fleetupgrade deliberately will not
---------------------------------------------------

:doc:`fleetupgrade` is explicit that it *reports only* — it "never restarts,
never kills, never types into a pane and never answers a dialog". That boundary
is about **eligibility**, and this does not cross it. ``fleetupgrade`` still
decides who *may* be rolled and an agent still decides who *is*. What moves into
a tool is **how**: the keystroke sequence, which was hand-copied runbook prose.

Prose is what failed. On 2026-10-23 a coordinator read a resumed pane's
**replayed** ``/exit`` farewells as five live failed exits, and refused to roll a
healthy session on every fire for nine consecutive fires. ``--resume``
re-renders a session's transcript, and ``/exit`` records its farewell, so every
exit a session has ever made is drawn above the live input line on every
restart. A tool that owns the sequence cannot make that mistake, because it never
reads above the input line — it uses ``fleet.panes.type_line``, which checks the
input line alone and clears it on failure.

The narrow grant
----------------

Under auto mode an agent's raw ``tmux send-keys`` is denied. The rule that
unblocks it, ``Bash(tmux send-keys:*)``, is a **prefix** rule: it cannot
constrain which keys reach which pane, so it permits typing arbitrary text into
any pane's shell. ``Bash(fleetroll:*)`` permits one verified sequence against one
named session.

**The tool is what makes the grant narrow**, and that is the larger half of why
it exists. Granting the rule is the fleet owner's decision; nothing here asks for
it, and the tool is equally useful driven by hand.

What it refuses
---------------

Eligibility is **re-derived** from ``fleetupgrade --eligible --json`` on every
run and never taken from the caller — a driver that has already decided to roll
something is the last thing to trust about whether it may. If that cannot be
read, the answer is *unknown* and the roll is refused: a roll that proceeded
because the gate could not be consulted is a roll with no gate.

It also refuses when the name is not live or resolves to more than one process,
when the session is **the one asking** (tested on process ancestry, not on the
name — a name can be changed), when it is already on the target, when there is no
``--resume`` uuid in its argv, when no binary for the target is in the version
store, and when the pane is busy or showing a dialog. **It never answers a
dialog**: a trust prompt, the background-work dialog and the resume-mode prompt
each mean a human has been asked something.

The sequence
------------

Record the pid and its start time first; every later claim is scoped to that pid.
Type ``/exit`` as its own send and require the **input line** to read exactly
that. Press Enter. Poll until that pid is gone — and if it is not, stop, having
changed nothing further. **Never kill, never fall back to a signal**: a session
that will not exit is holding something, and killing it is how the thing it was
holding becomes invisible.

Relaunch from the **versioned path**, never a bare ``claude`` — that resolves to
the newest installed and defeats the soak gate the target came from. Verify it
came back by ``claude agents`` naming it *and* its version equalling the target
exactly — not merely advanced, and not equal to ``installed``. Then re-apply the
color, because a roll copies the name forward and drops it
(:doc:`fleetupgrade` documents why).

Exit codes
----------

``0`` rolled · ``2`` refused at preflight · ``3`` did not exit · ``4`` did not
come back · ``5`` came back on the wrong version. Anything but ``0`` names the
state it stopped in, because the caller is unattended and an ambiguous exit reads
as success.

What it does not do
-------------------

Pick the session. Decide target policy. Consult the soak or lag gates. Write to
``autoroll.log``. Those stay with the caller, so that this is equally usable for
a hand-driven roll.
