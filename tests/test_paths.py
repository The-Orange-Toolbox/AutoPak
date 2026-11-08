"""Tests for path normalisation.

These are the rules that decide whether AutoPak looks for a file under the
name it actually has on disk. Every one of them exists because some tool in
the Source content pipeline spells paths its own way, so the cases below are
real spellings, not invented edge cases.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from paths import (internal_path, replace_extension, sound_path,  # noqa: E402
                   unpatch_wvt, vmt_path)


class InternalPathTestCase(unittest.TestCase):
    def testBackslashesBecomeForwardSlashes(self):
        # Model headers and .phy blobs are written with Windows separators.
        self.assertEqual(internal_path('models\\props\\x.mdl'),
                         'models/props/x.mdl')

    def testAParentSegmentIsCollapsed(self):
        # Real .res files do this, and the engine resolves it.
        self.assertEqual(internal_path('materials/vgui/../hud/logos/spray.vmt'),
                         'materials/hud/logos/spray.vmt')

    def testAPlainPathIsLeftAlone(self):
        self.assertEqual(internal_path('materials/metal/wall.vmt'),
                         'materials/metal/wall.vmt')


class VmtPathTestCase(unittest.TestCase):
    def testItStripsTheMaterialsPrefix(self):
        self.assertEqual(vmt_path('materials/metal/wall'), 'metal/wall')

    def testItStripsAVmtSuffix(self):
        self.assertEqual(vmt_path('metal/wall.vmt'), 'metal/wall')

    def testItStripsAVtfSuffix(self):
        self.assertEqual(vmt_path('metal/wall.vtf'), 'metal/wall')

    def testItStripsBothPrefixAndSuffix(self):
        self.assertEqual(vmt_path('materials\\metal\\wall.vtf'), 'metal/wall')

    def testItTrimsSurroundingWhitespaceAndSlashes(self):
        # Hand-written VMTs are full of these.
        self.assertEqual(vmt_path('  /metal/wall/  '), 'metal/wall')

    def testItCollapsesDuplicateSlashes(self):
        self.assertEqual(vmt_path('metal//wall'), 'metal/wall')

    def testThePrefixIsStrippedCaseInsensitively(self):
        self.assertEqual(vmt_path('Materials/Metal/Wall.VMT'),
                         'Metal/Wall')

    def testAStemWithoutEitherIsUnchanged(self):
        self.assertEqual(vmt_path('metal/wall'), 'metal/wall')

    def testADotInADirectoryNameSurvives(self):
        # Only a trailing .vmt/.vtf is a suffix; 'v2.0' is a folder.
        self.assertEqual(vmt_path('metal/v2.0/wall'), 'metal/v2.0/wall')


class SoundPathTestCase(unittest.TestCase):
    def testItAddsTheSoundPrefix(self):
        self.assertEqual(sound_path('ambient/wind.wav'),
                         'sound/ambient/wind.wav')

    def testItStripsAStreamedMarker(self):
        # '*' means stream from disk rather than precache into memory.
        self.assertEqual(sound_path('*music/theme.mp3'),
                         'sound/music/theme.mp3')

    def testItStripsEveryPrecachePrefix(self):
        self.assertEqual(sound_path('#@>^ambient/wind.wav'),
                         'sound/ambient/wind.wav')

    def testItStripsTrailingSpaces(self):
        self.assertEqual(sound_path('ambient/wind.wav  '),
                         'sound/ambient/wind.wav')

    def testBackslashesAreNormalised(self):
        self.assertEqual(sound_path('ambient\\wind.wav'),
                         'sound/ambient/wind.wav')


class UnpatchWvtTestCase(unittest.TestCase):
    def testAGeneratedBlendPatchMapsBackToItsOriginal(self):
        # vbsp writes these into the map's own pakfile; what needs packing
        # is the material the mapper actually made.
        self.assertEqual(
            unpatch_wvt('materials/maps/cp_vanguard/nature/blend01_wvt_patch.vmt'),
            'materials/nature/blend01.vmt')

    def testAnOrdinaryMaterialIsUnchanged(self):
        self.assertEqual(unpatch_wvt('materials/nature/blend01.vmt'),
                         'materials/nature/blend01.vmt')

    def testAMaterialUnderMapsThatIsNotAPatchIsUnchanged(self):
        self.assertEqual(unpatch_wvt('materials/maps/cp_vanguard/cubemap.vmt'),
                         'materials/maps/cp_vanguard/cubemap.vmt')


class ReplaceExtensionTestCase(unittest.TestCase):
    def testItReplacesRatherThanAppends(self):
        self.assertEqual(replace_extension('models/props/x.mdl', '.vvd'),
                         'models/props/x.vvd')

    def testItHandlesAMultiPartExtension(self):
        self.assertEqual(replace_extension('models/props/x.mdl', '.dx90.vtx'),
                         'models/props/x.dx90.vtx')

    def testADotInADirectoryNameIsNotAnExtension(self):
        self.assertEqual(replace_extension('models/v2.0/x', '.vvd'),
                         'models/v2.0/x.vvd')


if __name__ == '__main__':
    unittest.main()
