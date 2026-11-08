"""Tests for the files a map has by convention.

Nothing in a BSP points at its own soundscape script or its navigation
mesh; the engine finds them by name. That makes this the one pass that
guesses, so the tests are as much about what it does *not* pick up.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

import utilityfiles  # noqa: E402

from content import build  # noqa: E402


class ProbeTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='autopak-utility-')
        self.index, _ = build(directories=[self.root], use_vpk=False)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, internal):
        path = os.path.join(self.root, internal.replace('/', os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as handle:
            handle.write('x')
        return path

    def probe(self, mapname='mymap', **kwargs):
        return utilityfiles.probe(self.index, mapname, **kwargs)

    def packed(self, found):
        return [internal for _, internal, _, _ in found]

    def testAMapWithNoneOfThemFindsNothing(self):
        self.assertEqual(self.probe(), [])

    def testTheSoundscapeScript(self):
        self.write('scripts/soundscapes_mymap.txt')

        self.assertEqual(self.packed(self.probe()),
                         ['scripts/soundscapes_mymap.txt'])

    def testTheOtherSoundscapeSpelling(self):
        self.write('scripts/soundscapes_mymap.vsc')

        self.assertEqual(self.packed(self.probe()),
                         ['scripts/soundscapes_mymap.vsc'])

    def testTheNavigationMesh(self):
        self.write('maps/mymap.nav')

        self.assertEqual(self.packed(self.probe()), ['maps/mymap.nav'])

    def testARenamedNavIsPackedUnderTheGenericName(self):
        # So it still loads if the map file is renamed between versions.
        self.write('maps/mymap.nav')

        found = self.probe(rename_nav=True)

        self.assertEqual(self.packed(found), [utilityfiles.EMBED_NAV])
        self.assertEqual(found[0][0], 'maps/mymap.nav')

    def testTheParticleManifest(self):
        self.write('maps/mymap_particles.txt')

        self.assertEqual(self.packed(self.probe()),
                         ['maps/mymap_particles.txt'])

    def testARenamedManifest(self):
        self.write('maps/mymap_particles.txt')

        found = self.probe(rename_particle_manifest=True)

        self.assertEqual(self.packed(found),
                         ['maps/' + utilityfiles.RENAMED_MANIFEST])

    def testLevelSounds(self):
        self.write('maps/mymap_level_sounds.txt')

        self.assertEqual(self.packed(self.probe()),
                         ['maps/mymap_level_sounds.txt'])

    def testAnMvmMapsLevelSoundsGoInAtTheFixedPath(self):
        # Mann-vs-Machine reads these from one place regardless of the map
        # name, so packing it under the map's name does nothing at all.
        self.write('maps/mvm_mymap_level_sounds.txt')

        found = self.probe(mapname='mvm_mymap')

        self.assertEqual(self.packed(found),
                         ['scripts/mvm_level_sound_tweaks.txt'])

    def testTheOverviewDefinitionAndMaterial(self):
        self.write('resource/overviews/mymap.txt')
        self.write('materials/overviews/mymap.vmt')

        self.assertEqual(sorted(self.packed(self.probe())),
                         ['materials/overviews/mymap.vmt',
                          'resource/overviews/mymap.txt'])

    def testTheRoundInfoPanel(self):
        self.write('resource/roundinfo/mymap.res')

        self.assertEqual(self.packed(self.probe()),
                         ['resource/roundinfo/mymap.res'])

    def testLanguageFilesAreFound(self):
        self.write('maps/mymap_english.txt')

        self.assertEqual(self.packed(self.probe()),
                         ['maps/mymap_english.txt'])

    def testTheParticleManifestIsNotMistakenForALanguageFile(self):
        # Both match 'maps/<mapname>*.txt'; packing the manifest twice
        # under two kinds would be harmless but confusing, and the
        # level sounds file has a genuinely different destination.
        self.write('maps/mymap_particles.txt')
        self.write('maps/mymap_level_sounds.txt')

        packed = self.packed(self.probe())

        self.assertEqual(sorted(packed), ['maps/mymap_level_sounds.txt',
                                          'maps/mymap_particles.txt'])

    def testAnotherMapsFilesAreNotPickedUp(self):
        self.write('maps/othermap.nav')
        self.write('scripts/soundscapes_othermap.txt')

        self.assertEqual(self.probe(), [])

    def testEverythingFoundIsSpeculative(self):
        # Most maps have none of these, so their absence must never reach
        # the missing report.
        self.write('maps/mymap.nav')

        _, _, _, origin = self.probe()[0]

        self.assertTrue(origin)


if __name__ == '__main__':
    unittest.main()
