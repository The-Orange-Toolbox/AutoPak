"""End-to-end tests: a whole map, packed.

Every other test file checks one rule in isolation. These build a small but
complete mod -- a map, its content, and the sidecar files a map has by
convention -- and run the real :func:`pack.pack` over it, so the wiring
between the passes is covered too. A rule that works perfectly and is never
called from the pipeline fails here and nowhere else.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))
sys.path.insert(0, HERE)

import content  # noqa: E402
import pack  # noqa: E402

from bspfixture import build_bsp  # noqa: E402

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

MATERIAL = '''"LightmappedGeneric"
{
\t"$basetexture" "mine/wall"
\t"$bumpmap" "mine/wall_n"
}
'''


class PackTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-pack-')
        self.game = os.path.join(self.root, 'tf')
        self.maps = os.path.join(self.game, 'maps')
        os.makedirs(self.maps)

        self.write('gameinfo.txt', GAMEINFO)
        self.output = os.path.join(self.root, 'files.txt')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, internal, text=''):
        path = os.path.join(self.game, internal.replace('/', os.sep))
        directory = os.path.dirname(path)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, 'w') as handle:
            handle.write(text)
        return path

    def bsp(self, **kwargs):
        return build_bsp(os.path.join(self.maps, 'mymap.bsp'), **kwargs)

    def pack(self, path, **kwargs):
        options = dict(bsp_path=path, game_dir=self.game,
                       output_path=self.output, quiet=True)
        options.update(kwargs)
        return pack.pack(**options)

    def listed(self):
        with open(self.output) as handle:
            lines = [line.strip() for line in handle if line.strip()]
        return lines[0::2]

    # -- the basics -------------------------------------------------------

    def testAMapWithNothingCustomPacksNothing(self):
        summary = self.pack(self.bsp())

        self.assertEqual(summary['packed'], 0)
        self.assertEqual(summary['missing'], 0)

    def testAMaterialAndItsTexturesArePacked(self):
        self.write('materials/mine/wall.vmt', MATERIAL)
        self.write('materials/mine/wall.vtf')
        self.write('materials/mine/wall_n.vtf')

        self.pack(self.bsp(textures=['MINE/WALL']))

        self.assertEqual(sorted(self.listed()),
                         ['materials/mine/wall.vmt',
                          'materials/mine/wall.vtf',
                          'materials/mine/wall_n.vtf'])

    def testAPatchChainIsFollowed(self):
        self.write('materials/mine/red.vmt',
                   'Patch\n{\n"include" "materials/mine/base.vmt"\n}\n')
        self.write('materials/mine/base.vmt',
                   '"VertexLitGeneric"\n{\n"$basetexture" "mine/skin"\n}\n')
        self.write('materials/mine/skin.vtf')

        self.pack(self.bsp(textures=['MINE/RED']))

        self.assertIn('materials/mine/skin.vtf', self.listed())

    def testAMissingMaterialIsReportedNotPacked(self):
        summary = self.pack(self.bsp(textures=['MINE/GONE']))

        self.assertEqual(summary['missing'], 1)
        self.assertEqual(summary['missing_list'][0]['internal'],
                         'materials/mine/gone.vmt')

    def testAnAbsentSkyboxFaceIsNotReported(self):
        # Thirteen of the fourteen candidates never exist.
        summary = self.pack(self.bsp(entities=[
            [('classname', 'worldspawn'), ('skyname', 'sky_test_01')]]))

        self.assertEqual(summary['missing'], 0)

    # -- the seeds --------------------------------------------------------

    def testAnEntityModelIsPackedWithItsSiblings(self):
        self.write('models/mine/thing.mdl')
        self.write('models/mine/thing.vvd')
        self.write('models/mine/thing.dx90.vtx')

        self.pack(self.bsp(entities=[
            [('classname', 'worldspawn')],
            [('classname', 'prop_dynamic'),
             ('model', 'models/mine/thing.mdl')]]))

        listed = self.listed()

        self.assertIn('models/mine/thing.mdl', listed)
        self.assertIn('models/mine/thing.vvd', listed)
        self.assertIn('models/mine/thing.dx90.vtx', listed)

    def testAStaticPropIsPacked(self):
        self.write('models/mine/prop.mdl')

        self.pack(self.bsp(static_props=['models/mine/prop.mdl']))

        self.assertIn('models/mine/prop.mdl', self.listed())

    def testStockContentIsNotPackedButIsNotMissingEither(self):
        # No VPKs here, so 'stock' is stood in for by the pakfile: a
        # material vbsp generated into the map has no loose original and
        # must not be reported.
        summary = self.pack(self.bsp(
            textures=['MAPS/MYMAP/WATER'],
            pakfile={'materials/maps/mymap/water.vmt': '"Water"\n{\n}\n'}))

        self.assertEqual(summary['missing'], 0)
        self.assertEqual(summary['embedded'], 1)

    def testAnEmbeddedPatchPullsInItsParent(self):
        self.write('materials/mine/water.vmt',
                   '"Water"\n{\n"$basetexture" "mine/water"\n}\n')
        self.write('materials/mine/water.vtf')

        self.pack(self.bsp(pakfile={
            'materials/maps/mymap/water.vmt':
                'Patch\n{\n"include" "materials/mine/water.vmt"\n}\n'}))

        self.assertIn('materials/mine/water.vmt', self.listed())

    # -- the long tail ----------------------------------------------------

    def testASoundscapeScriptAndItsSoundsArePacked(self):
        self.write('scripts/soundscapes_mymap.txt',
                   'Mymap.Wind\n{\n"wave" "mine/wind.wav"\n}\n')
        self.write('sound/mine/wind.wav')

        self.pack(self.bsp())

        listed = self.listed()

        self.assertIn('scripts/soundscapes_mymap.txt', listed)
        self.assertIn('sound/mine/wind.wav', listed)

    def testAParticleManifestPullsInItsFilesMaterials(self):
        self.write('maps/mymap_particles.txt',
                   'particles_manifest\n{\n"file" "!particles/mine.pcf"\n}\n')
        # A .pcf that will not parse still has to be packed; only its
        # dependencies are lost, and that is a warning not a failure.
        self.write('particles/mine.pcf', 'not really a particle file')

        summary = self.pack(self.bsp())

        listed = self.listed()

        self.assertIn('maps/mymap_particles.txt', listed)
        self.assertIn('particles/mine.pcf', listed)
        self.assertEqual(summary['missing'], 0)

    def testAVscriptAndWhatItPrecachesArePacked(self):
        self.write('scripts/vscripts/mymap/logic.nut',
                   'PrecacheModel("models/mine/x.mdl")\n'
                   'PrecacheSound("mine/beep.wav")\n')
        self.write('models/mine/x.mdl')
        self.write('sound/mine/beep.wav')

        self.pack(self.bsp(entities=[
            [('classname', 'worldspawn')],
            [('classname', 'logic_script'),
             ('vscripts', 'mymap/logic.nut')]]))

        listed = self.listed()

        self.assertIn('scripts/vscripts/mymap/logic.nut', listed)
        self.assertIn('models/mine/x.mdl', listed)
        self.assertIn('sound/mine/beep.wav', listed)

    def testAVscriptHintPacksWhatNoScannerCouldFind(self):
        self.write('scripts/vscripts/mymap/logic.nut',
                   '// !CompilePal::IncludeFile("materials/mine/hint.vmt")\n')
        self.write('materials/mine/hint.vmt', '"UnlitGeneric"\n{\n}\n')

        self.pack(self.bsp(entities=[
            [('classname', 'worldspawn')],
            [('classname', 'logic_script'),
             ('vscripts', 'mymap/logic.nut')]]))

        self.assertIn('materials/mine/hint.vmt', self.listed())

    def testANavMeshIsFoundWithoutBeingReferenced(self):
        self.write('maps/mymap.nav')

        self.pack(self.bsp())

        self.assertIn('maps/mymap.nav', self.listed())

    def testARenamedNavIsListedUnderTheGenericName(self):
        self.write('maps/mymap.nav')

        self.pack(self.bsp(), rename_nav=True)

        listed = self.listed()

        self.assertIn('maps/embed.nav', listed)
        self.assertNotIn('maps/mymap.nav', listed)

    def testUtilityFilesCanBeSkipped(self):
        self.write('maps/mymap.nav')

        self.pack(self.bsp(), utility_files=False)

        self.assertEqual(self.listed(), [])

    # -- sounds -----------------------------------------------------------

    def testASoundscriptEntryIsCountedNotReportedMissing(self):
        # The rule that keeps the report usable.
        summary = self.pack(self.bsp(entities=[
            [('classname', 'worldspawn')],
            [('classname', 'ambient_generic'), ('message', 'Ambient.Wind')]]))

        self.assertEqual(summary['missing'], 0)
        self.assertEqual(summary['scripted'], 1)

    def testASoundPathIsReportedWhenAbsent(self):
        summary = self.pack(self.bsp(entities=[
            [('classname', 'worldspawn')],
            [('classname', 'ambient_generic'),
             ('message', 'mine/gone.wav')]]))

        self.assertEqual(summary['missing'], 1)

    # -- selection --------------------------------------------------------

    def testAnIncludedFileIsPackedWithoutBeingReferenced(self):
        path = self.write('materials/mine/extra.vmt', '"Unlit"\n{\n}\n')

        self.pack(self.bsp(), includes=[path])

        self.assertIn('materials/mine/extra.vmt', self.listed())

    def testAnExcludedFileIsNotPacked(self):
        self.write('materials/mine/wall.vmt', MATERIAL)
        self.write('materials/mine/wall.vtf')
        self.write('materials/mine/wall_n.vtf')

        self.pack(self.bsp(textures=['MINE/WALL']),
                  excludes=['materials/mine/wall.vtf'])

        self.assertNotIn('materials/mine/wall.vtf', self.listed())

    def testAnExcludedDirectoryIsNotPacked(self):
        self.write('materials/mine/wall.vmt', MATERIAL)
        self.write('materials/mine/wall.vtf')

        self.pack(self.bsp(textures=['MINE/WALL']),
                  exclude_dirs=['materials/mine'])

        self.assertEqual(self.listed(), [])

    def testSoftwareMeshesCanBeSkipped(self):
        self.write('models/mine/thing.mdl')
        self.write('models/mine/thing.sw.vtx')
        self.write('models/mine/thing.dx90.vtx')

        self.pack(self.bsp(static_props=['models/mine/thing.mdl']),
                  pack_swvtx=False)

        listed = self.listed()

        self.assertNotIn('models/mine/thing.sw.vtx', listed)
        self.assertIn('models/mine/thing.dx90.vtx', listed)

    def testAnExtraContentDirectoryIsSearched(self):
        extra = os.path.join(self.root, 'extra')
        os.makedirs(os.path.join(extra, 'materials', 'mine'))
        with open(os.path.join(extra, 'materials', 'mine', 'wall.vmt'),
                  'w') as handle:
            handle.write('"Unlit"\n{\n}\n')

        self.pack(self.bsp(textures=['MINE/WALL']), source_dirs=[extra])

        self.assertIn('materials/mine/wall.vmt', self.listed())

    # -- output -----------------------------------------------------------

    def testTheListIsAlternatingInternalAndExternalPaths(self):
        self.write('materials/mine/wall.vmt', '"Unlit"\n{\n}\n')

        self.pack(self.bsp(textures=['MINE/WALL']))

        with open(self.output) as handle:
            lines = [line.strip() for line in handle if line.strip()]

        self.assertEqual(lines[0], 'materials/mine/wall.vmt')
        self.assertTrue(os.path.isfile(lines[1]))

    def testTwoRunsProduceTheSameFile(self):
        # Discovery order is stable, so a diff between two lists means a
        # real change in the map's content.
        self.write('materials/mine/wall.vmt', MATERIAL)
        self.write('materials/mine/wall.vtf')

        bsp = self.bsp(textures=['MINE/WALL'])

        self.pack(bsp)
        with open(self.output) as handle:
            first = handle.read()

        self.pack(bsp)
        with open(self.output) as handle:
            second = handle.read()

        self.assertEqual(first, second)

    def testTheSummaryCountsWhatWasPacked(self):
        self.write('materials/mine/wall.vmt', MATERIAL)
        self.write('materials/mine/wall.vtf')
        self.write('materials/mine/wall_n.vtf')

        summary = self.pack(self.bsp(textures=['MINE/WALL']))

        self.assertEqual(summary['packed'], 3)
        self.assertEqual(summary['by_kind']['material'], 1)
        self.assertEqual(summary['by_kind']['texture'], 2)
        self.assertGreater(summary['bytes'], 0)


class FailureTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-packfail-')

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def testAGameFolderWithNoSearchPathsIsRefused(self):
        game = os.path.join(self.root, 'tf')
        os.makedirs(game)
        with open(os.path.join(game, 'gameinfo.txt'), 'w') as handle:
            handle.write('"GameInfo"\n{\n}\n')

        bsp = build_bsp(os.path.join(self.root, 'mymap.bsp'))

        with self.assertRaises(pack.PackError):
            pack.pack(bsp_path=bsp, game_dir=game,
                      output_path=os.path.join(self.root, 'files.txt'),
                      quiet=True)


if __name__ == '__main__':
    unittest.main()
