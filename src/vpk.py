"""Reading the file *names* out of a VPK, and nothing else.

AutoPak opens a VPK for exactly one reason: to answer "does the base game
already have this?". An asset that is only in a VPK belongs to the game, so
it is not packed and -- crucially -- it is not reported missing either.

So this reader stops at the directory tree. It never touches the numbered
archive files that hold the actual bytes, never decompresses anything, and
has no way to extract a file even by accident. That is a deliberate
constraint, not an unfinished feature: VPK content must never end up inside
a map's pakfile.

The directory is three nested loops of nul-terminated strings -- extension,
then path, then filename -- each level ending with an empty string. A file's
engine path is ``<path>/<filename>.<extension>``, with a lone space standing
in for "no path" or "no extension".
"""

import os
import struct

#: 0x55AA1234, little-endian, at the front of every VPK.
SIGNATURE = 0x55AA1234

#: Only versions 1 and 2 exist. They differ in header length only, which is
#: all this reader cares about; the tree that follows is identical.
HEADER_SIZES = {1: 12, 2: 28}


class VpkError(Exception):
    """A file that does not look like a VPK directory."""


def _read_cstring(data, offset):
    """Read a nul-terminated latin-1 string.

    :returns: (text, offset just past the terminator)
    """
    end = data.find(b'\x00', offset)
    if end < 0:
        raise VpkError('unterminated string in directory tree')
    return data[offset:end].decode('latin-1'), end + 1


def read_paths(path):
    """Every engine-relative file path a VPK contains.

    :param path: the ``_dir.vpk`` to read.
    :type path: str
    :returns: lowercase, forward-slashed paths.
    :rtype: set
    :raises VpkError: when the file is not a readable VPK directory.
    """
    try:
        with open(path, 'rb') as handle:
            head = handle.read(12)
            if len(head) < 12:
                raise VpkError('too short to be a vpk: ' + path)

            signature, version, tree_size = struct.unpack('<III', head)
            if signature != SIGNATURE:
                raise VpkError('not a vpk: ' + path)
            if version not in HEADER_SIZES:
                raise VpkError(
                    'unsupported vpk version {} in {}'.format(version, path))

            handle.seek(HEADER_SIZES[version])
            tree = handle.read(tree_size)
    except (IOError, OSError) as error:
        raise VpkError('cannot read {}: {}'.format(path, error))

    return _read_tree(tree)


def _read_tree(tree):
    """Walk the three nested loops of the directory tree."""
    paths = set()
    offset = 0
    size = len(tree)

    while offset < size:
        extension, offset = _read_cstring(tree, offset)
        if not extension:
            break

        while offset < size:
            directory, offset = _read_cstring(tree, offset)
            if not directory:
                break

            while offset < size:
                name, offset = _read_cstring(tree, offset)
                if not name:
                    break

                # VPKDirectoryEntry: crc, preload length, archive index,
                # offset, length, terminator. Only the preload length
                # matters here, because those bytes sit inline in the tree
                # and have to be stepped over to reach the next name.
                if offset + 18 > size:
                    raise VpkError('directory entry runs past the tree')
                preload = struct.unpack_from('<H', tree, offset + 4)[0]
                offset += 18 + preload

                paths.add(_join(directory, name, extension))

    return paths


def _join(directory, name, extension):
    """Assemble one entry's engine path.

    A lone space is how a VPK spells "the root folder" and "no extension".
    """
    if extension != ' ':
        name = name + '.' + extension
    if directory == ' ':
        return name.lower()
    return (directory + '/' + name).replace('\\', '/').lower()


class VpkIndex(object):
    """The combined contents of several VPKs, for existence tests only."""

    def __init__(self):
        #: :type: (set) - every path across every VPK read in.
        self.paths = set()
        #: :type: (list) - the VPKs that were read, in order.
        self.sources = []
        #: :type: (list) - (path, reason) for VPKs that could not be read.
        self.failures = []

    def add(self, path):
        """Read one VPK into the index.

        A VPK that will not parse is recorded and skipped rather than
        raised: a single unreadable archive should cost one warning, not
        the whole run.

        :returns: True if it was read.
        :rtype: bool
        """
        try:
            self.paths |= read_paths(path)
        except VpkError as error:
            self.failures.append((path, str(error)))
            return False

        self.sources.append(path)
        return True

    def __contains__(self, internal_path):
        return internal_path.replace('\\', '/').lower() in self.paths

    def __len__(self):
        return len(self.paths)


def index(paths):
    """Build a :class:`VpkIndex` from several VPK files.

    :param paths: ``_dir.vpk`` paths, in search order.
    :type paths: iterable of str
    :rtype: VpkIndex
    """
    built = VpkIndex()
    for path in paths:
        if os.path.isfile(path):
            built.add(path)
    return built
