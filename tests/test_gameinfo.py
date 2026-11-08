"""Tests for reading a mod's search paths.

Getting these wrong does not degrade the pack, it inverts it: a search path
that fails to resolve turns every base-game asset behind it into a reported
missing file, and a VPK entry that gets dropped does the same. The cases
below are taken from Team Fortress 2's own gameinfo.txt.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from gameinfo import (GameinfoError, find_game_dir,  # noqa: E402
                      search_paths, vpk_dir_file)

from test_vpk import build_vpk  # noqa: E402


def gameinfo(*entries):
    lines = ['"GameInfo"', '{', '\tFileSystem', '\t{', '\t\tSearchPaths',
             '\t\t{']
    for role, value in entries:
        lines.append('\t\t\t{}\t{}'.format(role, value))
    lines += ['\t\t}', '\t}', '}', '']
    return '\n'.join(lines)


class SearchPathTestCase(unittest.TestCase):
    def setUp(self):
        # A miniature Steam layout: <root>/tf is the mod, <root>/hl2 is the
        # shared content beside it.
        self.root = tempfile.mkdtemp(prefix='autopak-gameinfo-')
        self.game = os.path.join(self.root, 'tf')
        self.shared = os.path.join(self.root, 'hl2')
        os.makedirs(self.game)
        os.makedirs(self.shared)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, text):
        with open(os.path.join(self.game, 'gameinfo.txt'), 'w') as handle:
            handle.write(text)

    def resolve(self, *entries):
        self.write(gameinfo(*entries))
        return search_paths(self.game)

    def testGameinfoPathIsTheModFolder(self):
        directories, _ = self.resolve(('mod', '|gameinfo_path|.'))

        self.assertEqual(directories, [self.game])

    def testABareRelativePathResolvesBesideTheMod(self):
        directories, _ = self.resolve(('game', 'hl2'))

        self.assertEqual(directories, [self.shared])

    def testAllSourceEnginePathsIsResolvedNotSkipped(self):
        # CompilePal drops this token, which it can afford to because an
        # unresolved path only means "not packed". Here it would mean every
        # HL2 asset gets reported missing.
        directories, _ = self.resolve(('game', '|all_source_engine_paths|hl2'))

        self.assertEqual(directories, [self.shared])

    def testAnAbsolutePathIsUsedAsIs(self):
        directories, _ = self.resolve(('game', self.shared.replace('\\', '/')))

        self.assertEqual(directories, [self.shared])

    def testAWildcardMountsEverySubfolder(self):
        for name in ('bravo', 'alpha'):
            os.makedirs(os.path.join(self.game, 'custom', name))

        directories, _ = self.resolve(('game', '|gameinfo_path|custom/*'))

        self.assertEqual(directories, [os.path.join(self.game, 'custom', 'alpha'),
                                       os.path.join(self.game, 'custom', 'bravo')])

    def testAWildcardAlsoMountsLooseVpksBesideTheSubfolders(self):
        # The comment in TF2's own gameinfo.txt says so: dropping a VPK in
        # custom/ is the documented way to install a mod.
        os.makedirs(os.path.join(self.game, 'custom'))
        build_vpk(os.path.join(self.game, 'custom', 'mod_dir.vpk'),
                  ['materials/x.vmt'])

        _, vpks = self.resolve(('game', '|gameinfo_path|custom/*'))

        self.assertEqual([os.path.basename(v) for v in vpks], ['mod_dir.vpk'])

    def testAVpkEntryIsKept(self):
        # CompilePal skips these. AutoPak needs them to tell base-game
        # content from content that is genuinely absent.
        build_vpk(os.path.join(self.game, 'tf2_textures_dir.vpk'),
                  ['materials/x.vmt'])

        _, vpks = self.resolve(('game', 'tf/tf2_textures.vpk'))

        self.assertEqual([os.path.basename(v) for v in vpks],
                         ['tf2_textures_dir.vpk'])

    def testAVpkNamedInGameinfoButAbsentIsSkipped(self):
        # tf2_lv.vpk is listed in every TF2 install and shipped in none.
        _, vpks = self.resolve(('game_lv', 'tf/tf2_lv.vpk'))

        self.assertEqual(vpks, [])

    def testBinariesAreNotAContentPath(self):
        os.makedirs(os.path.join(self.game, 'bin'))

        directories, _ = self.resolve(('gamebin', 'tf/bin'))

        self.assertEqual(directories, [])

    def testAFolderNamedTwiceIsSearchedOnce(self):
        directories, _ = self.resolve(('mod', '|gameinfo_path|.'),
                                      ('game', 'tf'))

        self.assertEqual(directories, [self.game])

    def testOrderIsThePriorityOrder(self):
        # Custom content has to beat the game's, or a mapper's override of a
        # stock material never gets packed.
        os.makedirs(os.path.join(self.game, 'custom', 'mine'))

        directories, _ = self.resolve(('game', '|gameinfo_path|custom/*'),
                                      ('mod', '|gameinfo_path|.'),
                                      ('game', 'hl2'))

        self.assertEqual(directories,
                         [os.path.join(self.game, 'custom', 'mine'),
                          self.game, self.shared])

    def testAMissingSearchPathsBlockIsAnError(self):
        self.write('"GameInfo"\n{\n}\n')

        with self.assertRaises(GameinfoError):
            search_paths(self.game)

    def testANonexistentDirectoryIsSkipped(self):
        directories, _ = self.resolve(('game', 'nowhere'))

        self.assertEqual(directories, [])


class VpkDirFileTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-vpkname-')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def testItFindsTheDirHalfOfAMultiPartVpk(self):
        # gameinfo says 'tf2_textures.vpk'; the disk has
        # 'tf2_textures_dir.vpk' plus numbered archives.
        actual = os.path.join(self.root, 'tf2_textures_dir.vpk')
        build_vpk(actual, ['materials/x.vmt'])

        found = vpk_dir_file(os.path.join(self.root, 'tf2_textures.vpk'))

        self.assertEqual(found, actual)

    def testASinglePartVpkIsUsedDirectly(self):
        actual = os.path.join(self.root, 'mod.vpk')
        build_vpk(actual, ['materials/x.vmt'])

        self.assertEqual(vpk_dir_file(actual), actual)

    def testAnAbsentVpkIsNone(self):
        self.assertIsNone(vpk_dir_file(os.path.join(self.root, 'no.vpk')))


class FindGameDirTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-findgame-')
        self.game = os.path.join(self.root, 'tf')
        self.maps = os.path.join(self.game, 'maps')
        os.makedirs(self.maps)
        with open(os.path.join(self.game, 'gameinfo.txt'), 'w') as handle:
            handle.write(gameinfo(('mod', '|gameinfo_path|.')))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def testItWalksUpFromTheMap(self):
        found = find_game_dir(os.path.join(self.maps, 'x.bsp'))

        self.assertEqual(found, self.game)

    def testAMapNowhereNearAGameFolderIsNone(self):
        self.assertIsNone(find_game_dir(os.path.join(self.root, 'x.bsp')))


if __name__ == '__main__':
    unittest.main()
