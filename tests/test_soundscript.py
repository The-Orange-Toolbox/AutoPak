"""Tests for soundscripts and soundscapes.

Read line by line rather than through the keyvalues reader, because these
are hand-edited more than any other format in Source and an unbalanced brace
in one is routine. The tests below pin that tolerance: a file that is
malformed halfway down still has to yield the sounds above and below the
mistake.
"""

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from formats import soundscript  # noqa: E402


class WaveTestCase(unittest.TestCase):
    def testASingleWave(self):
        text = 'Ambient.Wind\n{\n"wave" "ambient/wind/wind1.wav"\n}\n'

        self.assertEqual(soundscript.waves(text),
                         ['sound/ambient/wind/wind1.wav'])

    def testEveryWaveInAnRndwaveBlock(self):
        # rndwave needs no special handling: its inner lines start with
        # 'wave' like any other.
        text = ('Ambient.Wind\n{\n"rndwave"\n{\n'
                '"wave" "ambient/a.wav"\n'
                '"wave" "ambient/b.wav"\n}\n}\n')

        self.assertEqual(soundscript.waves(text),
                         ['sound/ambient/a.wav', 'sound/ambient/b.wav'])

    def testUnquotedWavesAreRead(self):
        text = 'Ambient.Wind\n{\nwave ambient/wind.wav\n}\n'

        self.assertEqual(soundscript.waves(text), ['sound/ambient/wind.wav'])

    def testAPrecachePrefixIsStripped(self):
        text = '"wave" "*music/theme.mp3"\n'

        self.assertEqual(soundscript.waves(text), ['sound/music/theme.mp3'])

    def testAnUnbalancedBraceDoesNotLoseTheRest(self):
        # The whole reason this is a line scanner. A structural parse would
        # drop everything below the mistake.
        text = ('A\n{\n"wave" "a.wav"\n'
                'B\n{\n"wave" "b.wav"\n}\n'
                'C\n{\n"wave" "c.wav"\n}\n')

        self.assertEqual(soundscript.waves(text),
                         ['sound/a.wav', 'sound/b.wav', 'sound/c.wav'])

    def testAKeyThatMerelyStartsWithWaveIsNotAWave(self):
        text = '"wavelength" "500"\n"wave" "real.wav"\n'

        self.assertEqual(soundscript.waves(text), ['sound/real.wav'])

    def testTheSameWaveTwiceIsReportedOnce(self):
        text = '"wave" "a.wav"\n"wave" "a.wav"\n'

        self.assertEqual(soundscript.waves(text), ['sound/a.wav'])

    def testAWaveWithNoValueIsSkipped(self):
        self.assertEqual(soundscript.waves('"wave"\n'), [])

    def testAFileWithNoSoundsIsEmpty(self):
        self.assertEqual(soundscript.waves('Ambient.Wind\n{\n"channel" "1"\n}'),
                         [])


class DependenciesTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='autopak-soundscript-')

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def testItReadsFromDisk(self):
        path = os.path.join(self.directory, 'soundscapes_map.txt')
        with open(path, 'w') as handle:
            handle.write('"wave" "ambient/wind.wav"\n')

        self.assertEqual(soundscript.dependencies(path),
                         ['sound/ambient/wind.wav'])

    def testAnUnreadableFileIsEmpty(self):
        self.assertEqual(
            soundscript.dependencies(os.path.join(self.directory, 'no.txt')),
            [])


if __name__ == '__main__':
    unittest.main()
