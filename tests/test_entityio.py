r"""Tests for reading entity outputs.

An output in a compiled map is one string with escape characters where the
commas were, and some of them carry a whole second output or a fragment of
VScript. Content named this way appears nowhere else in the map, so a
parsing mistake here is content silently absent from the pack.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

import entityio  # noqa: E402

ESC = entityio.SEPARATOR


def output(*fields):
    return ESC.join(fields)


class ParseOutputTestCase(unittest.TestCase):
    def testItSplitsTheFiveFields(self):
        value = output('relay', 'SetModel', 'models/x.mdl', '0', '-1')

        self.assertEqual(entityio.parse_output(value),
                         ('relay', 'SetModel', 'models/x.mdl', '0', '-1'))

    def testAnOrdinaryKeyvalueIsNotAnOutput(self):
        self.assertIsNone(entityio.parse_output('models/props/barrel.mdl'))

    def testTheWrongNumberOfFieldsIsNotAnOutput(self):
        self.assertIsNone(entityio.parse_output(output('a', 'b', 'c')))

    def testAnEmptyParameterIsStillAValidOutput(self):
        value = output('relay', 'Trigger', '', '0', '-1')

        self.assertEqual(entityio.parse_output(value)[2], '')


class AddOutputTestCase(unittest.TestCase):
    def testTheSimpleFormIsLeftAlone(self):
        # AddOutput "targetname newname" sets a keyvalue and names nothing.
        found = entityio.resolve_addoutput('AddOutput', 'targetname newname')

        self.assertEqual(found, ('AddOutput', 'targetname newname'))

    def testTheComplexFormIsUnwrapped(self):
        # This carries a whole output, and the model inside it has to be
        # packed like any other.
        found = entityio.resolve_addoutput(
            'AddOutput', 'OnUser1 relay:SetModel:models/x.mdl:0:-1')

        self.assertEqual(found, ('SetModel', 'models/x.mdl'))

    def testAnotherInputIsLeftAlone(self):
        found = entityio.resolve_addoutput('SetModel', 'models/x.mdl')

        self.assertEqual(found, ('SetModel', 'models/x.mdl'))

    def testAMalformedComplexFormIsLeftAlone(self):
        found = entityio.resolve_addoutput('AddOutput', 'OnUser1 relay:Kill')

        self.assertEqual(found[0], 'AddOutput')


class ConsoleCommandTestCase(unittest.TestCase):
    def testItSplitsVerbFromArgument(self):
        self.assertEqual(entityio.console_command('r_screenoverlay effects/x'),
                         ('r_screenoverlay', 'effects/x'))

    def testTheVerbIsLowercased(self):
        self.assertEqual(entityio.console_command('PlayGameSound foo.wav')[0],
                         'playgamesound')

    def testQuotesAreStripped(self):
        self.assertEqual(entityio.console_command('"play" "music/x.mp3"')[1],
                         'music/x.mp3')

    def testACommandWithNoArgumentIsNothing(self):
        self.assertEqual(entityio.console_command('restart'), (None, None))


class ScriptCallTestCase(unittest.TestCase):
    def testASingleCall(self):
        found = entityio.script_calls('EmitSound("ambient/wind.wav")')

        self.assertEqual(found, [('EmitSound', 'ambient/wind.wav')])

    def testSeveralStatements(self):
        found = entityio.script_calls(
            'self.PrecacheModel("models/a.mdl"); '
            'self.PrecacheSound("b.wav")')

        self.assertEqual(found, [('self.PrecacheModel', 'models/a.mdl'),
                                 ('self.PrecacheSound', 'b.wav')])

    def testEachArgumentIsReported(self):
        found = entityio.script_calls('Foo("a.mdl", "b.mdl")')

        self.assertEqual(found, [('Foo', 'a.mdl'), ('Foo', 'b.mdl')])

    def testBacktickQuotesAreStripped(self):
        # Hammer needs backticks where a real quote would end the keyvalue.
        found = entityio.script_calls('EmitSound(`ambient/wind.wav`)')

        self.assertEqual(found, [('EmitSound', 'ambient/wind.wav')])

    def testUnbalancedBackticksAreRefused(self):
        # The string was cut in half somewhere; anything read out of it
        # would be nonsense.
        self.assertEqual(entityio.script_calls('EmitSound(`ambient/wind'), [])

    def testATableArgumentStaysWhole(self):
        # The commas inside it separate fields, not arguments.
        found = entityio.script_calls(
            'EmitSoundEx({ sound_name = "a.wav", volume = 1 })')

        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], 'EmitSoundEx')
        self.assertIn('sound_name', found[0][1])

    def testASemicolonInsideATableDoesNotSplitTheCall(self):
        found = entityio.script_calls('Foo({ a = 1; b = 2 })')

        self.assertEqual(len(found), 1)

    def testTextWithNoCallIsNothing(self):
        self.assertEqual(entityio.script_calls('local x = 5'), [])


class ScriptTableTestCase(unittest.TestCase):
    def testItReadsTheFields(self):
        found = entityio.script_table(
            '{ sound_name = "ambient/wind.wav", volume = 1 }')

        self.assertEqual(found['sound_name'], 'ambient/wind.wav')

    def testKeysAreLowercased(self):
        found = entityio.script_table('{ Sound_Name = "a.wav" }')

        self.assertEqual(found['sound_name'], 'a.wav')

    def testSomethingThatIsNotATableIsEmpty(self):
        self.assertEqual(entityio.script_table('not a table'), {})


if __name__ == '__main__':
    unittest.main()
