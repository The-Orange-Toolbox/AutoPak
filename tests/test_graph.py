"""Tests for the dependency walk.

Three properties matter here and none of them is visible from the output of
a successful run:

* it terminates, including through a cycle and including through content
  that does not exist;
* it stops at content the map does not own, because a stock asset's
  dependencies are stock too;
* a guess that resolves nowhere stays out of the missing report, or the
  report is noise.

The resolver is stubbed so these can be tested without a filesystem.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

import graph  # noqa: E402

from content import EMBEDDED, MISSING, PACKED, STOCK  # noqa: E402
from report import Report  # noqa: E402


class FakeIndex(object):
    """A resolver driven by a dict, so tests can state the world outright."""

    def __init__(self, statuses):
        self.statuses = statuses
        self.asked = []

    def resolve(self, internal):
        self.asked.append(internal)
        status = self.statuses.get(internal, MISSING)
        external = '/content/' + internal if status == PACKED else None
        return (status, external, False)


class WalkTestCase(unittest.TestCase):
    def build(self, statuses, edges=None):
        """A pack list whose materials point at whatever *edges* says."""
        self.index = FakeIndex(statuses)
        packlist = graph.PackList(self.index, Report(quiet=True))

        edges = edges or {}

        def expand(packlist, internal, external, extra):
            for target in edges.get(internal, ()):
                packlist.add(target, graph.KIND_MATERIAL, internal)

        self.expanders = {graph.KIND_MATERIAL: expand}
        return packlist

    def testAPackedAssetIsExpanded(self):
        packlist = self.build({'a.vmt': PACKED, 'b.vmt': PACKED},
                              edges={'a.vmt': ['b.vmt']})
        packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')

        packlist.run(self.expanders)

        self.assertEqual([a['internal'] for a in packlist.packed()],
                         ['a.vmt', 'b.vmt'])

    def testACycleTerminates(self):
        packlist = self.build({'a.vmt': PACKED, 'b.vmt': PACKED},
                              edges={'a.vmt': ['b.vmt'], 'b.vmt': ['a.vmt']})
        packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')

        packlist.run(self.expanders)

        self.assertEqual(len(packlist.assets), 2)

    def testASelfReferenceTerminates(self):
        packlist = self.build({'a.vmt': PACKED},
                              edges={'a.vmt': ['a.vmt']})
        packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')

        packlist.run(self.expanders)

        self.assertEqual(len(packlist.assets), 1)

    def testACycleThroughAMissingFileTerminates(self):
        # Presence in the visited set, not the outcome, is what stops the
        # walk -- so this has to end just as readily.
        packlist = self.build({'a.vmt': PACKED},
                              edges={'a.vmt': ['gone.vmt'],
                                     'gone.vmt': ['a.vmt']})
        packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')

        packlist.run(self.expanders)

        self.assertEqual(len(packlist.assets), 2)

    def testAStockAssetIsNotExpanded(self):
        # The whole efficiency and correctness argument: a stock material's
        # textures are stock too, so there is nothing to find down there.
        packlist = self.build({'a.vmt': STOCK, 'b.vmt': PACKED},
                              edges={'a.vmt': ['b.vmt']})
        packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')

        packlist.run(self.expanders)

        self.assertEqual(packlist.packed(), [])
        self.assertNotIn('b.vmt', packlist.assets)

    def testAMissingAssetIsNotExpanded(self):
        packlist = self.build({}, edges={'a.vmt': ['b.vmt']})
        packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')

        packlist.run(self.expanders)

        self.assertNotIn('b.vmt', packlist.assets)

    def testAnAssetReferencedTenTimesIsResolvedOnce(self):
        packlist = self.build({'a.vmt': PACKED})
        for _ in range(10):
            packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')

        self.assertEqual(self.index.asked, ['a.vmt'])

    def testPathsAreNormalisedBeforeDeduplicating(self):
        # Otherwise the same bytes get packed twice under two names, and
        # which one the engine loads is anyone's guess.
        packlist = self.build({'materials/a.vmt': PACKED})
        packlist.add('materials/a.vmt', graph.KIND_MATERIAL, 'seed')
        packlist.add('Materials\\A.VMT', graph.KIND_MATERIAL, 'seed')

        self.assertEqual(len(packlist.assets), 1)

    def testTheCeilingStopsTheWalk(self):
        packlist = self.build({})
        packlist.assets = dict(
            ('filler{}.vmt'.format(n), {}) for n in range(graph.MAX_ASSETS))

        added = packlist.add('one/more.vmt', graph.KIND_MATERIAL, 'seed')

        self.assertFalse(added)
        self.assertTrue(packlist.report.warnings)

    def testAnExpanderThatRaisesIsAWarningNotACrash(self):
        # One unreadable file must not cost the whole run.
        packlist = self.build({'a.vmt': PACKED, 'b.vmt': PACKED})
        packlist.add('a.vmt', graph.KIND_MATERIAL, 'seed')
        packlist.add('b.vmt', graph.KIND_MATERIAL, 'seed')

        def explode(packlist, internal, external, extra):
            if internal == 'a.vmt':
                raise ValueError('nope')

        packlist.run({graph.KIND_MATERIAL: explode})

        self.assertTrue(packlist.report.warnings)
        self.assertEqual(len(packlist.packed()), 2)


class MissingReportTestCase(unittest.TestCase):
    def build(self, statuses):
        return graph.PackList(FakeIndex(statuses), Report(quiet=True))

    def testADefiniteReferenceThatIsAbsentIsReported(self):
        packlist = self.build({})
        packlist.add('models/x.mdl', graph.KIND_MODEL, 'prop_static')

        self.assertEqual([a['internal'] for a in packlist.missing()],
                         ['models/x.mdl'])

    def testASpeculativeReferenceThatIsAbsentIsNot(self):
        # Thirteen of the fourteen skybox faces AutoPak asks for do not
        # exist on a typical map. Reporting them would drown the one line
        # that matters.
        packlist = self.build({})
        packlist.add('materials/skybox/sky_hdrup.vmt', graph.KIND_MATERIAL,
                     'worldspawn skyname', speculative=True)

        self.assertEqual(packlist.missing(), [])

    def testAnEmbeddedAssetIsNotMissing(self):
        # vbsp generated it into the map; there is no loose original and
        # nothing is wrong.
        packlist = self.build({'materials/maps/x/water.vmt': EMBEDDED})
        packlist.add('materials/maps/x/water.vmt', graph.KIND_MATERIAL,
                     'texdata')

        self.assertEqual(packlist.missing(), [])

    def testAStockAssetIsNotMissing(self):
        packlist = self.build({'materials/dev/measure.vmt': STOCK})
        packlist.add('materials/dev/measure.vmt', graph.KIND_MATERIAL,
                     'texdata')

        self.assertEqual(packlist.missing(), [])

    def testTheReportSaysWhatAskedForIt(self):
        packlist = self.build({})
        packlist.add('models/x.mdl', graph.KIND_MODEL, 'prop_static')

        self.assertEqual(packlist.missing()[0]['origin'], 'prop_static')


class ExclusionTestCase(unittest.TestCase):
    def build(self, statuses):
        return graph.PackList(FakeIndex(statuses), Report(quiet=True))

    def testAnExcludedFileIsNotPacked(self):
        packlist = self.build({'materials/a.vmt': PACKED})
        packlist.exclude(internal_paths=['materials/a.vmt'])

        packlist.add('materials/a.vmt', graph.KIND_MATERIAL, 'seed')

        self.assertEqual(packlist.packed(), [])

    def testAnExcludedDirectoryCoversWhatIsUnderIt(self):
        packlist = self.build({'materials/skip/a.vmt': PACKED})
        packlist.exclude(prefixes=['materials/skip'])

        packlist.add('materials/skip/a.vmt', graph.KIND_MATERIAL, 'seed')

        self.assertEqual(packlist.packed(), [])

    def testAnExcludedDirectoryDoesNotCoverASimilarName(self):
        packlist = self.build({'materials/skipper/a.vmt': PACKED})
        packlist.exclude(prefixes=['materials/skip'])

        packlist.add('materials/skipper/a.vmt', graph.KIND_MATERIAL, 'seed')

        self.assertEqual(len(packlist.packed()), 1)


class KindForTestCase(unittest.TestCase):
    def testItReadsTheExtension(self):
        cases = {
            'materials/a.vmt': graph.KIND_MATERIAL,
            'materials/a.vtf': graph.KIND_TEXTURE,
            'models/a.mdl': graph.KIND_MODEL,
            'particles/a.pcf': graph.KIND_PARTICLE,
            'sound/a.wav': graph.KIND_SOUND,
            'scripts/vscripts/a.nut': graph.KIND_SCRIPT,
            'resource/a.res': graph.KIND_RESOURCE,
            'maps/a.nav': graph.KIND_MISC,
        }
        for path, expected in cases.items():
            self.assertEqual(graph.kind_for(path), expected, path)


if __name__ == '__main__':
    unittest.main()
