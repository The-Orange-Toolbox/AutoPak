"""Tests for the VGCT executable definition.

A sidecar that fails schema validation is skipped silently: the exe builds,
the zip is fine, and the tool simply never appears in the create-node menu.
That is a bad thing to discover after publishing a release, so the same
check the build runs is also a test.
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

from _constants import NAME, VERSION  # noqa: E402

EXTENSIONS = os.path.join(HERE, os.pardir, 'extensions')
SIDECAR = os.path.join(EXTENSIONS, NAME + '.vgct.json')
SCHEMA = os.path.join(EXTENSIONS, 'vgct.schema.json')


class SidecarTestCase(unittest.TestCase):
    def setUp(self):
        with open(SIDECAR) as handle:
            self.definition = json.load(handle)

    def testItSatisfiesTheSchema(self):
        from jsonschema import Draft202012Validator

        with open(SCHEMA, encoding='utf-8') as handle:
            validator = Draft202012Validator(json.load(handle))

        errors = ['{}: {}'.format('/'.join(str(p) for p in e.absolute_path)
                                  or '(root)', e.message)
                  for e in validator.iter_errors(self.definition)]

        self.assertEqual(errors, [])

    def testTheStampedFieldsMatchTheBuild(self):
        # build.py overwrites these at package time. Keeping the checked-in
        # file in step means what is reviewed is what ships.
        self.assertEqual(self.definition['name'], NAME)
        self.assertEqual(self.definition['id'], NAME.lower())
        self.assertEqual(self.definition['version'], VERSION)
        self.assertEqual(self.definition['executable'],
                         {'value': NAME + '.exe'})

    def testItTakesABspAndGivesBackAFileList(self):
        inputs = {port['id']: port['type']
                  for port in self.definition['inputs']}
        outputs = {port['id']: port['type']
                   for port in self.definition['outputs']}

        self.assertEqual(inputs['bsp'], 'BSP')
        self.assertEqual(outputs['filelist'], 'File')

    def testTheMapIsAnInputOnly(self):
        # AutoPak reads the map and writes a text file. It produces no BSP,
        # so declaring one as an output -- even as a passthrough -- would
        # claim authorship of a file it never touches, and invite a graph
        # to chain off AutoPak as though it had done something to the map.
        outputs = [port['id'] for port in self.definition['outputs']]

        self.assertEqual(outputs, ['filelist'])
        self.assertNotIn('BSP', [port['type']
                                 for port in self.definition['outputs']])

    def testEveryArgumentWithAFlagUsesALongFlag(self):
        # The sidecar and the CompilePal parameters file are both written
        # against the long forms; a short flag here would be a typo.
        for argument in self.definition['arguments']:
            flag = argument.get('flag')
            if flag is not None:
                self.assertTrue(flag.startswith('--'),
                                'not a long flag: ' + flag)


if __name__ == '__main__':
    unittest.main()
