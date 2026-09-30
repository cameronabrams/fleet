"""Whose transcript is this? One answer, shared by fleetlog and fleetgantt.

A name is not an identity; a transcript is. Names are reused (an old name can later
belong to a different session) and renamed (a session carries its name into a later
transcript and changes it there). So a transcript is identified, in order, by:

  1. its OWN last name record, if that is a current role;
  2. the rename table, if its own last name is retired -- built from every
     transcript's name sequence, it records what a retired name became;
  3. the current owner of its directory;
  4. its own name as written.

Rule 2 is never applied over rule 1. OBSERVED 2026-09-14: applying the table to a
transcript's FIRST name reported the original coordinator transcript (named `coord`
throughout) as another session that had later carried one of its old names.
"""
import re

SELF_RE = re.compile(r"This session is (\S+) \[[0-9a-f]{6}\]")
AGENT_RE = re.compile(r'"agentName"\s*:\s*"([^"]+)"')

def names_in_line(line):
    """Names a raw transcript line self-reports, in order."""
    out = [m.group(1) for m in SELF_RE.finditer(line)] if "This session is " in line else []
    if '"agent-name"' in line:
        out += AGENT_RE.findall(line)
    return out

def rename_map(sequences, current, dir_owner):
    """Retired name -> current role.

    `sequences` is [(project_dir_name, [names in file order])], NEWEST transcript
    first, so the freshest evidence wins. A transcript whose last name is current
    maps its earlier names to it (lineage); otherwise they map to the current owner
    of its directory. A current name is never remapped."""
    out = {}
    for project, seq in sequences:
        if not seq:
            continue
        target = seq[-1] if seq[-1] in current else dir_owner.get(project)
        if not target:
            continue
        for n in seq:
            if n not in current:
                out.setdefault(n, target)
    return out

def attribute(own_name, project, current, renames, dir_owner, place_named=True,
              own_seq=None):
    """(identity, how, inferred) for a transcript whose own last name is `own_name`
    (None if it recorded none). `inferred` is True unless the transcript named
    itself as that role.

    place_named=False keeps a transcript that recorded a name which is neither a
    role nor a known rename (a remote-session title, a one-off) out of its
    directory owner's lane: it has said who it is, and it is not that role. The
    message graph still needs a node for it, so fleetlog places it; the chart
    shows it apart.

    `own_seq` is THIS transcript's own name record, and gates the rename branch.
    `renames` is keyed by bare name across every transcript, and auto-generated
    display names (`<project>-<short id>`) are not unique: on 2026-09-22 a session
    started by hand for one task, which recorded only the auto name it happened to
    be given, inherited a real role's lineage and was drawn inside that role's lane
    as "renamed: X became Y". It was never renamed and was never that role.
    A rename is ONE transcript's history; applying it to another is a guess, and
    this one was stated as a fact. Pass `own_seq` wherever the answer is shown as
    an identity. Omitted, the cross-transcript lineage still applies -- fleetlog
    wants it for the message graph, where there is no lane to mislabel."""
    if own_name and (current is None or own_name in current):
        return own_name, "own name record", False
    if own_name and own_name in renames:
        target = renames[own_name]
        # Corroborated: THIS transcript recorded both names, so it really was
        # renamed. Uncorroborated: the mapping comes from another transcript's
        # record -- which is often right (a session resumed elsewhere and renamed
        # there; its old transcript is that session's earlier life) and sometimes
        # wrong (a different session that merely ended up with the same
        # auto-generated display name). The two are indistinguishable from the
        # data, so the answer is kept and the CLAIM is not.
        if own_seq is None or target in own_seq:
            return target, f"renamed: {own_name!r} became {target!r}", True
        if place_named:
            return target, f"{own_name!r} -> {target!r}, from another transcript", True
        # place_named=False: a caller that treats the answer as an identity -- a
        # lane on a chart -- shows it apart rather than binding it to the role.
    owner = dir_owner.get(project) if (place_named or not own_name) else None
    if owner:
        why = f"named {own_name!r}; " if own_name else "no name recorded; "
        return owner, why + "placed by its directory", True
    if own_name:
        return own_name, "own name record (not a current role)", False
    return None, "no name recorded", True
