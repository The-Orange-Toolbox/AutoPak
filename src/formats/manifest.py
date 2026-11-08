r""".. Particle manifests

A map lists the particle files it needs in
``maps/<mapname>_particles.txt``:

.. code-block:: none

    particles_manifest
    {
        "file"  "!particles/my_effects.pcf"
    }

The leading ``!`` means "precache this at map load". It is part of the
directive, not of the filename, so it comes off.

Without the manifest the engine never loads the map's custom particles at
all, which makes the manifest itself one of the more important things to
pack -- and one of the easiest to forget, because nothing in the map's
entities points at it.
"""

import paths

from formats import kv1


def files(text):
    """The particle files a manifest names.

    :param text: the contents of the manifest.
    :type text: str
    :returns: internal paths.
    :rtype: list
    """
    root = kv1.parse(text)

    found = []
    for _, value in root.find_all(['file']):
        name = str(value).strip().lstrip('!').strip()
        if not name:
            continue
        found.append(paths.internal_path(name).lower())

    return _unique(found)


def dependencies(path):
    """Read a manifest off disk.

    :rtype: list
    """
    root = kv1.load(path)
    if root is None:
        return []

    found = []
    for _, value in root.find_all(['file']):
        name = str(value).strip().lstrip('!').strip()
        if name:
            found.append(paths.internal_path(name).lower())

    return _unique(found)


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
