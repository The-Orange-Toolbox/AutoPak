r""".. VBSP - detail sprite definitions

Worldspawn's ``detailvbsp`` names one of these, and it describes the grass,
pebbles and litter vbsp scatters across displacement surfaces:

.. code-block:: none

    detail.vbsp
    {
        "grass"
        {
            "density"   "1000"
            "grassA"
            {
                "sprite"    "0 0 256 256 512"
                "model"     "models/props_foliage/grass.mdl"
            }
        }
    }

Most entries are regions of the sheet named by worldspawn's
``detailmaterial``, so they need nothing packed of their own. Some name a
model instead, and those do.
"""

import paths

from formats import kv1


def references(text):
    """The materials and models a detail sprite definition names.

    :param text: the contents of a ``.vbsp``.
    :type text: str
    :returns: (materials, models) -- both lists of internal paths.
    :rtype: tuple
    """
    root = kv1.parse(text)

    materials = []
    for _, value in root.find_all(['material']):
        stem = paths.vmt_path(value)
        if stem:
            materials.append('materials/{}.vmt'.format(stem).lower())

    models = []
    for _, value in root.find_all(['model']):
        name = paths.internal_path(str(value)).lower().strip()
        # 'sprite' entries carry sheet coordinates under nearby keys; only
        # something that looks like a model path is one.
        if name.endswith('.mdl'):
            models.append(name)

    return _unique(materials), _unique(models)


def dependencies(path):
    """Read a detail sprite definition off disk.

    :rtype: tuple
    """
    try:
        with open(path, 'r', encoding='latin-1', errors='replace') as handle:
            return references(handle.read())
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
