r""".. RES - vgui layouts

A ``.res`` describes a panel: where its elements sit, and which images they
draw. The images are what a packer wants:

.. code-block:: none

    "Resource/UI/RoundInfo.res"
    {
        "MapImage"
        {
            "ControlName"   "ImagePanel"
            "image"         "..\vgui\maps\menu_photos_mymap"
        }
    }

Those paths are written relative to ``materials/vgui/`` and habitually use
``..`` to climb back out of it, which is why they go through the normal
path normalisation rather than being concatenated.

``#base`` directives are surfaced for the caller to resolve, since finding
the referenced file needs search paths this module does not have.
"""

import paths

from formats import kv1

#: Where a .res image path is relative to.
IMAGE_ROOT = 'materials/vgui/'


def images(text):
    """The materials a vgui layout draws.

    :param text: the contents of a ``.res``.
    :type text: str
    :returns: (materials, base files) -- the second needing search paths to
        resolve, so it is left to the caller.
    :rtype: tuple
    """
    root = kv1.parse(text)

    found = []
    for _, value in root.find_all(['image']):
        stem = str(value).strip()
        if not stem:
            continue

        stem = paths.vmt_path(stem)
        if not stem:
            continue

        # Most values are relative to materials/vgui/, and habitually climb
        # out of it with '..' -- '../hud/icon' is the commonest spelling in
        # the game's own files. A few name the folder outright instead, and
        # prefixing those again would look for materials/vgui/vgui/...
        if stem.lower().startswith('vgui/'):
            internal = paths.internal_path('materials/' + stem)
        else:
            internal = paths.internal_path(IMAGE_ROOT + stem)

        internal = internal.lower()
        if not internal.endswith('.vmt'):
            internal += '.vmt'
        found.append(internal)

    bases = [paths.internal_path(b).lower() for b in root.bases if b]

    return _unique(found), _unique(bases)


def dependencies(path):
    """Read a vgui layout off disk.

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
