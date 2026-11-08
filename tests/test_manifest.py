"""Tests for particle manifests, vgui layouts, overview files and detail
sprite definitions.

Four small formats that share one property: nothing in the map points at
what they name, so anything missed here is content that simply never
appears in game.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from formats import detailvbsp, manifest, radar, res  # noqa: E402


class ManifestTestCase(unittest.TestCase):
    def testItReadsTheParticleFiles(self):
        text = ('particles_manifest\n{\n'
                '"file" "!particles/my_effects.pcf"\n}\n')

        self.assertEqual(manifest.files(text),
                         ['particles/my_effects.pcf'])

    def testThePrecacheMarkerIsNotPartOfTheName(self):
        # The leading '!' tells the engine to precache; it is a directive,
        # not a character in the filename.
        text = 'particles_manifest\n{\n"file" "!particles/a.pcf"\n}\n'

        self.assertEqual(manifest.files(text), ['particles/a.pcf'])

    def testAFileWithoutTheMarkerIsStillRead(self):
        text = 'particles_manifest\n{\n"file" "particles/a.pcf"\n}\n'

        self.assertEqual(manifest.files(text), ['particles/a.pcf'])

    def testSeveralFilesAreAllRead(self):
        text = ('particles_manifest\n{\n'
                '"file" "!particles/a.pcf"\n'
                '"file" "!particles/b.pcf"\n}\n')

        self.assertEqual(manifest.files(text),
                         ['particles/a.pcf', 'particles/b.pcf'])

    def testAnEmptyManifestIsEmpty(self):
        self.assertEqual(manifest.files('particles_manifest\n{\n}\n'), [])


class ResTestCase(unittest.TestCase):
    def testABareImageNameIsRelativeToVgui(self):
        text = ('"Resource/UI/Panel.res"\n{\n"MapImage"\n{\n'
                '"image" "importtool_goldstar"\n}\n}\n')

        images, _ = res.images(text)

        self.assertEqual(images, ['materials/vgui/importtool_goldstar.vmt'])

    def testARelativePathIsResolved(self):
        # '../hud/icon' is the commonest spelling in the game's own files:
        # out of materials/vgui/ and back in somewhere else.
        text = '"P"\n{\n"E"\n{\n"image" "../hud/icon"\n}\n}\n'

        images, _ = res.images(text)

        self.assertEqual(images, ['materials/hud/icon.vmt'])

    def testAValueThatAlreadyNamesVguiIsNotPrefixedTwice(self):
        text = '"P"\n{\n"E"\n{\n"image" "vgui/maps/menu_photos_mymap"\n}\n}\n'

        images, _ = res.images(text)

        self.assertEqual(images,
                         ['materials/vgui/maps/menu_photos_mymap.vmt'])

    def testBaseDirectivesAreSurfacedForTheCallerToResolve(self):
        text = '#base "shared.res"\n"P"\n{\n}\n'

        _, bases = res.images(text)

        self.assertEqual(bases, ['shared.res'])

    def testAnImageInsideNestedPanelsIsFound(self):
        text = ('"P"\n{\n"A"\n{\n"B"\n{\n"image" "deep"\n}\n}\n}\n')

        images, _ = res.images(text)

        self.assertEqual(images, ['materials/vgui/deep.vmt'])


class RadarTestCase(unittest.TestCase):
    def testItReadsTheOverviewMaterial(self):
        text = '"mymap"\n{\n"material" "overviews/mymap_radar"\n}\n'

        materials, radars = radar.images(text)

        self.assertEqual(materials, ['materials/overviews/mymap_radar.vmt'])
        self.assertIn('resource/overviews/mymap_radar.dds', radars)

    def testAMultiLevelMapNeedsOneImagePerFloor(self):
        text = ('"mymap"\n{\n"material" "overviews/mymap_radar"\n'
                '"verticalsections"\n{\n'
                '"default" { "AltitudeMax" "10000" }\n'
                '"lower" { "AltitudeMax" "100" }\n}\n}\n')

        _, radars = radar.images(text)

        self.assertIn('resource/overviews/mymap_default_radar.dds', radars)
        self.assertIn('resource/overviews/mymap_lower_radar.dds', radars)

    def testAnOverviewWithNoMaterialIsEmpty(self):
        materials, radars = radar.images('"mymap"\n{\n"scale" "5"\n}\n')

        self.assertEqual((materials, radars), ([], []))


class DetailVbspTestCase(unittest.TestCase):
    def testItReadsADetailModel(self):
        text = ('detail.vbsp\n{\n"grass"\n{\n"grassA"\n{\n'
                '"model" "models/props_foliage/grass.mdl"\n}\n}\n}\n')

        _, models = detailvbsp.references(text)

        self.assertEqual(models, ['models/props_foliage/grass.mdl'])

    def testSpriteCoordinatesAreNotAModel(self):
        # A sprite entry carries sheet coordinates, not a path.
        text = ('detail.vbsp\n{\n"grass"\n{\n"grassA"\n{\n'
                '"sprite" "0 0 256 256 512"\n}\n}\n}\n')

        _, models = detailvbsp.references(text)

        self.assertEqual(models, [])

    def testItReadsADetailMaterial(self):
        text = ('detail.vbsp\n{\n"grass"\n{\n'
                '"material" "detail/detailsprites"\n}\n}\n')

        materials, _ = detailvbsp.references(text)

        self.assertEqual(materials, ['materials/detail/detailsprites.vmt'])


if __name__ == '__main__':
    unittest.main()
