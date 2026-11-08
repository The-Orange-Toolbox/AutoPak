"""Turning what a file says into a path the engine would look up.

Source content is written by hand, by Hammer, by half a dozen exporters and
by vbsp, and they disagree about almost everything: slash direction, leading
and trailing whitespace, whether a material reference carries the
``materials/`` prefix, whether it carries the ``.vmt`` suffix, and how many
consecutive slashes is a reasonable number. The engine is forgiving about
all of it. A packer has to be forgiving in exactly the same way, or it looks
for a file under a name nothing on disk has and reports content missing that
is sitting right there.

These rules are ported from CompilePal, which worked them out against the
real corpus. They look arbitrary because they are: each one is some
exporter's habit.
"""

import re

#: Characters Source uses to prefix a sound name in a precache: ``*`` for
#: streamed, ``#`` to bypass the soundscript system, ``^`` for a
#: distance-attenuated one, and so on. They are part of the reference, not
#: part of the filename.
SOUND_PREFIXES = '*#@><^()}$!? '

#: vbsp renames blend materials used on non-displacement brushes, writing a
#: generated patch material into ``materials/maps/<map>/`` instead. The
#: generated one is already in the map's pakfile; what has to be packed is
#: the original the mapper made.
WVT_PATCH = re.compile(r'^materials/maps/[^/]+/(.+)_wvt_patch\.vmt$',
                       re.IGNORECASE)

_MULTI_SLASH = re.compile(r'/+')
_PARENT_SEGMENT = re.compile(r'/.*/\.\.')


def internal_path(value):
    """Normalise an engine-relative path to the form used as a key.

    Backslashes become forward slashes, and a ``..`` segment is collapsed
    against what precedes it -- ``materials/vgui/../hud/x.vmt`` is
    ``materials/hud/x.vmt``, and both spellings have to land on one entry
    or the same bytes get packed twice under two names.

    :param value: a path as some file spelled it.
    :type value: str
    :returns: the normalised path, forward-slashed.
    :rtype: str
    """
    path = str(value).replace('\\', '/')
    return _PARENT_SEGMENT.sub('', path)


def vmt_path(value):
    """Normalise a material or texture reference to a bare stem.

    Strips the ``materials/`` prefix and the ``.vmt``/``.vtf`` suffix, so
    that everything downstream can add back whichever one it means. A VMT
    naming ``$basetexture "metal/wall"`` and one naming
    ``$basetexture "materials\\metal\\wall.vtf"`` are the same texture.

    :param value: the value of a material or texture key.
    :type value: str
    :returns: the stem, with no prefix, suffix, or leading slash.
    :rtype: str
    """
    path = str(value).strip(' /\\')
    path = path.replace('\\', '/')
    path = _MULTI_SLASH.sub('/', path)

    if path.lower().startswith('materials/'):
        path = path[len('materials/'):]
    if path.lower().endswith(('.vmt', '.vtf')):
        path = path[:-4]

    return path


def sound_path(value):
    """Turn a sound reference into a path under ``sound/``.

    :param value: the value of a sound key, precache prefixes and all.
    :type value: str
    :returns: the path the file would have, forward-slashed.
    :rtype: str
    """
    clip = str(value).strip(SOUND_PREFIXES)
    return internal_path('sound/' + clip)


def unpatch_wvt(path):
    """Map a vbsp-generated blend patch back to the material it patches.

    :param path: an internal material path.
    :type path: str
    :returns: the original material's path, or *path* unchanged when it is
        not a generated patch.
    :rtype: str
    """
    match = WVT_PATCH.match(path)
    if match is None:
        return path
    return 'materials/' + match.group(1) + '.vmt'


def replace_extension(path, extension):
    """Swap a path's extension, the way a model's siblings are named.

    ``x.mdl`` with ``.dx90.vtx`` is ``x.dx90.vtx`` -- the extension is
    replaced, not appended, which is why this is not just concatenation.

    :param path: the path to rewrite.
    :type path: str
    :param extension: the new extension, leading dot included.
    :type extension: str
    :rtype: str
    """
    cut = path.rfind('.')
    slash = path.rfind('/')
    if cut > slash:
        path = path[:cut]
    return path + extension
