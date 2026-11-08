"""Tests for the entity rules.

This is the largest block of ported knowledge in AutoPak, and none of it is
derivable: Source has no schema saying which keyvalues hold filenames, so
every rule here is something someone worked out from a map that shipped
broken. The tests exist so that knowledge cannot be lost to a refactor.

Entities are fed in exactly the shape valvebsp hands back -- a list of
entities, each a list of [key, value] pairs -- so no BSP is needed.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, 'src'))

import entities  # noqa: E402
import entityio  # noqa: E402

ESC = entityio.SEPARATOR


def entity(classname, **pairs):
    found = [['classname', classname]]
    for key, value in pairs.items():
        found.append([key, value])
    return found


def collect(*entity_lists):
    return entities.collect(list(entity_lists))


class MaterialKeyTestCase(unittest.TestCase):
    def testARopeMaterial(self):
        found = collect(entity('keyframe_rope', ropematerial='cable/cable'))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/cable/cable.vmt'])

    def testAnOverlayMaterial(self):
        found = collect(entity('info_overlay', material='decals/blood'))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/decals/blood.vmt'])

    def testASpriteModelKeyIsAMaterialNotAModel(self):
        # env_sprite's 'model' names a material. Reading it as a model
        # looks for a .mdl that was never there and packs nothing.
        found = collect(entity('env_sprite', model='sprites/glow01.vmt'))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/sprites/glow01.vmt'])
        self.assertEqual(found.models, [])

    def testASpriteKeepsASprExtension(self):
        # .spr sprites are their own format and are not .vmt files.
        found = collect(entity('env_glow', model='sprites/light_glow.spr'))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/sprites/light_glow.spr'])

    def testATeamIconAlsoNeedsItsLockedVariant(self):
        # Shown before the round starts. Nothing else names it.
        found = collect(entity('team_control_point', team_icon_2='hud/icon'))
        found_materials = [m for m, _ in found.materials]

        self.assertIn('materials/hud/icon.vmt', found_materials)
        self.assertIn('materials/hud/icon_locked.vmt', found_materials)

    def testEveryMaterialKeyIsRead(self):
        import keys
        for key in keys.ENT_MATERIAL_KEYS:
            found = collect(entity('some_entity', **{key: 'some/thing'}))

            self.assertIn('materials/some/thing.vmt',
                          [m for m, _ in found.materials],
                          'not read: ' + key)


class ImpliedMaterialTestCase(unittest.TestCase):
    def testEnvFunnelNamesNothingButNeedsASprite(self):
        found = collect(entity('env_funnel'))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/sprites/flare6.vmt'])

    def testEnvEmbersNeedsItsParticleMaterial(self):
        found = collect(entity('env_embers'))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/particle/fire.vmt'])

    def testEveryFuncDustVariantNeedsSparkles(self):
        for classname in ('func_dustmotes', 'func_dustcloud'):
            found = collect(entity(classname))

            self.assertEqual([m for m, _ in found.materials],
                             ['materials/particle/sparkles.vmt'], classname)


class TeamFlagTestCase(unittest.TestCase):
    def testTheTrailUsesTheShortTeamAbbreviation(self):
        # 'blu', not 'blue'. The next test uses 'blue' for the same team.
        # Both spellings are what is on disk; making them consistent
        # breaks one of them.
        found = collect(entity('item_teamflag', flag_trail='flagtrail'))

        self.assertEqual([m for m, _ in found.materials], [
            'materials/effects/flagtrail.vmt',
            'materials/effects/flagtrail_red.vmt',
            'materials/effects/flagtrail_blu.vmt',
        ])

    def testTheIconUsesTheLongTeamAbbreviation(self):
        found = collect(entity('item_teamflag', flag_icon='flagicon'))

        self.assertEqual([m for m, _ in found.materials], [
            'materials/vgui/flagicon.vmt',
            'materials/vgui/flagicon_red.vmt',
            'materials/vgui/flagicon_blue.vmt',
        ])


class SkyboxTestCase(unittest.TestCase):
    def testASwapperNamesFourteenCandidateFaces(self):
        found = collect(entity('skybox_swapper', SkyboxName='sky_night_01'))
        found_materials = [m for m, _ in found.materials]

        self.assertEqual(len(found_materials), 14)
        self.assertIn('materials/skybox/sky_night_01up.vmt', found_materials)
        self.assertIn('materials/skybox/sky_night_01_hdrup.vmt',
                      found_materials)


class ModelKeyTestCase(unittest.TestCase):
    def testAPropModel(self):
        found = collect(entity('prop_dynamic', model='models/props/x.mdl'))

        self.assertEqual([m for m, _ in found.models], ['models/props/x.mdl'])

    def testABrushEntitysModelIsNotAFile(self):
        # func_* entities carry '*17', an index into the map's own
        # brushwork. There is no file to pack.
        found = collect(entity('func_door', model='*17'))

        self.assertEqual(found.models, [])

    def testAFuncEntityStillNeedsItsGibs(self):
        found = collect(entity('func_breakable',
                               gibmodel='models/gibs/wood.mdl'))

        self.assertEqual([m for m, _ in found.models],
                         ['models/gibs/wood.mdl'])

    def testModelOverrideIsMatchedWithItsOwnCasing(self):
        # The key really is spelled this way in the entity, and the model
        # key list is matched case-sensitively because of it.
        found = collect(entity('tf_gamerules',
                               ModelOverride='models/x.mdl'))

        self.assertEqual([m for m, _ in found.models], ['models/x.mdl'])

    def testASodaCanEntityNamesNoModelButNeedsOne(self):
        found = collect(entity('point_template',
                               template01='item_sodacan'))

        self.assertEqual([m for m, _ in found.models], ['models/can.mdl'])

    def testEveryModelKeyIsRead(self):
        import keys
        for key in keys.ENT_MODEL_KEYS:
            found = collect(entity('prop_dynamic', **{key: 'models/x.mdl'}))

            self.assertIn('models/x.mdl', [m for m, _ in found.models],
                          'not read: ' + key)


class SoundTestCase(unittest.TestCase):
    def testAPathIsTreatedAsAFile(self):
        found = collect(entity('ambient_generic',
                               message='ambient/wind/wind1.wav'))

        self.assertEqual([s for s, _ in found.sounds],
                         ['sound/ambient/wind/wind1.wav'])
        self.assertEqual(found.scripted_sounds, [])

    def testASoundscriptEntryIsNotTreatedAsAFile(self):
        # This is the rule that keeps the missing report usable: most
        # sound keys hold an entry name, and looking for a file called
        # 'Ambient.Wind' would report almost all of them missing.
        found = collect(entity('ambient_generic', message='Ambient.Wind'))

        self.assertEqual(found.sounds, [])
        self.assertEqual([s for s, _ in found.scripted_sounds],
                         ['Ambient.Wind'])

    def testAPrecachePrefixIsStripped(self):
        found = collect(entity('ambient_generic',
                               message='*music/theme.mp3'))

        self.assertEqual([s for s, _ in found.sounds],
                         ['sound/music/theme.mp3'])

    def testAPathWithoutAKnownExtensionIsStillAFile(self):
        found = collect(entity('ambient_generic', message='custom/thing'))

        self.assertEqual([s for s, _ in found.sounds],
                         ['sound/custom/thing'])

    def testEverySoundKeyIsRead(self):
        import keys
        for key in keys.ENT_SOUND_KEYS:
            found = collect(entity('some_entity', **{key: 'a/b.wav'}))

            self.assertIn('sound/a/b.wav', [s for s, _ in found.sounds],
                          'not read: ' + key)


class ParticleTestCase(unittest.TestCase):
    def testAParticleIsCollectedByName(self):
        # Particles are named, not pathed; the manifest says which file
        # defines each one.
        found = collect(entity('info_particle_system',
                               effect_name='my_custom_effect'))

        self.assertEqual([p for p, _ in found.particles],
                         ['my_custom_effect'])


class ScriptTestCase(unittest.TestCase):
    def testVscriptsIsASpaceSeparatedList(self):
        found = collect(entity('logic_script',
                               vscripts='a.nut b/c.nut'))

        self.assertEqual([s for s, _ in found.scripts],
                         ['scripts/vscripts/a.nut', 'scripts/vscripts/b/c.nut'])

    def testAVehicleScript(self):
        found = collect(entity('prop_vehicle',
                               vehiclescript='vehicles/jeep.txt'))

        self.assertEqual([m for m, _ in found.misc],
                         ['scripts/vehicles/jeep.txt'])

    def testAColorCorrectionFile(self):
        found = collect(entity('color_correction',
                               filename='materials/correction/x.raw'))

        self.assertEqual([m for m, _ in found.misc],
                         ['materials/correction/x.raw'])


class OutputTestCase(unittest.TestCase):
    def output(self, *fields):
        return ESC.join(fields)

    def testSetModelNamesAModel(self):
        found = collect(entity('logic_relay', OnTrigger=self.output(
            'prop', 'SetModel', 'models/x.mdl', '0', '-1')))

        self.assertEqual([m for m, _ in found.models], ['models/x.mdl'])

    def testSetCountdownImageIsAVguiMaterial(self):
        found = collect(entity('logic_relay', OnTrigger=self.output(
            'hud', 'SetCountdownImage', 'countdown_x', '0', '-1')))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/vgui/countdown_x.vmt'])

    def testAScreenOverlayCommandIsAMaterial(self):
        found = collect(entity('logic_relay', OnTrigger=self.output(
            'con', 'Command', 'r_screenoverlay effects/blur', '0', '-1')))

        self.assertEqual([m for m, _ in found.materials],
                         ['materials/effects/blur.vmt'])

    def testAPlaySoundCommandIsASound(self):
        found = collect(entity('logic_relay', OnTrigger=self.output(
            'con', 'Command', 'play music/theme.wav', '0', '-1')))

        self.assertEqual([s for s, _ in found.sounds],
                         ['sound/music/theme.wav'])

    def testPlayVoVariantsAreAllRead(self):
        for name in ('PlayVO', 'PlayVORed', 'PlayVOBlue'):
            found = collect(entity('logic_relay', OnTrigger=self.output(
                'speaker', name, 'vo/announcer.wav', '0', '-1')))

            self.assertEqual([s for s, _ in found.sounds],
                             ['sound/vo/announcer.wav'], name)

    def testRunScriptFileNamesAScript(self):
        found = collect(entity('logic_relay', OnTrigger=self.output(
            'script', 'RunScriptFile', 'mymap/logic.nut', '0', '-1')))

        self.assertEqual([s for s, _ in found.scripts],
                         ['scripts/vscripts/mymap/logic.nut'])

    def testAnAddOutputCarryingAModelIsUnwrapped(self):
        found = collect(entity('logic_relay', OnTrigger=self.output(
            'prop', 'AddOutput', 'OnUser1 p:SetModel:models/x.mdl:0:-1',
            '0', '-1')))

        self.assertEqual([m for m, _ in found.models], ['models/x.mdl'])


class ScriptCodeTestCase(unittest.TestCase):
    def code(self, script):
        return ESC.join(['!self', 'RunScriptCode', script, '0', '-1'])

    def testPrecacheModel(self):
        found = collect(entity('logic_relay',
                               OnTrigger=self.code(
                                   'self.PrecacheModel(`models/x.mdl`)')))

        self.assertEqual([m for m, _ in found.models], ['models/x.mdl'])

    def testEmitSound(self):
        found = collect(entity('logic_relay',
                               OnTrigger=self.code(
                                   'self.EmitSound(`ambient/x.wav`)')))

        self.assertEqual([s for s, _ in found.sounds],
                         ['sound/ambient/x.wav'])

    def testEmitSoundExReadsTheTable(self):
        found = collect(entity('logic_relay', OnTrigger=self.code(
            'EmitSoundEx({ sound_name = `ambient/x.wav`, volume = 1 })')))

        self.assertEqual([s for s, _ in found.sounds],
                         ['sound/ambient/x.wav'])

    def testSetSkyboxTextureNamesEveryFace(self):
        found = collect(entity('logic_relay', OnTrigger=self.code(
            'SetSkyboxTexture(`sky_night_01`)')))

        self.assertEqual(len(found.materials), 14)

    def testDispatchParticleEffectNamesAParticle(self):
        found = collect(entity('logic_relay', OnTrigger=self.code(
            'DispatchParticleEffect(`my_effect`, pos, ang)')))

        self.assertIn('my_effect', [p for p, _ in found.particles])

    def testIncludeScript(self):
        found = collect(entity('logic_relay', OnTrigger=self.code(
            'IncludeScript(`shared/util.nut`)')))

        self.assertEqual([s for s, _ in found.scripts],
                         ['scripts/vscripts/shared/util.nut'])


class OriginTestCase(unittest.TestCase):
    def testTheOriginNamesTheClassnameAndKey(self):
        # The missing report is only useful if it says where to look.
        found = collect(entity('prop_dynamic', model='models/x.mdl'))

        self.assertEqual(found.models[0][1], 'prop_dynamic "model"')


if __name__ == '__main__':
    unittest.main()
