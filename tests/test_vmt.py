"""Tests for reading materials.

Materials are where a pack is usually incomplete. A texture key nobody
thought of, a ``Patch`` chain followed only one level, a value that names a
render target rather than a file -- each one either drops content the map
needs or adds a line to the missing report that should not be there.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

import keys  # noqa: E402

from formats import vmt  # noqa: E402


def material(body, shader='LightmappedGeneric'):
    return '"{}"\n{{\n{}\n}}\n'.format(shader, body)


class TextureTestCase(unittest.TestCase):
    def testABaseTexture(self):
        text = material('"$basetexture" "metal/wall"')

        self.assertEqual(vmt.textures(text), ['materials/metal/wall.vtf'])

    def testEveryTextureKeyIsRecognised(self):
        # Table-driven over the whole ported list: a key silently dropped
        # here is content silently missing from every map that uses it.
        for key in keys.TEXTURE_KEYS:
            text = material('"{}" "some/texture"'.format(key))

            self.assertIn('materials/some/texture.vtf', vmt.textures(text),
                          'not recognised: ' + key)

    def testKeysAreMatchedCaseInsensitively(self):
        text = material('"$BaseTexture" "metal/wall"')

        self.assertEqual(vmt.textures(text), ['materials/metal/wall.vtf'])

    def testEnvmapAlsoAsksForTheHdrVariant(self):
        # A cubemap material usually ships both, and which one loads
        # depends on the player's settings.
        text = material('"$envmap" "cubemaps/office"')

        self.assertEqual(vmt.textures(text),
                         ['materials/cubemaps/office.vtf',
                          'materials/cubemaps/office.hdr.vtf'])

    def testOnlyEnvmapAsksForAnHdrVariant(self):
        text = material('"$bumpmap" "metal/wall_n"')

        self.assertEqual(vmt.textures(text), ['materials/metal/wall_n.vtf'])

    def testEnvCubemapIsNotAFile(self):
        # The engine builds this from the map's own cubemaps. Asking for it
        # on disk would put a false line in the missing report on nearly
        # every map in existence.
        text = material('"$envmap" "env_cubemap"')

        self.assertEqual(vmt.textures(text), [])

    def testARenderTargetIsNotAFile(self):
        text = material('"$basetexture" "_rt_Camera"')

        self.assertEqual(vmt.textures(text), [])

    def testATextureInsideAProxyBlockIsFound(self):
        text = material('"$basetexture" "metal/wall"\n'
                        '"Proxies"\n{\n"TextureScroll"\n{\n'
                        '"$detail" "metal/scroll"\n}\n}')

        self.assertIn('materials/metal/scroll.vtf', vmt.textures(text))

    def testATextureInsideADxLevelBlockIsFound(self):
        # The engine picks one branch; the pack needs both, because the
        # download has to work for players on either setting.
        text = material('">=DX90"\n{\n"$bumpmap" "metal/wall_n"\n}')

        self.assertIn('materials/metal/wall_n.vtf', vmt.textures(text))

    def testPathsAreNormalised(self):
        text = material('"$basetexture" "materials\\\\metal\\\\wall.vtf"')

        self.assertEqual(vmt.textures(text), ['materials/metal/wall.vtf'])

    def testTheSameTextureTwiceIsReportedOnce(self):
        text = material('"$basetexture" "metal/wall"\n'
                        '"$detail" "metal/wall"')

        self.assertEqual(vmt.textures(text), ['materials/metal/wall.vtf'])

    def testAnEmptyValueIsIgnored(self):
        text = material('"$basetexture" ""')

        self.assertEqual(vmt.textures(text), [])


class ReferenceTestCase(unittest.TestCase):
    def testAPatchIncludeIsFollowed(self):
        # This is how most model materials are written: a Patch naming a
        # shared parent, which itself names the textures.
        text = ('"Patch"\n{\n"include" "materials/models/base.vmt"\n'
                '"replace"\n{\n"$basetexture" "models/red"\n}\n}\n')

        self.assertEqual(vmt.references(text), ['materials/models/base.vmt'])

    def testTheReplaceBlockStillContributesTextures(self):
        text = ('"Patch"\n{\n"include" "materials/models/base.vmt"\n'
                '"replace"\n{\n"$basetexture" "models/red"\n}\n}\n')

        self.assertEqual(vmt.textures(text), ['materials/models/red.vtf'])

    def testEveryMaterialKeyIsRecognised(self):
        for key in keys.MATERIAL_KEYS:
            text = material('"{}" "some/other"'.format(key))

            self.assertIn('materials/some/other.vmt', vmt.references(text),
                          'not recognised: ' + key)

    def testABottomMaterialIsFollowed(self):
        # Water materials name the surface below them.
        text = material('"$bottommaterial" "nature/water_bottom"',
                        shader='Water')

        self.assertEqual(vmt.references(text),
                         ['materials/nature/water_bottom.vmt'])


class DependenciesTestCase(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.directory = tempfile.mkdtemp(prefix='autopak-vmt-')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def write(self, text):
        path = os.path.join(self.directory, 'test.vmt')
        with open(path, 'w') as handle:
            handle.write(text)
        return path

    def testItReadsBothKindsOfDependency(self):
        path = self.write('"Patch"\n{\n"include" "materials/base.vmt"\n'
                          '"replace"\n{\n"$basetexture" "red"\n}\n}\n')

        textures, references, truncated = vmt.dependencies(path)

        self.assertEqual(textures, ['materials/red.vtf'])
        self.assertEqual(references, ['materials/base.vmt'])
        self.assertFalse(truncated)

    def testATruncatedMaterialIsFlaggedButStillRead(self):
        path = self.write('"LightmappedGeneric"\n{\n"$basetexture" "red"\n')

        textures, _, truncated = vmt.dependencies(path)

        self.assertEqual(textures, ['materials/red.vtf'])
        self.assertTrue(truncated)

    def testAnUnreadableFileIsEmptyNotAnError(self):
        textures, references, _ = vmt.dependencies(
            os.path.join(self.directory, 'nope.vmt'))

        self.assertEqual((textures, references), ([], []))


if __name__ == '__main__':
    unittest.main()
