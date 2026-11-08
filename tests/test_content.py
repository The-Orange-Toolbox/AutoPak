"""Tests for the resolver.

The four answers this module gives are the whole behaviour of AutoPak, and
three of them are easy to confuse. A stock asset misread as missing turns
the report into noise; a stock asset misread as packable adds the base
game's textures to everyone's download; a missing asset misread as stock
hides exactly the problem the tool exists to surface.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from content import EMBEDDED, MISSING, PACKED, STOCK, build  # noqa: E402

from test_vpk import build_vpk  # noqa: E402


class ResolveTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-content-')
        self.custom = os.path.join(self.root, 'custom')
        self.game = os.path.join(self.root, 'game')
        os.makedirs(self.custom)
        os.makedirs(self.game)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def loose(self, directory, internal, text='x'):
        path = os.path.join(directory, internal.replace('/', os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write(text)
        return path

    def index(self, vpk_contents=None, pakfile=None, use_vpk=True):
        vpks = []
        if vpk_contents:
            vpks.append(build_vpk(os.path.join(self.root, 'stock_dir.vpk'),
                                  vpk_contents))
        built, _ = build(directories=[self.custom, self.game],
                         vpk_paths=vpks, pakfile=pakfile, use_vpk=use_vpk)
        return built

    def testALooseFileIsPacked(self):
        expected = self.loose(self.custom, 'materials/mine/wall.vmt')
        index = self.index()

        status, external, shadowed = index.resolve('materials/mine/wall.vmt')

        self.assertEqual(status, PACKED)
        self.assertEqual(external, expected)
        self.assertFalse(shadowed)

    def testAVpkOnlyFileIsStock(self):
        index = self.index(vpk_contents=['materials/dev/dev_measure.vmt'])

        status, external, _ = index.resolve('materials/dev/dev_measure.vmt')

        self.assertEqual(status, STOCK)
        self.assertIsNone(external)

    def testAFileInNeitherIsMissing(self):
        index = self.index(vpk_contents=['materials/dev/other.vmt'])

        status, external, _ = index.resolve('materials/mine/wall.vmt')

        self.assertEqual(status, MISSING)
        self.assertIsNone(external)

    def testALooseFileThatAlsoExistsInAVpkIsPackedAndFlagged(self):
        # Overriding a stock material is normal and deliberate. Packing a
        # decompiled stock asset by accident is not, and it is invisible
        # without the warning.
        self.loose(self.custom, 'materials/dev/dev_measure.vmt')
        index = self.index(vpk_contents=['materials/dev/dev_measure.vmt'])

        status, external, shadowed = index.resolve('materials/dev/dev_measure.vmt')

        self.assertEqual(status, PACKED)
        self.assertIsNotNone(external)
        self.assertTrue(shadowed)
        self.assertEqual(index.shadowed, ['materials/dev/dev_measure.vmt'])

    def testAPakfileOnlyFileIsEmbeddedNotMissing(self):
        # vbsp writes water and cubemap materials straight into the map.
        # They have no loose original, and calling them missing is a lie.
        index = self.index(
            pakfile={'materials/maps/x/cubemap.vmt'})

        status, _, _ = index.resolve('materials/maps/x/cubemap.vmt')

        self.assertEqual(status, EMBEDDED)

    def testALooseFileBeatsThePakfile(self):
        # Otherwise a stale asset from a previous pack would suppress the
        # loose file that is meant to replace it.
        self.loose(self.custom, 'materials/mine/wall.vmt')
        index = self.index(pakfile={'materials/mine/wall.vmt'})

        status, _, _ = index.resolve('materials/mine/wall.vmt')

        self.assertEqual(status, PACKED)

    def testTheFirstContentRootWins(self):
        # Search order is priority order: a map's custom folder overrides
        # the game's copy of the same file.
        expected = self.loose(self.custom, 'materials/wall.vmt', 'mine')
        self.loose(self.game, 'materials/wall.vmt', 'theirs')
        index = self.index()

        _, external, _ = index.resolve('materials/wall.vmt')

        self.assertEqual(external, expected)

    def testWithoutVpksEverythingNotLooseIsMissing(self):
        # What --no-vpk is for: make the report say everything the map
        # depends on, base game included.
        self.loose(self.custom, 'materials/mine/wall.vmt')
        index = self.index(vpk_contents=['materials/dev/dev_measure.vmt'],
                           use_vpk=False)

        self.assertEqual(index.resolve('materials/mine/wall.vmt')[0], PACKED)
        self.assertEqual(index.resolve('materials/dev/dev_measure.vmt')[0],
                         MISSING)

    def testTheAnswerIsCached(self):
        index = self.index()
        first = index.resolve('materials/mine/wall.vmt')

        # Creating the file afterwards must not change the answer within a
        # run; the crawl asks about the same path many times and has to get
        # a consistent story.
        self.loose(self.custom, 'materials/mine/wall.vmt')

        self.assertEqual(index.resolve('materials/mine/wall.vmt'), first)

    def testLookupIsCaseInsensitive(self):
        self.loose(self.custom, 'materials/mine/wall.vmt')
        index = self.index()

        status, _, _ = index.resolve('Materials/Mine/Wall.VMT')

        self.assertEqual(status, PACKED)


class InternalPathForTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-internal-')
        self.custom = os.path.join(self.root, 'tf', 'custom', 'mine')
        os.makedirs(self.custom)
        self.index, _ = build(directories=[self.custom], use_vpk=False)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def testItStripsTheContentRoot(self):
        found = self.index.internal_path_for(
            os.path.join(self.custom, 'materials', 'mine', 'wall.vmt'))

        self.assertEqual(found, 'materials/mine/wall.vmt')

    def testAFileOutsideEveryContentRootIsNone(self):
        # The engine could not load it either, so the caller should say so
        # rather than invent an internal path for it.
        found = self.index.internal_path_for(
            os.path.join(self.root, 'elsewhere', 'wall.vmt'))

        self.assertIsNone(found)


if __name__ == '__main__':
    unittest.main()
