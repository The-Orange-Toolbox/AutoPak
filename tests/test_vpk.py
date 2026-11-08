"""Tests for the VPK directory reader.

The reader exists to answer one question -- is this asset part of the base
game? -- so the tests are about names, never bytes. They build VPKs byte by
byte rather than shipping a binary fixture, which keeps the format's shape
visible: three nested loops of nul-terminated strings, each ending with an
empty one.
"""

import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from vpk import SIGNATURE, VpkError, index, read_paths  # noqa: E402


def _split(internal_path):
    """Break a path into the (extension, directory, name) a VPK stores.

    A lone space is how the format spells "root folder" and "no extension".
    """
    directory, _, name = internal_path.rpartition('/')
    stem, dot, extension = name.rpartition('.')
    if not dot:
        stem, extension = name, ' '
    return extension, directory or ' ', stem


def build_vpk(path, internal_paths, version=1, preload=0):
    """Write a real, parseable VPK directory holding *internal_paths*.

    Only the directory is written -- no archive files, no data -- which is
    all the reader ever looks at.
    """
    tree = bytearray()
    grouped = {}
    for internal in internal_paths:
        extension, directory, name = _split(internal)
        grouped.setdefault(extension, {}).setdefault(directory, []).append(name)

    for extension in sorted(grouped):
        tree += extension.encode('latin-1') + b'\x00'
        for directory in sorted(grouped[extension]):
            tree += directory.encode('latin-1') + b'\x00'
            for name in sorted(grouped[extension][directory]):
                tree += name.encode('latin-1') + b'\x00'
                tree += struct.pack('<IHHIIH', 0, preload, 0, 0, 0, 0xFFFF)
                tree += b'\x00' * preload
            tree += b'\x00'          # end of this directory
        tree += b'\x00'              # end of this extension
    tree += b'\x00'                  # end of the tree

    if version == 1:
        header = struct.pack('<III', SIGNATURE, 1, len(tree))
    else:
        header = struct.pack('<IIIIIII', SIGNATURE, 2, len(tree), 0, 0, 0, 0)

    with open(path, 'wb') as handle:
        handle.write(header)
        handle.write(bytes(tree))

    return path


class ReadPathsTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-vpk-')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def vpk(self, paths, **kwargs):
        return build_vpk(os.path.join(self.root, 'test_dir.vpk'), paths,
                         **kwargs)

    def testItReadsAVersionOneDirectory(self):
        path = self.vpk(['materials/metal/wall.vmt',
                         'models/props/barrel.mdl'])

        self.assertEqual(read_paths(path),
                         {'materials/metal/wall.vmt',
                          'models/props/barrel.mdl'})

    def testItReadsAVersionTwoDirectory(self):
        # v2 differs only in header length; the tree is identical.
        path = self.vpk(['materials/metal/wall.vmt'], version=2)

        self.assertEqual(read_paths(path), {'materials/metal/wall.vmt'})

    def testItReassemblesExtensionPathAndName(self):
        path = self.vpk(['sound/ambient/wind/gust01.wav'])

        self.assertEqual(read_paths(path), {'sound/ambient/wind/gust01.wav'})

    def testAFileAtTheRootHasNoDirectory(self):
        path = self.vpk(['readme.txt'])

        self.assertEqual(read_paths(path), {'readme.txt'})

    def testAFileWithNoExtension(self):
        path = self.vpk(['scripts/makefile'])

        self.assertEqual(read_paths(path), {'scripts/makefile'})

    def testPathsComeBackLowercased(self):
        # Lookups are case-insensitive, so the index stores one casing.
        path = self.vpk(['Materials/Metal/Wall.vmt'])

        self.assertEqual(read_paths(path), {'materials/metal/wall.vmt'})

    def testPreloadBytesAreSteppedOver(self):
        # Small files keep their first bytes inline in the tree. Failing to
        # skip them desynchronises every entry after the first.
        path = self.vpk(['materials/a.vmt', 'materials/b.vmt'], preload=16)

        self.assertEqual(read_paths(path),
                         {'materials/a.vmt', 'materials/b.vmt'})

    def testManyExtensionsAndDirectories(self):
        wanted = {'materials/a.vmt', 'materials/b.vtf', 'materials/sub/c.vmt',
                  'models/d.mdl', 'sound/e.wav'}
        path = self.vpk(sorted(wanted))

        self.assertEqual(read_paths(path), wanted)

    def testAnEmptyVpkReadsAsNoPaths(self):
        path = self.vpk([])

        self.assertEqual(read_paths(path), set())

    def testSomethingThatIsNotAVpkIsRejected(self):
        path = os.path.join(self.root, 'not_dir.vpk')
        with open(path, 'wb') as handle:
            handle.write(b'this is not a vpk at all')

        with self.assertRaises(VpkError):
            read_paths(path)

    def testAnUnsupportedVersionIsRejected(self):
        path = os.path.join(self.root, 'v9_dir.vpk')
        with open(path, 'wb') as handle:
            handle.write(struct.pack('<III', SIGNATURE, 9, 0))

        with self.assertRaises(VpkError):
            read_paths(path)

    def testATruncatedFileIsRejected(self):
        path = os.path.join(self.root, 'short_dir.vpk')
        with open(path, 'wb') as handle:
            handle.write(b'\x00\x00')

        with self.assertRaises(VpkError):
            read_paths(path)


class IndexTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-vpkindex-')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def testItMergesSeveralVpks(self):
        first = build_vpk(os.path.join(self.root, 'a_dir.vpk'),
                          ['materials/a.vmt'])
        second = build_vpk(os.path.join(self.root, 'b_dir.vpk'),
                           ['models/b.mdl'])

        built = index([first, second])

        self.assertIn('materials/a.vmt', built)
        self.assertIn('models/b.mdl', built)
        self.assertEqual(len(built.sources), 2)

    def testMembershipIsCaseInsensitive(self):
        path = build_vpk(os.path.join(self.root, 'a_dir.vpk'),
                         ['materials/metal/wall.vmt'])

        built = index([path])

        self.assertIn('Materials/Metal/Wall.VMT', built)

    def testMembershipAcceptsBackslashes(self):
        path = build_vpk(os.path.join(self.root, 'a_dir.vpk'),
                         ['materials/metal/wall.vmt'])

        built = index([path])

        self.assertIn('materials\\metal\\wall.vmt', built)

    def testOneUnreadableVpkDoesNotStopTheRest(self):
        # A single corrupt archive should cost one warning, not the run.
        good = build_vpk(os.path.join(self.root, 'good_dir.vpk'),
                         ['materials/a.vmt'])
        bad = os.path.join(self.root, 'bad_dir.vpk')
        with open(bad, 'wb') as handle:
            handle.write(b'garbage')

        built = index([bad, good])

        self.assertIn('materials/a.vmt', built)
        self.assertEqual(len(built.failures), 1)

    def testAnAbsentVpkIsIgnored(self):
        built = index([os.path.join(self.root, 'nope_dir.vpk')])

        self.assertEqual(len(built), 0)
        self.assertEqual(built.failures, [])


if __name__ == '__main__':
    unittest.main()
