"""Tests for the output format.

bspzip reads this file positionally: line one is a name inside the map, line
two is where to get the bytes, and so on. Nothing validates it. An extra
blank line, a wrong separator, or a pair the wrong way round produces a map
that packs without complaint and is broken.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

import filelist  # noqa: E402

from report import Report  # noqa: E402


def asset(internal, external):
    return {'internal': internal, 'external': external}


class RenderTestCase(unittest.TestCase):
    def testItAlternatesInternalAndExternal(self):
        text = filelist.render([
            asset('materials/a.vmt', os.path.join('C:', 'content', 'a.vmt')),
            asset('models/b.mdl', os.path.join('C:', 'content', 'b.mdl')),
        ])

        lines = text.split('\r\n')

        self.assertEqual(lines[0], 'materials/a.vmt')
        self.assertEqual(lines[2], 'models/b.mdl')

    def testItUsesWindowsLineEndings(self):
        text = filelist.render([asset('a.vmt', 'C:\\a.vmt')])

        self.assertTrue(text.endswith('\r\n'))
        self.assertNotIn('\n\n', text)

    def testInternalPathsUseForwardSlashes(self):
        text = filelist.render([asset('materials\\a.vmt', 'C:\\a.vmt')])

        self.assertTrue(text.startswith('materials/a.vmt'))

    def testOrderIsPreserved(self):
        # Discovery order, so two runs of the same map produce identical
        # files and a diff between two lists means something.
        assets = [asset('c.vmt', 'C:\\c'), asset('a.vmt', 'C:\\a'),
                  asset('b.vmt', 'C:\\b')]

        text = filelist.render(assets)

        self.assertEqual(text.split('\r\n')[0:5:2], ['c.vmt', 'a.vmt', 'b.vmt'])

    def testNothingToPackIsAnEmptyFileNotABlankLine(self):
        self.assertEqual(filelist.render([]), '')


class WriteTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='autopak-filelist-')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def testItWritesWhatItRenders(self):
        path = os.path.join(self.directory, 'files.txt')

        count = filelist.write([asset('a.vmt', 'C:\\a.vmt')], path)

        with open(path, 'rb') as handle:
            raw = handle.read()

        self.assertEqual(count, 1)
        self.assertTrue(raw.startswith(b'a.vmt\r\n'))

    def testTheLineEndingsAreNotTranslatedTwice(self):
        # Opening in text mode without newline='' would turn each \r\n into
        # \r\r\n on Windows, which bspzip reads as an empty path.
        path = os.path.join(self.directory, 'files.txt')

        filelist.write([asset('a.vmt', 'C:\\a.vmt')], path)

        with open(path, 'rb') as handle:
            raw = handle.read()

        self.assertNotIn(b'\r\r', raw)

    def testItCreatesTheDirectory(self):
        path = os.path.join(self.directory, 'nested', 'files.txt')

        filelist.write([asset('a.vmt', 'C:\\a.vmt')], path)

        self.assertTrue(os.path.isfile(path))


class CheckTestCase(unittest.TestCase):
    def testALongPathIsWarnedAbout(self):
        report = Report(quiet=True)
        long_path = 'C:\\' + 'x' * filelist.MAX_PATH_LENGTH + '\\a.vmt'

        filelist.check([asset('a.vmt', long_path)], report)

        self.assertEqual(report.warning_count, 1)

    def testAnOrdinaryPathIsNot(self):
        report = Report(quiet=True)

        filelist.check([asset('a.vmt', 'C:\\content\\a.vmt')], report)

        self.assertEqual(report.warning_count, 0)

    def testANonAsciiInternalPathIsWarnedAbout(self):
        # The engine cannot load it, so saying nothing would hand the
        # mapper a map that silently fails for everyone else.
        report = Report(quiet=True)

        filelist.check([asset('materials/café.vmt', 'C:\\a.vmt')], report)

        self.assertEqual(report.warning_count, 1)


if __name__ == '__main__':
    unittest.main()
