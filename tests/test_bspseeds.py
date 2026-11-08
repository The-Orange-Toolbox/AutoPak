"""Tests for what the map's own lumps ask for.

These are the references that exist before any entity is read: brushwork
materials, the skybox, the props, and whatever the compiler already wrote
into the map. Each is a small rule with a specific reason to exist, and the
reasons are not guessable from the code.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))
sys.path.insert(0, HERE)

import bspseeds  # noqa: E402

from bspfixture import build_bsp, static_prop_lump  # noqa: E402


class SeedTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='autopak-seeds-')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def bsp(self, **kwargs):
        path = build_bsp(os.path.join(self.directory, 'testmap.bsp'), **kwargs)
        return bspseeds.read(path)


class BrushMaterialTestCase(SeedTestCase):
    def testEachTexdataNameBecomesAMaterial(self):
        bsp = self.bsp(textures=['MINE/WALL', 'TOOLS/TOOLSNODRAW'])

        found = [internal for internal, _ in bspseeds.brush_materials(bsp)]

        self.assertEqual(found, ['materials/mine/wall.vmt',
                                 'materials/tools/toolsnodraw.vmt'])

    def testARootLevelMaterialKeepsOneSeparator(self):
        # A material directly under materials/ is recorded with a leading
        # slash, and joining it naively would give 'materials//name'.
        bsp = self.bsp(textures=['/ROOTLEVEL'])

        found = [internal for internal, _ in bspseeds.brush_materials(bsp)]

        self.assertEqual(found, ['materials/rootlevel.vmt'])

    def testANameThatAlreadyCarriesTheExtensionIsNotDoubled(self):
        # Real maps do this: cp_snake records
        # 'WATER/WATER_2FORT_BENEATH.VMT' in the table. Appending .vmt
        # blindly looks for a file called '...vmt.vmt', which resolves
        # nowhere and reports content missing that is sitting right there.
        bsp = self.bsp(textures=['WATER/WATER_2FORT_BENEATH.VMT'])

        found = [internal for internal, _ in bspseeds.brush_materials(bsp)]

        self.assertEqual(found, ['materials/water/water_2fort_beneath.vmt'])

    def testANameThatAlreadyCarriesThePrefixIsNotDoubled(self):
        bsp = self.bsp(textures=['materials/mine/wall'])

        found = [internal for internal, _ in bspseeds.brush_materials(bsp)]

        self.assertEqual(found, ['materials/mine/wall.vmt'])

    def testAGeneratedBlendPatchIsMappedBackToItsOriginal(self):
        # vbsp renames blend materials used on brushes and writes the
        # generated one into the map. What has to be packed is the
        # original the mapper made, which is not named anywhere else.
        bsp = self.bsp(textures=['MAPS/TESTMAP/NATURE/BLEND01_WVT_PATCH'])

        found = [internal for internal, _ in bspseeds.brush_materials(bsp)]

        self.assertEqual(found, ['materials/nature/blend01.vmt'])


class WorldspawnTestCase(SeedTestCase):
    def testItReadsTheFirstEntity(self):
        bsp = self.bsp(entities=[[('classname', 'worldspawn'),
                                  ('skyname', 'sky_test_01')]])

        self.assertEqual(bspseeds.worldspawn(bsp)['skyname'], 'sky_test_01')

    def testASkynameGivesFourteenCandidateFaces(self):
        # Six sides plus the bare name, each with and without _hdr. Most
        # will not exist, which is why they are all speculative.
        found = bspseeds.skybox_materials('sky_test_01')

        self.assertEqual(len(found), 14)
        self.assertIn(('materials/skybox/sky_test_01up.vmt',
                       'worldspawn skyname'), found)
        self.assertIn(('materials/skybox/sky_test_01_hdrup.vmt',
                       'worldspawn skyname'), found)

    def testEverySkyboxFaceIsSpeculative(self):
        bsp = self.bsp(entities=[[('classname', 'worldspawn'),
                                  ('skyname', 'sky_test_01')]])

        found = bspseeds.world_materials(bsp, 'testmap')
        skybox = [f for f in found if 'skybox' in f[0]]

        self.assertTrue(all(speculative for _, _, speculative in skybox))

    def testADetailMaterialIsADefiniteReference(self):
        # Unlike the skybox faces, this one is named outright and its
        # absence is a real problem worth reporting.
        bsp = self.bsp(entities=[[('classname', 'worldspawn'),
                                  ('detailmaterial', 'detail/sprites')]])

        found = bspseeds.world_materials(bsp, 'testmap')

        self.assertIn(('materials/detail/sprites.vmt',
                       'worldspawn detailmaterial', False), found)

    def testTheMenuPhotoIsSpeculative(self):
        # Most maps do not have one.
        bsp = self.bsp()

        found = bspseeds.world_materials(bsp, 'testmap')
        photo = [f for f in found if 'menu_photos' in f[0]]

        self.assertEqual(len(photo), 1)
        self.assertTrue(photo[0][2])

    def testTheDetailSpriteFileIsFound(self):
        bsp = self.bsp(entities=[[('classname', 'worldspawn'),
                                  ('detailvbsp', 'detail_2fort.vbsp')]])

        self.assertEqual(bspseeds.detail_sprite_file(bsp),
                         ('detail_2fort.vbsp', 'worldspawn detailvbsp'))

    def testAMapWithNoDetailSpritesGivesNothing(self):
        self.assertIsNone(bspseeds.detail_sprite_file(self.bsp()))


class PakfileTestCase(SeedTestCase):
    def testItListsWhatIsAlreadyInTheMap(self):
        bsp = self.bsp(pakfile={'materials/maps/x/water.vmt': 'x'})

        self.assertEqual(bspseeds.pakfile_names(bsp),
                         {'materials/maps/x/water.vmt'})

    def testAMapWithNoPakfileIsEmptyNotAnError(self):
        self.assertEqual(bspseeds.pakfile_names(self.bsp()), set())

    def testAnEmbeddedMaterialContributesItsParent(self):
        # This is why the pakfile is read at all: vbsp writes generated
        # water and cubemap materials that patch a parent which is not
        # named anywhere else in the map.
        bsp = self.bsp(pakfile={
            'materials/maps/x/water.vmt':
                'Patch\n{\n"include" "materials/nature/water.vmt"\n}\n'})

        found = [internal for internal, _ in bspseeds.pakfile_materials(bsp)]

        self.assertEqual(found, ['materials/nature/water.vmt'])

    def testTheOriginNamesTheEmbeddedFile(self):
        bsp = self.bsp(pakfile={
            'materials/maps/x/water.vmt':
                'Patch\n{\n"include" "materials/nature/water.vmt"\n}\n'})

        _, origin = bspseeds.pakfile_materials(bsp)[0]

        self.assertIn('materials/maps/x/water.vmt', origin)


class PropTestCase(SeedTestCase):
    def testStaticPropModelsAreFound(self):
        bsp = self.bsp(static_props=['models/mine/a.mdl', 'models/mine/b.mdl'])

        self.assertEqual(set(bspseeds.prop_models(bsp)),
                         {'models/mine/a.mdl', 'models/mine/b.mdl'})

    def testSkinsAreMergedPerModel(self):
        # A model placed two hundred times must be added once carrying
        # every skin any of those props asked for, or the crawl either
        # packs materials nothing uses or misses ones something does.
        path = os.path.join(self.directory, 'skins.bsp')
        import bspfixture
        original = bspfixture.static_prop_lump
        bspfixture.static_prop_lump = lambda models, props=None, version=10: \
            static_prop_lump(models, props=[(0, 0), (0, 3), (1, 2)])
        try:
            build_bsp(path, static_props=['models/a.mdl', 'models/b.mdl'])
        finally:
            bspfixture.static_prop_lump = original

        found = bspseeds.prop_models(bspseeds.read(path))

        self.assertEqual(found['models/a.mdl'], {0, 3})
        self.assertEqual(found['models/b.mdl'], {2})

    def testAMapWithNoPropsGivesNothing(self):
        self.assertEqual(bspseeds.prop_models(self.bsp()), {})


class ReadTestCase(SeedTestCase):
    def testACompressedMapIsRefused(self):
        path = build_bsp(os.path.join(self.directory, 'packed.bsp'),
                         textures=['MINE/WALL'])
        with open(path, 'rb') as handle:
            data = bytearray(handle.read())
        offset = int.from_bytes(data[8:12], 'little')
        data[offset:offset + 4] = b'LZMA'
        with open(path, 'wb') as handle:
            handle.write(bytes(data))

        with self.assertRaises(bspseeds.BspError) as caught:
            bspseeds.read(path)

        self.assertIn('bspzip -repack', str(caught.exception))

    def testSomethingThatIsNotABspIsRefused(self):
        path = os.path.join(self.directory, 'nope.bsp')
        with open(path, 'wb') as handle:
            handle.write(b'not a map at all')

        with self.assertRaises(bspseeds.BspError):
            bspseeds.read(path)

    def testAnOrdinaryMapNeedsNoProfile(self):
        self.assertIsNone(bspseeds.detect_profile(
            build_bsp(os.path.join(self.directory, 'plain.bsp'))))


if __name__ == '__main__':
    unittest.main()
