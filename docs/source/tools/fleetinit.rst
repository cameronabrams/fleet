fleetinit
=========

.. tooldoc:: fleetinit

Usage
-----

.. code-block:: text

   fleetinit                      show the plan; change nothing (the default)
   fleetinit --go                 create <config>/, <config>/briefs/ and fleet.toml
   fleetinit --from PATH --go     take the shareable parts of an existing config
   fleetinit --save-profile PATH  write those parts out, and stop

Options: ``--name``, ``--timezone``, ``--fleet`` answer the prompts
non-interactively; ``--keep`` takes the source's own answers and asks nothing.

Why it comes first
------------------

On a fresh machine nothing else can run: :doc:`../index` installs through
``install``, which exits 2 without a ``fleet.toml``. So this is the step that
blocks every other step, and it was built before the conveniences for that reason
rather than because it was the smallest.

Where the defaults come from
----------------------------

**This repository ships the schema and the questions, never the answers.** A name,
a cluster, an ssh host and an account code belong to a person and a site, and the
application may not contain them. So a new configuration gets its defaults one of
two ways:

``--from <an existing fleet.toml>``
   copies the parts that are about *how someone likes fleets to work* — ``[human]``,
   ``[paths]``, ``[spawn]``, ``[context]``, ``[notify]``, ``[mail]`` and every
   ``[cluster.*]`` — and leaves behind the parts that are about *one particular
   fleet*.

the prompts
   asked when a value is missing and there is a terminal to ask at. With no
   terminal they fall back silently, so a scripted run is not left waiting.

The fresh-machine path is therefore: clone this repository, fetch your own
configuration from wherever you keep it, ``fleetinit --from <it> --go``. With
nothing personal to hand, the prompts and the shipped example still produce a
working configuration.

``--save-profile`` writes the shareable subset of a configuration to a path of
your choosing and stops, so the thing worth carrying can be kept somewhere
separate from the fleet it came from.

What travels, and what does not
-------------------------------

Three kinds of content, measured on a live 313-line configuration: 99 lines of
preferences and cluster schema that travel, 47 lines of roster, and 143 lines of
history.

.. list-table::
   :widths: 24 16 60
   :header-rows: 1

   * - section
     - what happens
     - why
   * - ``[human]`` ``[paths]`` ``[spawn]`` ``[context]`` ``[notify]`` ``[mail]``
       ``[cluster.*]``
     - copied
     - how a person likes fleets to work, and the site they work at
   * - ``[colors]`` ``[owners]``
     - **emptied**
     - every fleet *has* a roster; these are per-fleet in their contents, not in
       their existence
   * - ``[parked.*]`` ``[retired.*]``
     - dropped
     - history a new fleet has none of, naming transcripts that are not on the
       new disk
   * - ``[authority]``
     - dropped
     - a statement about one grant to one set of sessions
   * - ``[updates]``
     - dropped
     - names a host

The roster is **emptied rather than deleted**, and that distinction was found by
running the whole path rather than by a test: deleting the header left a
configuration that ``fleetspawn --color`` then refused to add to — correctly,
since it will not guess where a missing section belongs.

Copied as text, not re-emitted
------------------------------

There is no comment-preserving TOML writer in the standard library and this
package may not add a dependency, so the source is copied **as text** and whole
sections are removed by line. The comments are the reason a configuration is worth
reading — they say why each value is what it is — and a parse-and-re-emit would
drop every one of them.

A comment paragraph directly above an *emptied* header stays, because a fresh
fleet needs that explanation more than an established one does. One above a
*dropped* header goes with it, since prose explaining a section that is no longer
there is worse than keeping both or dropping both.

The result is parsed before it replaces anything, and an existing ``fleet.toml``
is never overwritten: one that is already there is somebody's work.
