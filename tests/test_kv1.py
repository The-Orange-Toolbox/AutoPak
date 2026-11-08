"""Tests for the shared KeyValues reader.

Six format parsers sit on this one module, so a bug here is a bug in all of
them at once. The cases below are the ones real Source content actually
produces: unquoted keys, comments in awkward places, conditional suffixes,
repeated keys, and files that simply stop in the middle.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from formats.kv1 import Node, parse  # noqa: E402


class TokenisingTestCase(unittest.TestCase):
    def testQuotedKeysAndValues(self):
        root = parse('"LightmappedGeneric"\n{\n\t"$basetexture" "metal/wall"\n}\n')
        shader = root.first_block('LightmappedGeneric')

        self.assertEqual(shader.pairs, [('$basetexture', 'metal/wall')])

    def testUnquotedKeysAndValues(self):
        # gameinfo.txt and many hand-written VMTs leave the quotes off.
        root = parse('LightmappedGeneric\n{\n\t$basetexture metal/wall\n}\n')
        shader = root.first_block('LightmappedGeneric')

        self.assertEqual(shader.pairs, [('$basetexture', 'metal/wall')])

    def testABackslashIsNotAnEscape(self):
        # This is the whole reason not to reuse a generic KV parser: most
        # material references in the game are written with backslashes.
        root = parse('x\n{\n\t"$basetexture" "metal\\wall"\n}\n')

        self.assertEqual(root.first_block('x').find_first('$basetexture'),
                         'metal\\wall')

    def testACommentIsIgnored(self):
        root = parse('x\n{\n\t// $basetexture "commented/out"\n'
                     '\t"$bumpmap" "metal/wall_n"\n}\n')

        self.assertEqual(root.first_block('x').pairs,
                         [('$bumpmap', 'metal/wall_n')])

    def testATrailingCommentAfterAValueIsIgnored(self):
        root = parse('x\n{\n\t"$basetexture" "metal/wall" // why not\n}\n')

        self.assertEqual(root.first_block('x').find_first('$basetexture'),
                         'metal/wall')

    def testASlashInsideAQuotedValueIsNotAComment(self):
        # Every path has slashes in it; only a doubled one starts a comment,
        # and never inside quotes.
        root = parse('x\n{\n\t"$basetexture" "metal//wall"\n}\n')

        self.assertEqual(root.first_block('x').find_first('$basetexture'),
                         'metal//wall')

    def testAConditionalSuffixIsDropped(self):
        root = parse('x\n{\n\t"$basetexture" "metal/wall" [$WIN32]\n}\n')

        self.assertEqual(root.first_block('x').pairs,
                         [('$basetexture', 'metal/wall')])

    def testAConditionalOnABlockIsDropped(self):
        root = parse('x\n{\n\t">=DX90" [$WIN32]\n\t{\n'
                     '\t\t"$bumpmap" "metal/wall_n"\n\t}\n}\n')

        self.assertEqual(root.first_block('x').find_first('$bumpmap'),
                         'metal/wall_n')


class StructureTestCase(unittest.TestCase):
    def testDuplicateKeysAreAllKept(self):
        # A soundscript block lists many waves under the same key. A dict
        # would keep one of them and silently drop the rest.
        root = parse('rndwave\n{\n\t"wave" "a.wav"\n\t"wave" "b.wav"\n'
                     '\t"wave" "c.wav"\n}\n')

        waves = [v for _, v in root.find_all(['wave'])]

        self.assertEqual(waves, ['a.wav', 'b.wav', 'c.wav'])

    def testOrderIsPreserved(self):
        root = parse('x\n{\n\t"a" "1"\n\t"b" "2"\n\t"c" "3"\n}\n')

        self.assertEqual([k for k, _ in root.first_block('x').pairs],
                         ['a', 'b', 'c'])

    def testNestedBlocksAreParsed(self):
        root = parse('x\n{\n\t"Proxies"\n\t{\n\t\t"TextureScroll"\n'
                     '\t\t{\n\t\t\t"texturescrollvar" "$basetexturetransform"\n'
                     '\t\t}\n\t}\n}\n')
        proxies = root.first_block('x').first_block('Proxies')

        self.assertIsInstance(proxies.first_block('TextureScroll'), Node)

    def testFindAllReachesIntoNestedBlocks(self):
        # A texture key inside Proxies or a DX-level block is still a
        # texture the map needs.
        root = parse('x\n{\n\t"$basetexture" "a"\n\t">=DX90"\n'
                     '\t{\n\t\t"$bumpmap" "b"\n\t}\n}\n')

        found = dict(root.find_all(['$basetexture', '$bumpmap']))

        self.assertEqual(found, {'$basetexture': 'a', '$bumpmap': 'b'})

    def testFindAllIsCaseInsensitive(self):
        root = parse('x\n{\n\t"$BaseTexture" "metal/wall"\n}\n')

        self.assertEqual([v for _, v in root.find_all(['$basetexture'])],
                         ['metal/wall'])

    def testFindAllDoesNotMatchBlockNames(self):
        # A block named 'material' is not a material reference.
        root = parse('x\n{\n\t"material"\n\t{\n\t\t"a" "1"\n\t}\n}\n')

        self.assertEqual(root.find_all(['material']), [])

    def testBaseDirectivesAreSurfaced(self):
        # Resolving these needs search paths, so the reader only reports
        # them and leaves the lookup to the caller.
        root = parse('#base "shared.res"\n#base "other.res"\nx\n{\n}\n')

        self.assertEqual(root.bases, ['shared.res', 'other.res'])


class MalformedInputTestCase(unittest.TestCase):
    def testAnUnclosedBlockIsReportedNotRaised(self):
        root = parse('x\n{\n\t"$basetexture" "metal/wall"\n')

        self.assertTrue(root.truncated)
        self.assertEqual(root.first_block('x').find_first('$basetexture'),
                         'metal/wall')

    def testWhatWasReadBeforeTheBreakIsKept(self):
        # The point of not raising: a truncated soundscript still tells us
        # about every wave above the break.
        root = parse('a\n{\n\t"wave" "one.wav"\n}\nb\n{\n\t"wave" "two.wav"\n')

        self.assertEqual([v for _, v in root.find_all(['wave'])],
                         ['one.wav', 'two.wav'])

    def testAnUnterminatedQuoteDoesNotSwallowTheRestOfTheFile(self):
        root = parse('x\n{\n\t"$basetexture" "metal/wall\n'
                     '\t"$bumpmap" "metal/wall_n"\n}\n')

        self.assertEqual(root.first_block('x').find_first('$bumpmap'),
                         'metal/wall_n')

    def testAStrayCloseBraceIsIgnored(self):
        root = parse('}\nx\n{\n\t"$basetexture" "metal/wall"\n}\n')

        self.assertEqual(root.first_block('x').find_first('$basetexture'),
                         'metal/wall')

    def testAnEmptyFileParsesToNothing(self):
        root = parse('')

        self.assertEqual(root.pairs, [])
        self.assertFalse(root.truncated)

    def testAFileOfOnlyCommentsParsesToNothing(self):
        root = parse('// nothing here\n// nor here\n')

        self.assertEqual(root.pairs, [])


if __name__ == '__main__':
    unittest.main()
