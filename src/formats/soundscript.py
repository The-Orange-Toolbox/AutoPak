r""".. Soundscripts and soundscapes

Both formats wrap their audio in the same way -- a ``wave`` key naming a
file, sometimes inside an ``rndwave`` block that picks one at random:

.. code-block:: none

    Ambient.Wind
    {
        "channel"   "CHAN_STATIC"
        "rndwave"
        {
            "wave"  "ambient/wind/wind1.wav"
            "wave"  "ambient/wind/wind2.wav"
        }
    }

This is read line by line rather than through the keyvalues reader, and
deliberately so. Soundscripts are edited by hand more than any other format
in Source and unbalanced braces in them are routine; a structural parse of a
file that ends one brace short loses every sound below the mistake, while a
line scan loses none of them. ``rndwave`` needs no special handling for the
same reason -- its inner lines start with ``wave`` like any other.
"""

import paths


def waves(text):
    """Every sound file a soundscript or soundscape names.

    :param text: the contents of the file.
    :type text: str
    :returns: internal paths under ``sound/``.
    :rtype: list
    """
    found = []

    for line in text.splitlines():
        cleaned = line.replace('\t', ' ').replace('"', ' ').strip()
        if not cleaned:
            continue

        # 'wave' as a whole word, not 'wavelength' or a targetname that
        # happens to start with it.
        parts = cleaned.split(None, 1)
        if len(parts) != 2 or parts[0].lower() != 'wave':
            continue

        clip = parts[1].strip()
        if not clip:
            continue

        found.append(paths.sound_path(clip))

    return _unique(found)


def dependencies(path):
    """Read a soundscript off disk.

    :rtype: list
    """
    try:
        with open(path, 'r', encoding='latin-1', errors='replace') as handle:
            return waves(handle.read())
    except (IOError, OSError):
        return []


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
