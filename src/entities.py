"""What the entities in a map ask for.

Most of a custom map's content is named here rather than in the lumps: every
prop, sprite, sound, particle and script is an entity keyvalue. Source has no
schema saying which keys hold filenames, so :mod:`keys` carries the list and
this module applies it, along with the special cases where a value means
something other than what its key suggests.

The special cases are not decoration. ``env_funnel`` names no material at
all and needs one packed regardless; a ``model`` key on a sprite holds a
material, not a model; ``item_teamflag`` builds three filenames out of one
value, and uses a different abbreviation for the same team in two adjacent
keys. Every one of them is a map that shipped broken once.

Sounds get a decision of their own. Most sound keys hold a soundscript
entry name -- ``Ambient.Wind`` -- rather than a path, and treating those as
files would report almost every one of them missing and bury the few that
genuinely are. See :func:`classify_sound`.
"""

import keys
import paths

import entityio

#: Keys read directly off an entity, whatever its classname.
UTILITY_KEYS = {
    'vehiclescript': 'scripts/',
    'scriptfile': '',
    'res_file': '',
}

#: Hardcoded content some entities need without naming it.
IMPLIED_MATERIALS = {
    'env_funnel': ['materials/sprites/flare6.vmt'],
    'env_embers': ['materials/particle/fire.vmt'],
}

#: Values that are themselves the name of a model, rather than keys.
IMPLIED_MODELS = {
    'item_sodacan': 'models/can.mdl',
    'env_beverage': 'models/can.mdl',
    'tf_projectile_throwable': 'models/props_gameplay/small_loaf.mdl',
}

#: Outputs whose parameter is a material.
IO_MATERIAL_INPUTS = ('setcountdownimage', 'setoverlaymaterial')

#: Outputs whose parameter is a model.
IO_MODEL_INPUTS = ('setmodel', 'setcustommodel',
                   'setcustommodelwithclassanimations')

#: Console commands that name content.
IO_COMMAND_MATERIALS = ('r_screenoverlay',)
IO_COMMAND_SOUNDS = ('play', 'playgamesound')

#: VScript functions that name content. Matched on the part after the last
#: dot, so ``self.EmitSound`` and ``EntFire(...).EmitSound`` both count.
SCRIPT_MATERIAL_CALLS = ('setskyboxtexture', 'setscriptoverlaymaterial')
SCRIPT_MODEL_CALLS = ('setmodel', 'setmodelsimple')
SCRIPT_SOUND_CALLS = ('emitsound', 'emitambientsoundon', 'precachesound')
SCRIPT_TABLE_SOUND_CALLS = ('emitsoundex',)
SCRIPT_PARTICLE_CALLS = ('dispatchparticleeffect',)
SCRIPT_SCRIPT_CALLS = ('includescript', 'doincludescript')


class References(object):
    """What one pass over the entities turned up.

    Kept as plain lists of (value, origin) so the caller decides what to do
    with each; this module does no resolving and no reporting.
    """

    def __init__(self):
        self.materials = []
        self.models = []
        self.sounds = []
        self.scripted_sounds = []
        self.particles = []
        self.scripts = []
        self.misc = []

    def __len__(self):
        return sum(len(getattr(self, name)) for name in
                   ('materials', 'models', 'sounds', 'scripted_sounds',
                    'particles', 'scripts', 'misc'))


def classify_sound(value):
    """Decide whether a sound value is a file or a soundscript entry.

    ``ambient/wind.wav`` is a file. ``Ambient.Wind`` is an entry in a
    soundscript, and the file behind it is only discoverable by reading
    ``game_sounds`` manifests -- which AutoPak does not do. Reporting those
    as missing would make the report roughly ninety percent noise, so they
    are counted separately instead.

    :returns: True when the value names a file on disk.
    :rtype: bool
    """
    cleaned = str(value).strip(paths.SOUND_PREFIXES)
    if not cleaned:
        return False

    lowered = cleaned.lower()
    if lowered.endswith(keys.SOUND_EXTENSIONS):
        return True

    # A path is a path even without a recognised extension; a bare dotted
    # name with no separator is a soundscript entry.
    return '/' in cleaned or '\\' in cleaned


def _material(value):
    """Turn an entity's material value into an internal path.

    ``.spr`` is left alone -- sprites keep their own extension -- and
    anything else gains ``.vmt``.
    """
    stem = paths.vmt_path(value)
    if not stem:
        return None
    if stem.lower().endswith('.spr'):
        return ('materials/' + stem).lower()
    return ('materials/' + stem + '.vmt').lower()


def _model(value):
    stem = paths.internal_path(value).lower().strip()
    if not stem:
        return None
    return stem


def collect(entities):
    """Read every entity in the map.

    :param entities: the parsed entity lump -- a list of entities, each a
        list of [key, value] pairs.
    :type entities: list
    :rtype: References
    """
    found = References()

    for entity in entities:
        pairs = [(str(k), str(v)) for k, v in entity]
        classname = ''
        for key, value in pairs:
            if key.lower() == 'classname':
                classname = value.lower()
                break

        origin = classname or 'entity'
        _collect_entity(found, pairs, classname, origin)

    return found


def _collect_entity(found, pairs, classname, origin):
    for name in IMPLIED_MATERIALS.get(classname, ()):
        found.materials.append((name, origin))

    if classname.startswith('func_dust'):
        found.materials.append(('materials/particle/sparkles.vmt', origin))

    for key, value in pairs:
        if not value:
            continue

        lowered = key.lower()

        _collect_material(found, classname, lowered, key, value, origin)
        _collect_model(found, classname, lowered, key, value, origin)
        _collect_sound(found, lowered, key, value, origin)
        _collect_particle(found, lowered, value, origin)
        _collect_utility(found, lowered, value, origin)

        output = entityio.parse_output(value)
        if output is not None:
            _collect_output(found, output, origin + ' ' + key)


def _collect_material(found, classname, lowered, key, value, origin):
    where = '{} "{}"'.format(origin, key)

    # A sprite's 'model' key holds a material, not a model. Reading it as a
    # model would look for a .mdl that does not exist and pack nothing.
    if lowered == 'model' and ('sprite' in classname or 'glow' in classname):
        internal = _material(value)
        if internal:
            found.materials.append((internal, where))
        return

    if lowered not in keys.ENT_MATERIAL_KEYS:
        _collect_special_material(found, classname, lowered, value, where)
        return

    internal = _material(value)
    if internal:
        found.materials.append((internal, where))

    # Team icons have a locked variant shown before the round starts.
    if lowered.startswith('team_icon'):
        locked = _material(value + '_locked')
        if locked:
            found.materials.append((locked, where))


def _collect_special_material(found, classname, lowered, value, where):
    if classname == 'item_teamflag':
        if lowered == 'flag_trail':
            # 'blu', not 'blue'. The two keys below disagree about the
            # abbreviation and both spellings are what is on disk; making
            # them consistent breaks one of them.
            for suffix in ('', '_red', '_blu'):
                internal = _material('effects/' + value + suffix)
                if internal:
                    found.materials.append((internal, where))
        elif lowered == 'flag_icon':
            for suffix in ('', '_red', '_blue'):
                internal = _material('vgui/' + value + suffix)
                if internal:
                    found.materials.append((internal, where))

    elif classname == 'skybox_swapper' and lowered == 'skyboxname':
        for internal in _skybox(value):
            found.materials.append((internal, where))


def _skybox(sky_name):
    """The fourteen candidate faces of a skybox."""
    stem = paths.vmt_path(sky_name)
    if not stem:
        return []

    found = []
    for side in keys.SKYBOX_SIDES:
        found.append('materials/skybox/{}{}.vmt'.format(stem, side).lower())
        found.append('materials/skybox/{}_hdr{}.vmt'.format(stem, side).lower())
    return found


def _collect_model(found, classname, lowered, key, value, origin):
    where = '{} "{}"'.format(origin, key)

    # A brush entity's 'model' is '*17', an index into the map's own
    # brushes. Only its gibs are a real file.
    if classname.startswith('func'):
        if lowered == 'gibmodel':
            internal = _model(value)
            if internal:
                found.models.append((internal, where))
        return

    if 'sprite' in classname or 'glow' in classname:
        return

    if key in keys.ENT_MODEL_KEYS:
        internal = _model(value)
        # '*12' is a brushwork index, not a file.
        if internal and not internal.startswith('*'):
            found.models.append((internal, where))

    implied = IMPLIED_MODELS.get(value.lower())
    if implied:
        found.models.append((implied, where))


def _collect_sound(found, lowered, key, value, origin):
    if lowered not in keys.ENT_SOUND_KEYS:
        return

    where = '{} "{}"'.format(origin, key)

    if classify_sound(value):
        found.sounds.append((paths.sound_path(value), where))
    else:
        found.scripted_sounds.append((value.strip(), where))


def _collect_particle(found, lowered, value, origin):
    if lowered in keys.ENT_PARTICLE_KEYS:
        found.particles.append((value.strip(), origin))


def _collect_utility(found, lowered, value, origin):
    if lowered == 'vscripts':
        # Space-separated list of scripts, all run on the same entity.
        for name in value.split():
            found.scripts.append(('scripts/vscripts/' + name.strip().lower(),
                                  origin + ' "vscripts"'))
        return

    if lowered in UTILITY_KEYS:
        prefix = UTILITY_KEYS[lowered]
        internal = paths.internal_path(prefix + value).lower()
        found.misc.append((internal, '{} "{}"'.format(origin, lowered)))
        return

    if lowered == 'filename':
        found.misc.append((paths.internal_path(value).lower(),
                           '{} "filename"'.format(origin)))


def _collect_output(found, output, where):
    _, target_input, parameter, _, _ = output
    target_input, parameter = entityio.resolve_addoutput(target_input,
                                                         parameter)
    lowered = target_input.lower()

    if not parameter:
        return

    if lowered in IO_MATERIAL_INPUTS:
        # SetCountdownImage names a vgui image without its folder.
        stem = ('vgui/' + parameter if lowered == 'setcountdownimage'
                else parameter)
        internal = _material(stem)
        if internal:
            found.materials.append((internal, where))
        return

    if lowered in IO_MODEL_INPUTS:
        internal = _model(parameter)
        if internal and not internal.startswith('*'):
            found.models.append((internal, where))
        return

    # Every PlayVO variant: PlayVO, PlayVORed, PlayVOBlue.
    if lowered.startswith('playvo'):
        if classify_sound(parameter):
            found.sounds.append((paths.sound_path(parameter), where))
        else:
            found.scripted_sounds.append((parameter.strip(), where))
        return

    if lowered == 'runscriptfile':
        name = parameter.strip().lower()
        found.scripts.append(('scripts/vscripts/' + name, where))
        return

    if lowered == 'setcustomupgradesfile':
        found.misc.append((paths.internal_path(parameter).lower(), where))
        return

    if lowered == 'command':
        _collect_command(found, parameter, where)
        return

    if lowered == 'runscriptcode':
        _collect_script_code(found, parameter, where)


def _collect_command(found, parameter, where):
    verb, argument = entityio.console_command(parameter)
    if verb is None:
        return

    if verb in IO_COMMAND_MATERIALS:
        internal = _material(argument)
        if internal:
            found.materials.append((internal, where))
    elif verb in IO_COMMAND_SOUNDS:
        if classify_sound(argument):
            found.sounds.append((paths.sound_path(argument), where))
        else:
            found.scripted_sounds.append((argument.strip(), where))


def _collect_script_code(found, code, where):
    for name, argument in entityio.script_calls(code):
        call = name.rpartition('.')[2].lower()

        if call in SCRIPT_TABLE_SOUND_CALLS:
            table = entityio.script_table(argument)
            sound = table.get('sound_name')
            if sound:
                if classify_sound(sound):
                    found.sounds.append((paths.sound_path(sound), where))
                else:
                    found.scripted_sounds.append((sound, where))
            continue

        if call in SCRIPT_MATERIAL_CALLS:
            if call == 'setskyboxtexture':
                for internal in _skybox(argument):
                    found.materials.append((internal, where))
            else:
                internal = _material(argument)
                if internal:
                    found.materials.append((internal, where))

        elif call in SCRIPT_MODEL_CALLS or call == 'precachemodel':
            internal = _model(argument)
            if internal and not internal.startswith('*'):
                found.models.append((internal, where))

        elif call in SCRIPT_SOUND_CALLS:
            if classify_sound(argument):
                found.sounds.append((paths.sound_path(argument), where))
            else:
                found.scripted_sounds.append((argument, where))

        elif call in SCRIPT_PARTICLE_CALLS:
            found.particles.append((argument, where))

        elif call in SCRIPT_SCRIPT_CALLS:
            found.scripts.append(
                ('scripts/vscripts/' + argument.strip().lower(), where))
