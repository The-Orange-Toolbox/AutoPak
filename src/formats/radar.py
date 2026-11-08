r""".. Overview files - the radar image a map shows

``resource/overviews/<mapname>.txt`` names the material drawn as the map's
overview, and multi-level maps add a ``verticalsections`` block with one
image per floor:

.. code-block:: none

    "mymap"
    {
        "material"  "overviews/mymap_radar"
        "verticalsections"
        {
            "default"   { "AltitudeMax" "10000" }
            "lower"     { "AltitudeMax" "100" }
        }
    }

The ``_radar`` suffix is stripped and reapplied per section, which looks
redundant but is not: the base name is what the section images are built
from, and the file on disk for the default level keeps the suffix.
"""

import paths

from formats import kv1


def images(text):
    """The overview materials and radar images a map declares.

    :param text: the contents of the overview file.
    :type text: str
    :returns: (materials, radar images) -- both lists of internal paths.
    :rtype: tuple
    """
    root = kv1.parse(text)

    materials = []
    radars = []

    for _, value in root.find_all(['material']):
        stem = paths.vmt_path(value)
        if not stem:
            continue

        materials.append('materials/{}.vmt'.format(stem).lower())

        base = 'resource/' + stem.lower()
        if base.endswith('_radar'):
            base = base[:-len('_radar')]

        radars.append(base + '_radar.dds')

        for section in _sections(root):
            radars.append('{}_{}_radar.dds'.format(base, section.lower()))

    return _unique(materials), _unique(radars)


def _sections(root):
    """The names of a multi-level map's floors."""
    found = []
    for _, value in root.pairs:
        if not isinstance(value, kv1.Node):
            continue
        block = value.first_block('verticalsections')
        if block is None:
            continue
        for name, nested in block.pairs:
            if isinstance(nested, kv1.Node) and name:
                found.append(name)
    return found


def dependencies(path):
    """Read an overview file off disk.

    :rtype: tuple
    """
    try:
        with open(path, 'r', encoding='latin-1', errors='replace') as handle:
            return images(handle.read())
    except (IOError, OSError):
        return [], []


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
