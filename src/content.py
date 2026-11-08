"""Deciding where an asset lives, and therefore what to do about it.

This is the one module that looks for a file, and the four answers it can
give are the whole behaviour of the tool:

``PACKED``
    Found as a loose file. It is the mapper's own content, so it goes in the
    list.
``STOCK``
    Not loose, but a VPK has it. It belongs to the base game, which every
    player already has, so it is skipped -- and, just as importantly, it is
    not reported missing. Recursion stops here: a stock material's textures
    are stock too, so there is nothing further to find.
``EMBEDDED``
    Not loose, not in a VPK, but already inside the map's own pakfile. vbsp
    generates water and cubemap materials straight into the map, and calling
    those missing would be a lie.
``MISSING``
    Nowhere. This is what the user came for.

VPKs are consulted only to tell STOCK from MISSING. Their contents are never
read and never packed.
"""

import os

PACKED = 'packed'
STOCK = 'stock'
EMBEDDED = 'embedded'
MISSING = 'missing'

#: Sound values that name a soundscript entry rather than a file. Classified
#: by :mod:`entities` before they ever reach the resolver, but the status
#: lives here with its siblings so a summary can list them all together.
SCRIPTED = 'scripted'


class ContentIndex(object):
    """Where to look for an asset, and what it means when it is not there."""

    def __init__(self, directories=None, vpks=None, pakfile=None):
        """
        :param directories: loose content roots, in search order.
        :type directories: list of str
        :param vpks: the VPK index, or None to treat every VPK as absent.
        :type vpks: vpk.VpkIndex
        :param pakfile: paths already inside the map's own pakfile.
        :type pakfile: set
        """
        self.directories = list(directories or ())
        self.vpks = vpks
        self.pakfile = set(p.lower() for p in (pakfile or ()))

        #: :type: (list) - internal paths found loose that a VPK also has.
        #: Usually a deliberate override; occasionally a decompiled stock
        #: asset quietly adding megabytes to everyone's download.
        self.shadowed = []

        self._cache = {}

    def find_loose(self, internal_path):
        """The first loose file matching *internal_path*.

        First hit wins, in search-path order, which is the same precedence
        the engine applies -- so a map's own custom folder beats the game's.

        :returns: an absolute path, or None.
        :rtype: str or None
        """
        relative = internal_path.replace('/', os.sep)
        for directory in self.directories:
            candidate = os.path.join(directory, relative)
            if os.path.isfile(candidate):
                return candidate
        return None

    def in_vpk(self, internal_path):
        """Whether any mounted VPK holds *internal_path*.

        :rtype: bool
        """
        if self.vpks is None:
            return False
        return internal_path in self.vpks

    def resolve(self, internal_path):
        """Work out what AutoPak should do about *internal_path*.

        :param internal_path: a normalised, forward-slashed engine path.
        :type internal_path: str
        :returns: (status, external_path, shadowed). The external path is
            set only for PACKED. *shadowed* is True when a loose file was
            packed even though a VPK also has it.
        :rtype: tuple
        """
        key = internal_path.lower()
        if key in self._cache:
            return self._cache[key]

        result = self._resolve(key)
        self._cache[key] = result
        return result

    def _resolve(self, key):
        loose = self.find_loose(key)
        in_vpk = self.in_vpk(key)

        if loose is not None:
            if in_vpk:
                self.shadowed.append(key)
                return (PACKED, loose, True)
            return (PACKED, loose, False)

        if in_vpk:
            return (STOCK, None, False)

        if key in self.pakfile:
            return (EMBEDDED, None, False)

        return (MISSING, None, False)

    def internal_path_for(self, external_path):
        """Work out what an external file would be called inside the map.

        Used for ``--include``, where the user names a file on disk and
        AutoPak has to decide what the engine would call it. The longest
        matching content root wins, so a file under ``tf/custom/mine`` is
        ``materials/...`` and not ``custom/mine/materials/...``.

        :returns: the internal path, or None if the file lies under none of
            the content roots -- in which case the engine could not load it
            either, and the caller should say so rather than guess.
        :rtype: str or None
        """
        full = os.path.abspath(external_path)
        best = None

        for directory in self.directories:
            root = os.path.abspath(directory)
            try:
                relative = os.path.relpath(full, root)
            except ValueError:  # different drives
                continue
            if relative.startswith(os.pardir):
                continue
            if best is None or len(relative) < len(best):
                best = relative

        if best is None:
            return None
        return best.replace(os.sep, '/').lower()


def build(directories=None, vpk_paths=None, pakfile=None, use_vpk=True):
    """Assemble a :class:`ContentIndex` and read the VPK directories.

    :param use_vpk: when False the VPKs are not opened at all, so anything
        not found loose is reported missing rather than recognised as
        base-game content.
    :type use_vpk: bool
    :returns: (index, failures) where failures is a list of
        (vpk path, reason) for archives that could not be read.
    :rtype: tuple
    """
    import vpk as vpk_module

    vpks = None
    failures = []
    if use_vpk:
        vpks = vpk_module.index(vpk_paths or ())
        failures = vpks.failures

    return ContentIndex(directories=directories, vpks=vpks,
                        pakfile=pakfile), failures
