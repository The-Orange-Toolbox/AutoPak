"""Tests for the command line itself.

Every other test calls into the domain modules directly, which means a flag
can be parsed, documented, and wired to nothing at all without a single test
noticing. These run the real entry point in a subprocess so the wiring is
covered too.

The validation tests matter more than they look. A packer is usually run
from inside a compile chain, where nobody is watching stdout -- so a
mistyped content directory has to stop the run with a sentence naming the
path, not scroll past as a warning and produce a map that is quietly missing
half its textures.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))
sys.path.insert(0, HERE)

from bspfixture import build_bsp  # noqa: E402

ENTRY = os.path.join(HERE, os.pardir, 'src', '__main__.py')

GAMEINFO = '''"GameInfo"
{
\tFileSystem
\t{
\t\tSearchPaths
\t\t{
\t\t\tgame\t|gameinfo_path|.
\t\t}
\t}
}
'''


class CommandLineTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='autopak-cli-')

        # A game folder the validation will accept, and a map inside it, so
        # the default --game discovery has something to walk up to.
        self.game = os.path.join(self.directory, 'tf')
        self.maps = os.path.join(self.game, 'maps')
        os.makedirs(self.maps)
        with open(os.path.join(self.game, 'gameinfo.txt'), 'w') as handle:
            handle.write(GAMEINFO)

        self.bsp = build_bsp(os.path.join(self.maps, 'testmap.bsp'),
                             textures=['MINE/WALL'])

        # The one material the map uses, present as loose content, so a
        # default run has something to pack and nothing to complain about.
        self.material = os.path.join(self.game, 'materials', 'mine',
                                     'wall.vmt')
        os.makedirs(os.path.dirname(self.material))
        with open(self.material, 'w') as handle:
            handle.write('"UnlitGeneric"\n{\n"$basetexture" "mine/wall"\n}\n')
        with open(os.path.join(self.game, 'materials', 'mine', 'wall.vtf'),
                  'wb') as handle:
            handle.write(b'VTF\x00')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def run_autopak(self, *arguments):
        return subprocess.run([sys.executable, ENTRY] + list(arguments),
                              capture_output=True, text=True)

    def testItRunsOnAMapInsideAGameFolder(self):
        result = self.run_autopak(self.bsp)

        self.assertEqual(result.returncode, 0, result.stderr)

    def testItFindsTheGameFolderByWalkingUpFromTheMap(self):
        # Nothing passed but the map: --game has to be discovered, or the
        # tool is unusable from Hammer's expert compile where the only
        # substitution available is the bsp path.
        result = self.run_autopak(self.bsp)

        self.assertEqual(result.returncode, 0, result.stderr)

    def testAMapOutsideAnyGameFolderAsksForTheGameFolder(self):
        stray = build_bsp(os.path.join(self.directory, 'stray.bsp'))

        result = self.run_autopak(stray)

        self.assertEqual(result.returncode, 2)
        self.assertIn('--game', result.stderr)

    def testAGameFolderWithNoGameinfoIsRejected(self):
        result = self.run_autopak(self.bsp, '--game', self.directory)

        self.assertEqual(result.returncode, 2)
        self.assertIn('gameinfo.txt', result.stderr)

    def testAMissingMapIsRejected(self):
        result = self.run_autopak(os.path.join(self.maps, 'nope.bsp'))

        self.assertEqual(result.returncode, 2)
        self.assertIn('not found', result.stderr)

    def testSomethingThatIsNotABspIsRejected(self):
        # Pointing a packer at the .vmf is an easy slip, and the error it
        # would otherwise produce comes from deep inside a lump reader.
        vmf = os.path.join(self.maps, 'testmap.vmf')
        with open(vmf, 'w') as handle:
            handle.write('')

        result = self.run_autopak(vmf)

        self.assertEqual(result.returncode, 2)
        self.assertIn('not a .bsp', result.stderr)

    def testVerboseAndQuietTogetherAreRejected(self):
        result = self.run_autopak(self.bsp, '-v', '-q')

        self.assertEqual(result.returncode, 2)

    def testAMissingContentDirectoryIsRejected(self):
        result = self.run_autopak(self.bsp, '--source-directory',
                                  os.path.join(self.directory, 'nowhere'))

        self.assertEqual(result.returncode, 2)
        self.assertIn('content directory', result.stderr)

    def testAMissingIncludeIsRejected(self):
        result = self.run_autopak(self.bsp, '--include',
                                  os.path.join(self.directory, 'nope.vmt'))

        self.assertEqual(result.returncode, 2)
        self.assertIn('included file', result.stderr)

    def testAMissingExcludeVpkIsRejected(self):
        result = self.run_autopak(self.bsp, '--exclude-vpk',
                                  os.path.join(self.directory, 'no_dir.vpk'))

        self.assertEqual(result.returncode, 2)
        self.assertIn('excluded vpk', result.stderr)

    def testEveryDocumentedFlagIsAccepted(self):
        # The sidecar and the CompilePal parameters file both name these
        # flags. If one is renamed here without being renamed there, the
        # tool silently stops working inside the GUI that launches it.
        result = self.run_autopak(
            self.bsp,
            '--game', self.game,
            '--source-directory', self.game,
            '--profile', 'TF2',
            '--no-vpk',
            '--no-swvtx',
            '--rename-nav',
            '--rename-particle-manifest',
            '--no-utility-files',
            '--output', os.path.join(self.directory, 'list.txt'),
            '--report', 'detailed',
            '--strict',
            '-v')

        self.assertEqual(result.returncode, 0, result.stderr)

    def testItWritesTheListBesideTheMapByDefault(self):
        self.run_autopak(self.bsp)

        expected = os.path.join(self.maps, 'testmap_files.txt')

        self.assertTrue(os.path.isfile(expected))

    def testTheListNamesTheMaterialAndItsTexture(self):
        output = os.path.join(self.directory, 'list.txt')

        self.run_autopak(self.bsp, '--output', output)

        with open(output) as handle:
            text = handle.read()

        self.assertIn('materials/mine/wall.vmt', text)
        self.assertIn('materials/mine/wall.vtf', text)

    def testStdoutWritesNoFile(self):
        output = os.path.join(self.directory, 'list.txt')

        result = self.run_autopak(self.bsp, '--stdout', '--output', output)

        self.assertIn('materials/mine/wall.vmt', result.stdout)
        self.assertFalse(os.path.isfile(output))

    def testAMissingFileIsReportedAndStillExitsZero(self):
        # Without --strict a compile chain carries on; the mapper is told
        # and decides for themselves.
        os.remove(self.material)

        result = self.run_autopak(self.bsp)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('materials/mine/wall.vmt', result.stdout)
        self.assertIn('missing', result.stdout)

    def testTheMissingReportSurvivesQuiet(self):
        # It is the main reason to run the tool, so -q must not hide it.
        os.remove(self.material)

        result = self.run_autopak(self.bsp, '-q')

        self.assertIn('materials/mine/wall.vmt', result.stdout)

    def testStrictFailsWhenSomethingIsMissing(self):
        os.remove(self.material)

        result = self.run_autopak(self.bsp, '--strict')

        self.assertEqual(result.returncode, 1)

    def testStrictPassesWhenNothingIsMissing(self):
        result = self.run_autopak(self.bsp, '--strict')

        self.assertEqual(result.returncode, 0, result.stdout)

    def testACompressedMapIsRefusedWithAnActionableMessage(self):
        # Valve repacked the stock maps, so this is what a mapper pointing
        # AutoPak at their game's own maps folder will hit first.
        compressed = os.path.join(self.maps, 'packed.bsp')
        with open(self.bsp, 'rb') as handle:
            data = bytearray(handle.read())
        offset = int.from_bytes(data[8:12], 'little')
        data[offset:offset + 4] = b'LZMA'
        with open(compressed, 'wb') as handle:
            handle.write(bytes(data))

        result = self.run_autopak(compressed)

        self.assertEqual(result.returncode, 1)
        self.assertIn('bspzip -repack', result.stdout)
        # A message, not a crash report.
        self.assertNotIn('Traceback', result.stdout + result.stderr)

    def testTheVersionMatchesTheConstants(self):
        from _constants import VERSION

        result = self.run_autopak('--version')

        self.assertEqual(result.stdout.strip(), VERSION)


if __name__ == '__main__':
    unittest.main()
