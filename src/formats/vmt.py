""".. VMT - materials

A material names two kinds of thing: textures, which are leaves, and other
materials, which are not. The second kind is what makes ``Patch`` work --

.. code-block:: none

    "Patch"
    {
        "include" "materials/models/props/base.vmt"
        "replace" { "$basetexture" "models/props/red" }
    }

-- and a chain of those can be several deep in real content, which is why
the crawl has to follow them rather than reading one file and stopping.

Keys are searched at every depth, not just the top level. Texture keys sit
inside ``Proxies`` blocks, inside ``>=DX90`` blocks, and inside ``replace``
and ``insert`` blocks, and all of them are content the map needs.
"""

import keys
import paths

from formats import kv1


def textures(text):
    """Every ``.vtf`` a material references.

    :param text: the contents of a ``.vmt``.
    :type text: str
    :returns: internal paths, lowercase, in file order without repeats.
    :rtype: list
    """
    root = kv1.parse(text)
    found = []

    for key, value in root.find_all(keys.TEXTURE_KEYS):
        stem = paths.vmt_path(value)
        if not stem or keys.is_denied_texture(stem):
            continue

        found.append('materials/{}.vtf'.format(stem).lower())

        # $envmap is the one key that also implies an HDR sibling. The
        # plain one usually exists too, so both are worth trying.
        if key.lower() == keys.HDR_TEXTURE_KEY:
            found.append('materials/{}.hdr.vtf'.format(stem).lower())

    return _unique(found)


def references(text):
    """Every other ``.vmt`` a material references.

    :param text: the contents of a ``.vmt``.
    :type text: str
    :returns: internal paths, lowercase, in file order without repeats.
    :rtype: list
    """
    root = kv1.parse(text)
    found = []

    for _, value in root.find_all(keys.MATERIAL_KEYS):
        stem = paths.vmt_path(value)
        if not stem or keys.is_denied_texture(stem):
            continue
        found.append('materials/{}.vmt'.format(stem).lower())

    return _unique(found)


def dependencies(path):
    """Read a material off disk and report everything it needs.

    :param path: an absolute path to a ``.vmt``.
    :type path: str
    :returns: (textures, materials, truncated). *truncated* is True when
        the file ended mid-block, which the caller turns into a warning.
    :rtype: tuple
    """
    try:
        with open(path, 'r', encoding='latin-1', errors='replace') as handle:
            text = handle.read()
    except (IOError, OSError):
        return [], [], False

    root = kv1.parse(text)
    return textures(text), references(text), root.truncated


def _unique(values):
    """Drop repeats, keeping first-seen order.

    A material naming the same texture for ``$basetexture`` and ``$detail``
    is common, and the crawl should see it once.
    """
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
