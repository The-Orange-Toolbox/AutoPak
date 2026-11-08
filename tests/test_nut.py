"""Tests for reading VScripts.

A script can precache content named nowhere else in the map, and it can also
tell a packer outright about content no scanner could work out. Both matter:
the first is the commonest way a scripted map ships broken, and the second
is the escape hatch for when it does.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from formats import nut  # noqa: E402


class CallTestCase(unittest.TestCase):
    def testIncludeScript(self):
        found = nut.references('IncludeScript("shared/util.nut")')

        self.assertEqual(found.scripts, ['scripts/vscripts/shared/util.nut'])

    def testDoIncludeScript(self):
        found = nut.references('DoIncludeScript("shared/util", null)')

        self.assertEqual(found.scripts, ['scripts/vscripts/shared/util.nut'])

    def testAScriptNamedWithoutItsExtensionStillResolves(self):
        # Squirrel does not require the extension and scripts often omit it.
        found = nut.references('IncludeScript("util")')

        self.assertEqual(found.scripts, ['scripts/vscripts/util.nut'])

    def testPrecacheModel(self):
        found = nut.references('self.PrecacheModel("models/custom/x.mdl")')

        self.assertEqual(found.models, ['models/custom/x.mdl'])

    def testPrecacheSound(self):
        found = nut.references('self.PrecacheSound("custom/beep.wav")')

        self.assertEqual(found.sounds, ['sound/custom/beep.wav'])

    def testACallOnAnObjectIsStillRead(self):
        found = nut.references('EntIndexToHScript(1).PrecacheModel("a.mdl")')

        self.assertEqual(found.models, ['a.mdl'])

    def testSeveralCallsOnOneLine(self):
        found = nut.references(
            'PrecacheModel("a.mdl"); PrecacheSound("b.wav")')

        self.assertEqual(found.models, ['a.mdl'])
        self.assertEqual(found.sounds, ['sound/b.wav'])

    def testACallInACommentIsIgnored(self):
        found = nut.references('// PrecacheModel("a.mdl")')

        self.assertEqual(found.models, [])

    def testCodeBeforeACommentIsStillRead(self):
        found = nut.references('PrecacheModel("a.mdl") // why not')

        self.assertEqual(found.models, ['a.mdl'])


class HintTestCase(unittest.TestCase):
    def testACompilePalIncludeFile(self):
        # The portable spelling, and the one scripts in the wild carry.
        found = nut.references(
            '// !CompilePal::IncludeFile("materials/custom/x.vmt")')

        self.assertEqual(found.files, ['materials/custom/x.vmt'])

    def testAnAutoPakIncludeFile(self):
        found = nut.references(
            '// !AutoPak::IncludeFile("materials/custom/x.vmt")')

        self.assertEqual(found.files, ['materials/custom/x.vmt'])

    def testAnIncludeDirectory(self):
        found = nut.references(
            '// !CompilePal::IncludeDirectory("materials/custom/set")')

        self.assertEqual(found.directories, ['materials/custom/set'])

    def testATrailingSlashOnADirectoryIsIgnored(self):
        found = nut.references(
            '// !CompilePal::IncludeDirectory("materials/custom/set/")')

        self.assertEqual(found.directories, ['materials/custom/set'])

    def testHintsAreCaseInsensitive(self):
        found = nut.references(
            '// !compilepal::includefile("materials/x.vmt")')

        self.assertEqual(found.files, ['materials/x.vmt'])

    def testAnOrdinaryCommentIsNotAHint(self):
        found = nut.references('// this is just a note')

        self.assertEqual((found.files, found.directories), ([], []))

    def testAHintAfterCodeIsStillRead(self):
        found = nut.references(
            'local x = 1 // !CompilePal::IncludeFile("materials/x.vmt")')

        self.assertEqual(found.files, ['materials/x.vmt'])


class FileTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='autopak-nut-')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def testItReadsFromDisk(self):
        path = os.path.join(self.directory, 'script.nut')
        with open(path, 'w') as handle:
            handle.write('PrecacheModel("models/a.mdl")\n')

        self.assertEqual(nut.dependencies(path).models, ['models/a.mdl'])

    def testAnUnreadableFileIsEmpty(self):
        found = nut.dependencies(os.path.join(self.directory, 'no.nut'))

        self.assertEqual(found.models, [])


if __name__ == '__main__':
    unittest.main()
