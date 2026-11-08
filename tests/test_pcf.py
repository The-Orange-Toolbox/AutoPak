"""Tests for reading particle systems.

Run against a real ``.pcf`` -- ValvePCF's own test file -- because the
format is binary DMX and a synthetic fixture would test the fixture rather
than the reader. The file is small and its contents are known.

The rules being checked are AutoPak's, not the library's: which attributes
count as a material, how a value written by the particle editor is
normalised, and that a cycle in the child links cannot hang the crawl.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from formats import pcf  # noqa: E402

SAMPLE = os.path.join(HERE, os.pardir, os.pardir, 'ValvePCF', 'tests',
                      'data', 'test.pcf')


class FakeAttribute(object):
    def __init__(self, name, type_, data):
        self._name = name
        self._type = type_
        self._data = data


class FakeSystem(object):
    def __init__(self, name='system', attributes=None, children=None):
        self._name = name
        self.attributes = attributes or []
        self.children = children or []
        self.renderers = []
        self.operators = []
        self.initializers = []
        self.emitters = []
        self.forces = []
        self.constraints = []


class FakeChild(object):
    def __init__(self, ref):
        self.ref = ref


def material(value):
    return FakeAttribute('material', pcf.STRING, value)


class ReferenceTestCase(unittest.TestCase):
    def testAMaterialAttribute(self):
        system = FakeSystem(attributes=[material('effects/bubble.vmt')])

        materials, _ = pcf.system_references(system)

        self.assertEqual(materials, ['materials/effects/bubble.vmt'])

    def testTheParticleEditorsBackslashesAreNormalised(self):
        # The format stores exactly what the editor wrote.
        system = FakeSystem(attributes=[material('effects\\bubble.vmt')])

        materials, _ = pcf.system_references(system)

        self.assertEqual(materials, ['materials/effects/bubble.vmt'])

    def testAStringEndingInVmtIsAMaterialWhateverItsKeyIs(self):
        system = FakeSystem(attributes=[
            FakeAttribute('some_other_key', pcf.STRING, 'effects/x.vmt')])

        materials, _ = pcf.system_references(system)

        self.assertEqual(materials, ['materials/effects/x.vmt'])

    def testAStringEndingInMdlIsAModel(self):
        system = FakeSystem(attributes=[
            FakeAttribute('model', pcf.STRING, 'models/props/x.mdl')])

        _, models = pcf.system_references(system)

        self.assertEqual(models, ['models/props/x.mdl'])

    def testANonStringAttributeIsIgnored(self):
        system = FakeSystem(attributes=[
            FakeAttribute('max_particles', 2, 12)])

        self.assertEqual(pcf.system_references(system), ([], []))

    def testAnEmptyValueIsIgnored(self):
        system = FakeSystem(attributes=[material('')])

        self.assertEqual(pcf.system_references(system), ([], []))

    def testAChildSystemIsFollowed(self):
        child = FakeSystem(attributes=[material('effects/child.vmt')])
        parent = FakeSystem(attributes=[material('effects/parent.vmt')],
                            children=[FakeChild(child)])

        materials, _ = pcf.system_references(parent)

        self.assertEqual(materials, ['materials/effects/parent.vmt',
                                     'materials/effects/child.vmt'])

    def testACycleInTheChildLinksTerminates(self):
        # Nothing in the format forbids one.
        first = FakeSystem(attributes=[material('effects/a.vmt')])
        second = FakeSystem(attributes=[material('effects/b.vmt')])
        first.children = [FakeChild(second)]
        second.children = [FakeChild(first)]

        materials, _ = pcf.system_references(first)

        self.assertEqual(sorted(materials), ['materials/effects/a.vmt',
                                             'materials/effects/b.vmt'])

    def testAChildWithNoTargetIsSkipped(self):
        system = FakeSystem(children=[FakeChild(None)])

        self.assertEqual(pcf.system_references(system), ([], []))


@unittest.skipUnless(os.path.isfile(SAMPLE), 'ValvePCF sample not present')
class RealFileTestCase(unittest.TestCase):
    def testItReadsTheMaterialsOutOfARealParticleFile(self):
        materials, _ = pcf.dependencies(SAMPLE)

        self.assertIn('materials/effects/bubble.vmt', materials)

    def testItNamesTheSystemsARealFileDefines(self):
        # Used to work out which file a map's named effect comes from.
        self.assertIn('hadal_bubbles', pcf.names(SAMPLE))


class FailureTestCase(unittest.TestCase):
    def testSomethingThatIsNotAParticleFileIsReported(self):
        # One bad file should cost a warning, not the run, so the caller
        # needs to be able to tell this apart from an empty file.
        with self.assertRaises(pcf.ParticleError):
            pcf.dependencies(__file__)


if __name__ == '__main__':
    unittest.main()
