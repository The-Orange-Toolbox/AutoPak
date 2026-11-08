"""Tests for model dependencies.

The material rules are the intricate part. A model names directories and
bare texture names separately and leaves the engine to try the combinations,
and skin families then narrow which of those names are actually reachable.
Getting the narrowing wrong is quiet in both directions: too wide and the
download carries materials nothing uses, too narrow and a prop placed with
an unusual skin is untextured for everyone but the author.

The model object is faked here. The point is the rules, not ValveMDL's
ability to read a header, and a synthetic ``studiohdr_t`` would test the
fixture more than the code.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from formats import model, phy  # noqa: E402


class FakeThing(object):
    def __init__(self, **fields):
        self.__dict__.update(fields)


class FakeMdl(object):
    """Just the surface :mod:`formats.model` reads."""

    def __init__(self, cdtextures=None, textures=None, skins=None,
                 meshes=None, includemodels=None):
        self.cdtextures = cdtextures if cdtextures is not None else ['models/']
        self.textures = [FakeThing(name=n) for n in (textures or [])]
        self.skins = skins
        self.meshes = [FakeThing(material=m) for m in (meshes or [])]
        self.includemodels = [FakeThing(label='', name=n)
                              for n in (includemodels or [])]
        self.header = None


class SiblingTestCase(unittest.TestCase):
    def testTheExtensionIsReplacedNotAppended(self):
        found = model.siblings('models/props/x.mdl')

        self.assertIn('models/props/x.vvd', found)
        self.assertNotIn('models/props/x.mdl.vvd', found)

    def testItAsksForEveryFlavourOfMesh(self):
        # Which one loads depends on the player's hardware, so the pack
        # has to carry them all.
        found = model.siblings('models/props/x.mdl')

        for extension in ('.dx80.vtx', '.dx90.vtx', '.sw.vtx', '.vtx'):
            self.assertIn('models/props/x' + extension, found)

    def testTheModelItselfIsNotItsOwnSibling(self):
        self.assertNotIn('models/props/x.mdl',
                         model.siblings('models/props/x.mdl'))

    def testSoftwareMeshesCanBeSkipped(self):
        found = model.siblings('models/props/x.mdl', pack_swvtx=False)

        self.assertNotIn('models/props/x.sw.vtx', found)
        self.assertIn('models/props/x.dx90.vtx', found)


class MaterialTestCase(unittest.TestCase):
    def testItCrossesDirectoriesWithNames(self):
        # The engine tries every combination until one exists, so AutoPak
        # has to offer every combination too.
        mdl = FakeMdl(cdtextures=['models/a/', 'models/b/'],
                      textures=['wall', 'floor'])

        self.assertEqual(model.materials(mdl), [
            'materials/models/a/wall.vmt',
            'materials/models/a/floor.vmt',
            'materials/models/b/wall.vmt',
            'materials/models/b/floor.vmt',
        ])

    def testWindowsSeparatorsInTheSearchPathAreNormalised(self):
        mdl = FakeMdl(cdtextures=['models\\props_aquatic\\'],
                      textures=['pipes01'])

        self.assertEqual(model.materials(mdl),
                         ['materials/models/props_aquatic/pipes01.vmt'])

    def testASearchPathWithNoTrailingSeparatorStillJoins(self):
        mdl = FakeMdl(cdtextures=['models/props'], textures=['wall'])

        self.assertEqual(model.materials(mdl),
                         ['materials/models/props/wall.vmt'])

    def testAModelWithNoSearchPathStillNamesItsTextures(self):
        mdl = FakeMdl(cdtextures=[], textures=['wall'])

        self.assertEqual(model.materials(mdl), ['materials/wall.vmt'])


class SkinTestCase(unittest.TestCase):
    def mdl(self):
        # Three textures, three skin families, one mesh using material 0 --
        # the shape of every reskinnable prop in the game.
        return FakeMdl(cdtextures=['models/'],
                       textures=['red', 'blue', 'green'],
                       skins=[[0, 1, 2], [1, 1, 2], [2, 1, 2]],
                       meshes=[0])

    def testWithNoSkinInformationEverythingIsPacked(self):
        # Over-packing is a much better failure than missing a material,
        # so this is the deliberate fallback.
        self.assertEqual(model.texture_names(self.mdl(), None),
                         ['red', 'blue', 'green'])

    def testOneSkinNarrowsToOneTexture(self):
        self.assertEqual(model.texture_names(self.mdl(), {0}), ['red'])
        self.assertEqual(model.texture_names(self.mdl(), {2}), ['green'])

    def testSeveralSkinsGiveTheUnion(self):
        self.assertEqual(model.texture_names(self.mdl(), {0, 2}),
                         ['red', 'green'])

    def testASkinTheModelDoesNotHaveFallsBackToTheFirst(self):
        # The engine does the same, so a prop placed with a bad skin index
        # renders with skin 0 rather than nothing.
        self.assertEqual(model.texture_names(self.mdl(), {99}), ['red'])

    def testOnlyMaterialsTheMeshesUseAreConsidered(self):
        # The skin table is as wide as the texture list, but a mesh only
        # ever refers to one column of it. Packing the whole row is what
        # makes a fifteen-skin model pack fifteen materials for nothing.
        mdl = FakeMdl(cdtextures=['models/'],
                      textures=['a', 'b', 'c'],
                      skins=[[0, 1, 2]],
                      meshes=[1])

        self.assertEqual(model.texture_names(mdl, {0}), ['b'])

    def testAModelWithNoMeshInformationPacksEverything(self):
        mdl = FakeMdl(cdtextures=['models/'], textures=['a', 'b'],
                      skins=[[0, 1]], meshes=[])

        self.assertEqual(model.texture_names(mdl, {0}), ['a', 'b'])


class IncludeModelTestCase(unittest.TestCase):
    def testIncludedModelsAreReported(self):
        # Usually shared animation sets. The engine loads them alongside.
        mdl = FakeMdl(includemodels=['models/player/shared_anims.mdl'])

        self.assertEqual(model.include_models(mdl),
                         ['models/player/shared_anims.mdl'])

    def testTheirPathsAreNormalised(self):
        mdl = FakeMdl(includemodels=['models\\Player\\Anims.mdl'])

        self.assertEqual(model.include_models(mdl),
                         ['models/player/anims.mdl'])


class PhyTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='autopak-phy-')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def collision(self, text, solids=1):
        """A structurally valid .phy: header, solids, then the text blob.

        The filler is packed floats rather than random bytes on purpose.
        Random data occasionally spells an identifier followed by a brace,
        which made this test disagree with itself between runs -- and that
        flakiness was pointing at a real weakness in how the text used to
        be located.
        """
        import struct

        body = b''.join(struct.pack('<f', n * 0.5) for n in range(16))
        data = struct.pack('<iiii', 16, 0x59485056, solids, 0)
        for _ in range(solids):
            data += struct.pack('<i', len(body)) + body

        return data + text.encode('latin-1')

    def testItFindsTheModelsAThingBreaksInto(self):
        # Nothing else in the map names these. A crate whose gibs are not
        # packed breaks into ERROR signs for everyone but the author.
        data = self.collision(
            'solid { index 0 }\n'
            'break\n{\n"model" "props_debris/wood_board01a"\n'
            '"health" "10"\n}\n')

        self.assertEqual(phy.gibs(data),
                         ['models/props_debris/wood_board01a.mdl'])

    def testItFindsRagdollsToo(self):
        data = self.collision('break\n{\n"ragdoll" "props/dead_body"\n}\n')

        self.assertEqual(phy.gibs(data), ['models/props/dead_body.mdl'])

    def testAnExtensionAlreadyPresentIsNotDoubled(self):
        data = self.collision(
            'break\n{\n"model" "props_debris/board.mdl"\n}\n')

        self.assertEqual(phy.gibs(data), ['models/props_debris/board.mdl'])

    def testAFullPathIsNotPrefixedTwice(self):
        data = self.collision(
            'break\n{\n"model" "models/props_debris/board.mdl"\n}\n')

        self.assertEqual(phy.gibs(data), ['models/props_debris/board.mdl'])

    def testSeveralGibsAreAllFound(self):
        data = self.collision(
            'break\n{\n"model" "debris/a"\n}\n'
            'break\n{\n"model" "debris/b"\n}\n')

        self.assertEqual(phy.gibs(data),
                         ['models/debris/a.mdl', 'models/debris/b.mdl'])

    def testACollisionModelWithNoGibsGivesNothing(self):
        data = self.collision('solid { index 0 }\n')

        self.assertEqual(phy.gibs(data), [])

    def testPureBinaryWithNoTextGivesNothing(self):
        self.assertEqual(phy.gibs(b'\x00\x01\x02\x03' * 32), [])

    def testAnUnreadableFileIsEmptyNotAnError(self):
        self.assertEqual(
            phy.dependencies(os.path.join(self.directory, 'nope.phy')), [])


if __name__ == '__main__':
    unittest.main()
