r""".. PHY - collision models, and the gibs they break into

A ``.phy`` is mostly binary collision data, but it ends with a KeyValues
text blob describing how the object behaves -- including, for anything
breakable, the models it turns into:

.. code-block:: none

    break
    {
        "model" "props_debris/wood_board01a"
        "health" "10"
    }

Nothing else in the map names those. A crate whose gibs are not packed
breaks into ERROR signs, and the mapper never sees it because their own
install has the models.

Finding where the text starts is done properly, by stepping over the
collision solids the header counts. The tempting shortcuts both fail on real
files: searching forwards for the first identifier-then-brace matches inside
packed floats often enough to matter, and scanning backwards for printable
bytes picks up whichever trailing float bytes happen to look like text and
glues them to the first key. Either way the failure is silent and costs a
gib, which is exactly the kind of thing nobody notices until a crate breaks
into ERROR signs on someone else's machine.

A file whose header does not make sense still gets the backward scan, since
a guess is better than giving up.
"""

import struct

import paths

from formats import kv1

#: ``phyheader_t``: its own size, an id, how many solids follow, a checksum.
_HEADER = '<iiii'
_HEADER_SIZE = 16

#: No real collision model has this many parts; a larger count means the
#: header is not one.
_MAX_SOLIDS = 1024

#: Bytes that can appear in the text blob: printable ASCII plus the
#: whitespace a keyvalues file uses.
_TEXT_BYTES = frozenset(list(range(32, 127)) + [9, 10, 13])


def _after_solids(data):
    """Where the collision data ends, by stepping over each solid.

    :returns: an offset, or None if the header does not describe a ``.phy``.
    :rtype: int or None
    """
    if len(data) < _HEADER_SIZE:
        return None

    header_size, _, solid_count, _ = struct.unpack_from(_HEADER, data, 0)

    if header_size < _HEADER_SIZE or header_size > len(data):
        return None
    if solid_count < 0 or solid_count > _MAX_SOLIDS:
        return None

    offset = header_size
    for _ in range(solid_count):
        if offset + 4 > len(data):
            return None
        # Each solid is preceded by the length of its data, not counting
        # the length field itself.
        size = struct.unpack_from('<i', data, offset)[0]
        if size < 0:
            return None
        offset += 4 + size
        if offset > len(data):
            return None

    return offset


def _trailing_text(data):
    """The last run of bytes that could be text.

    The fallback for a file whose header will not parse. It can pick up a
    stray byte of collision data, so it is only used when the structural
    answer is unavailable.
    """
    end = len(data)
    while end and data[end - 1] in (0, 10, 13, 32, 9):
        end -= 1

    start = end
    while start > 0 and data[start - 1] in _TEXT_BYTES:
        start -= 1

    return start, end


def text_blob(data):
    """The keyvalues text at the end of a collision model.

    :param data: the contents of a ``.phy``.
    :type data: bytes
    :returns: the text, or '' if there is none.
    :rtype: str
    """
    start = _after_solids(data)
    end = len(data)

    if start is None:
        start, end = _trailing_text(data)

    if start >= end:
        return ''

    text = data[start:end].decode('latin-1', 'replace')
    return text.split('\x00', 1)[0]


def gibs(data):
    """The models a collision model breaks into.

    :param data: the contents of a ``.phy``.
    :type data: bytes
    :returns: internal model paths.
    :rtype: list
    """
    text = text_blob(data)
    if not text:
        return []

    root = kv1.parse(text)

    found = []
    for block in _blocks_named(root, 'break'):
        for key in ('model', 'ragdoll'):
            for _, value in block.find_all([key]):
                name = paths.internal_path(str(value)).lower().strip()
                if not name:
                    continue
                if not name.endswith('.mdl'):
                    name += '.mdl'
                if not name.startswith('models/'):
                    name = 'models/' + name
                found.append(name)

    return _unique(found)


def _blocks_named(node, name, depth=0):
    """Every block called *name*, at any depth.

    A ``.phy`` wraps its sections differently depending on which exporter
    wrote it, so the search cannot assume a level.
    """
    if depth > 8:
        return

    lowered = name.lower()
    for key, value in node.pairs:
        if not isinstance(value, kv1.Node):
            continue
        if key.lower() == lowered:
            yield value
        for nested in _blocks_named(value, name, depth + 1):
            yield nested


def dependencies(path):
    """Read a collision model off disk and report its gibs.

    :param path: an absolute path to a ``.phy``.
    :type path: str
    :rtype: list
    """
    try:
        with open(path, 'rb') as handle:
            data = handle.read()
    except (IOError, OSError):
        return []

    return gibs(data)


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
