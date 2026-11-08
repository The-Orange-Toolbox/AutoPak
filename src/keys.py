"""The keyword tables that say which values name an asset.

Source has no schema for this. Whether a keyvalue holds a filename is
knowledge, not something you can derive, and these lists are that knowledge:
ported verbatim from CompilePal, which accumulated them the hard way over
years of maps that shipped with something missing.

They are Python lists rather than data files on purpose. PyInstaller's
one-file mode unpacks bundled data to a temporary directory, which means a
resource-path helper in every consumer and a failure mode that works from
source and breaks in the built exe. These are constants that change roughly
never, so a module is the honest place for them.

Two matching rules differ, and the difference is load-bearing:

* material, sound and particle keys are matched **lowercased**
* model keys are matched **case-sensitively** -- ``ModelOverride`` really is
  spelled that way in the entity, and lowercasing the comparison would make
  it match keys it should not
"""

#: VMT keys whose value names a ``.vtf``. Matched case-insensitively.
#:
#: CompilePal's file also lists ``$emissiveBlendTexture``,
#: ``$emissiveBlendBaseTexture`` and ``$emissiveBlendFlowTexture``. They are
#: case-variant duplicates of entries already here and are redundant under
#: case-insensitive matching, so they are left out.
#:
#: ``srgb?$basetexture`` is not a typo: it is a literal key some shaders
#: use. Keep it exactly as written.
TEXTURE_KEYS = (
    '$ambientocclusiontexture',
    '$basetexture',
    '$basetexture2',
    '$basetexture3',
    '$basetexture4',
    '$decaltexture',
    '$blendmodulatetexture',
    '$bumpmap',
    '$bumpmap2',
    '$bumpmask',
    '$cloudalphatexture',
    '$detail',
    '$detail2',
    '$tintmasktexture',
    '$masks',
    '$masks1',
    '$masks2',
    '$dudvmap',
    '$envmap',
    '$envmapmask',
    '$envmapmask2',
    '$flowmap',
    '$flowbounds',
    '$flow_noise_texture',
    '$emissiveblendtexture',
    '$emissiveblendbasetexture',
    '$emissiveblendflowtexture',
    '$fleshbordertexture1d',
    '$fleshcubetexture',
    '$fleshinteriornoisetexture',
    '$fleshinteriortexture',
    '$fleshnormaltexture',
    '$fleshsubsurfacetexture',
    '$hdrbasetexture',
    '$hdrcompressedtexture',
    '$lightwarptexture',
    '$material',
    '$normalmap',
    '$fresnelrangestexture',
    '$phongexponenttexture',
    '$phongwarptexture',
    '$reflecttexture',
    '$refracttexture',
    '$refracttinttexture',
    '$selfillummask',
    '$selfillumtexture',
    '$texture',
    '$texture2',
    '$worldspacetint',
    '$worldspacetype',
    '%tooltexture',
    'srgb?$basetexture',
    '$iris',
    '$ambientoccltexture',
    '$mraotexture',
    '$emissiontexture',
    '$portalmasktexture',
    '$portalcolortexture',
)

#: The one texture key that also implies an HDR variant beside it.
HDR_TEXTURE_KEY = '$envmap'

#: VMT keys whose value names another ``.vmt``. This is what makes a
#: ``Patch { include }`` chain resolve.
MATERIAL_KEYS = (
    '$bottommaterial',
    '$crackmaterial',
    '$fallbackmaterial',
    '$underwateroverlay',
    'include',
    'material',
)

#: Values that name something the engine builds at runtime rather than a
#: file on disk. ``$envmap "env_cubemap"`` appears in a large share of all
#: materials in the game; without this the missing-file report -- the whole
#: point of the tool -- would have a false line on nearly every map.
TEXTURE_DENYLIST = (
    'env_cubemap',
    '_rt_camera',
)

#: Anything starting with this is a runtime render target, not a file.
TEXTURE_DENY_PREFIX = '_rt_'

#: Entity keys whose value names a material. Matched lowercased.
ENT_MATERIAL_KEYS = (
    'material',
    'texture',
    'ropematerial',
    'overlaymaterial',
    'point_hud_icon_neutral',
    'point_hud_icon_axis',
    'point_hud_icon_allies',
    'point_hud_icon_timercap',
    'point_hud_icon_bombed',
    'spritename',
    'team_icon_0',
    'team_icon_2',
    'team_icon_3',
    'team_overlay_0',
    'team_overlay_2',
    'team_overlay_3',
    'team_base_icon_2',
    'team_base_icon_3',
    'particletrailmaterial',
    'overlayname1',
    'overlayname2',
    'overlayname3',
    'overlayname4',
    'overlayname5',
    'overlayname6',
    'overlayname7',
    'overlayname8',
    'overlayname9',
    'overlayname10',
    'font',
)

#: Entity keys whose value names a model. Matched **case-sensitively**.
ENT_MODEL_KEYS = (
    'model',
    'shootmodel',
    'point_allies_model',
    'point_axis_model',
    'point_reset_model',
    'missilemodel',
    'team_model_0',
    'team_model_2',
    'team_model_3',
    'flag_model',
    'plymodel',
    'powerup_model',
    'swapmodel',
    'prop_model_name',
    'ModelOverride',
)

#: Entity keys whose value names a sound. Matched lowercased.
ENT_SOUND_KEYS = (
    'breaksound',
    'closesound',
    'gassound',
    'gustsound',
    'locked_sound',
    'message',
    'messagesound',
    'movementsound',
    'movepingsound',
    'movesound',
    'noise1',
    'noise2',
    'puntsound',
    'reversalsoundlarge',
    'reversalsoundmedium',
    'reversalsoundsmall',
    'slidesoundback',
    'slidesoundfwd',
    'soundcloseoverride',
    'soundlockedoverride',
    'soundmoveoverride',
    'soundopenoverride',
    'soundunlockedoverride',
    'startclosesound',
    'startsound',
    'stopsound',
    'unlocked_sound',
    'point_allies_capsound',
    'point_axis_capsound',
    'point_resetsound',
    'fireendsound',
    'firestartsound',
    'flysound',
    'incomingsound',
    'launchsound',
    'pulsefiresound',
    'rotatesound',
    'rotatestartsound',
    'rotatestopsound',
    'team_capsound_0',
    'team_capsound_2',
    'team_capsound_3',
    'disablesound',
    'm_soundname',
    'commentaryfile',
    'commentaryfile_nohdr',
    'prop_pickup_sound',
    'prop_drop_sound',
)

#: Entity keys whose value names a particle system, by name rather than by
#: file. Resolved against the map's particle manifest.
ENT_PARTICLE_KEYS = (
    'effect_name',
    'particle_name',
    'explode_particle',
)

#: The six faces of a skybox, plus the empty string for the base name. Each
#: is tried with and without an ``_hdr`` infix, so one ``skyname`` produces
#: fourteen candidate materials -- most of which will not exist, which is
#: fine because they are speculative.
SKYBOX_SIDES = ('', 'bk', 'dn', 'ft', 'lf', 'rt', 'up')

#: The files that live beside a ``.mdl``. The extension is replaced, not
#: appended. Most models have only some of these.
MODEL_SIBLINGS = (
    '.dx80.vtx',
    '.dx90.vtx',
    '.phy',
    '.sw.vtx',
    '.vtx',
    '.xbox.vtx',
    '.vvd',
    '.ani',
)

#: File extensions that never have dependencies of their own, so the crawl
#: records them and stops.
LEAF_EXTENSIONS = (
    '.vtf',
    '.wav',
    '.mp3',
    '.ogg',
    '.nav',
    '.dds',
    '.jpg',
    '.jpeg',
    '.png',
    '.svg',
    '.ttf',
    '.otf',
    '.vvd',
    '.vtx',
    '.ani',
)

#: Extensions that make a sound value a real file path rather than a
#: soundscript entry name.
SOUND_EXTENSIONS = ('.wav', '.mp3', '.ogg')


def is_denied_texture(stem):
    """Whether *stem* names a runtime render target rather than a file.

    :param stem: a normalised texture path, no prefix or suffix.
    :type stem: str
    :rtype: bool
    """
    lowered = stem.lower()
    return lowered in TEXTURE_DENYLIST or lowered.startswith(TEXTURE_DENY_PREFIX)
