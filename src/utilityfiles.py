"""The files a map has by convention rather than by reference.

Nothing in a BSP points at its own soundscape script, its navigation mesh,
or its overview image. The engine finds them by name -- ``scripts/
soundscapes_<mapname>.txt``, ``maps/<mapname>.nav`` -- so a packer has to go
looking in the same places.

That makes this the one pass that guesses. Every path here is speculative:
most maps have none of these files, and their absence is normal rather than
a problem worth reporting.

Two of them can be renamed on the way in. A navigation mesh packed as
``maps/embed.nav`` loads whatever the map file is called afterwards, which
matters for a map that gets renamed between versions; a particle manifest
packed as ``particles.txt`` does the same. Both are opt-in, because both
change behaviour the mapper may be relying on.
"""

import fnmatch
import os

import graph

#: Where a renamed navigation mesh goes.
EMBED_NAV = 'maps/embed.nav'

#: Where a renamed particle manifest goes.
RENAMED_MANIFEST = 'particles.txt'

#: Map-name-shaped files that are not language files, and would otherwise
#: be swept up by the language file pattern.
NOT_LANGUAGE = ('_particles', '_level_sounds')


def probe(index, mapname, rename_nav=False, rename_particle_manifest=False):
    """Look for the sidecar files a map conventionally has.

    :param index: the resolver, used to see what exists.
    :type index: content.ContentIndex
    :param mapname: the map's name without extension.
    :type mapname: str
    :returns: (packed path, internal path, kind, origin) for each file that
        exists. The two paths differ only where a rename was asked for.
    :rtype: list
    """
    found = []

    def take(path, kind, origin, internal=None):
        if index.find_loose(path) is None:
            return False
        found.append((path, internal or path, kind, origin))
        return True

    # The soundscape script. Two spellings, and only one is ever present.
    if not take('scripts/soundscapes_{}.txt'.format(mapname),
                graph.KIND_SCRIPT, 'soundscape script'):
        take('scripts/soundscapes_{}.vsc'.format(mapname),
             graph.KIND_SCRIPT, 'soundscape script')

    # Per-map sound overrides. Mann-vs-Machine maps read theirs from a
    # fixed path instead of the map-named one, so it is packed under that
    # name or the engine never looks at it.
    level_sounds = 'maps/{}_level_sounds.txt'.format(mapname)
    if 'mvm' in mapname.lower():
        take(level_sounds, graph.KIND_SCRIPT, 'level sounds',
             internal='scripts/mvm_level_sound_tweaks.txt')
    else:
        take(level_sounds, graph.KIND_SCRIPT, 'level sounds')

    nav = 'maps/{}.nav'.format(mapname)
    take(nav, graph.KIND_MISC, 'navigation mesh',
         internal=EMBED_NAV if rename_nav else None)

    take('resource/roundinfo/{}.res'.format(mapname),
         graph.KIND_RESOURCE, 'round info panel')

    take('materials/overviews/{}.vmt'.format(mapname),
         graph.KIND_MATERIAL, 'overview material')

    take('resource/overviews/{}.txt'.format(mapname),
         graph.KIND_SCRIPT, 'overview definition')

    for path in _manifests(index, mapname):
        take(path, graph.KIND_SCRIPT, 'particle manifest',
             internal=('maps/' + RENAMED_MANIFEST
                       if rename_particle_manifest else None))

    for path in _language_files(index, mapname):
        take(path, graph.KIND_SCRIPT, 'language file')

    return found


def _manifests(index, mapname):
    """The particle manifests a map might have.

    Usually ``maps/<mapname>_particles.txt``, but the name has varied and
    some tools write a numbered suffix.
    """
    return _matching(index, 'maps', '{}_particles*.txt'.format(mapname))


def _language_files(index, mapname):
    """Per-map localisation files, which share the map's name."""
    found = []
    for path in _matching(index, 'maps', '{}*.txt'.format(mapname)):
        name = os.path.basename(path).lower()
        if any(marker in name for marker in NOT_LANGUAGE):
            continue
        found.append(path)
    return found


def _matching(index, directory, pattern):
    """Every file matching *pattern* in *directory*, across all content.

    Merged rather than first-hit, because a map's localisation may be split
    between a custom folder and the game's.
    """
    found = []
    seen = set()

    for root in index.directories:
        folder = os.path.join(root, directory.replace('/', os.sep))
        if not os.path.isdir(folder):
            continue

        try:
            names = os.listdir(folder)
        except OSError:
            continue

        for name in names:
            if not fnmatch.fnmatch(name.lower(), pattern.lower()):
                continue
            internal = '{}/{}'.format(directory, name).lower()
            if internal in seen:
                continue
            seen.add(internal)
            found.append(internal)

    return sorted(found)
