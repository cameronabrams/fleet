.. _templates:

Templates
=========

Starting points for configuration, in ``examples/``. Copy them into your
configuration directory and edit; none is read from the repository at runtime.

Brief
-----

Every session needs one, at ``<config>/briefs/<name>.md``. Keep it under a page: the
session re-reads it after every restart.

.. literalinclude:: ../../examples/brief.example.md
   :language: markdown

Conventions
-----------

The working rules every brief points to. Each rule records the failure that earned
it, so a new fleet can judge whether it applies — delete the ones that do not.

.. literalinclude:: ../../examples/conventions.example.md
   :language: markdown

Configuration
-------------

``fleet.toml`` is shown in full, section by section, in :doc:`configuration`.
