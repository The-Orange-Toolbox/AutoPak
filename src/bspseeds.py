"""What the map itself says it needs.

These are the references that come straight out of the BSP's lumps, before
any entity is looked at: the materials on the brushwork, the skybox, the
detail sprites, the static and detail prop models, and whatever is already
inside the map's own pakfile.

Reading the pakfile directly is worth calling out. CompilePal shells out to
``bspzip -extractfiles`` and scans the temporary directory, because it has
no way to read the lump. Having ``valvebsp`` means the same information is
one ``zipfile.ZipFile`` away, with no external process and nothing to clean
up -- and it is information the pack genuinely needs, because vbsp writes
generated water and cubemap materials in there whose parents have to be
packed.
"""

import io
import os
import struct
import zipfile

from valvebsp import Bsp
from valvebsp.lumps import (LUMP_ENTITIES, LUMP_GAME_LUMP,  # NOQA: F401
                            LUMP_PAKFILE, LUMP_TEXDATA_STRING_DATA)

import keys
import paths

#: Static prop and detail prop game lumps.
STATIC_PROPS = 'prps'
DETAIL_PROPS = 'prpd'

#: What a compressed lump starts with. valvebsp cannot read these, and
#: bspzip refuses them too.
LZMA_MAGIC = b'LZMA'

#: Where lump 0's file offset sits in a standard BSP header: 'VBSP', the
#: version, then the first lump_t.
_LUMP_TABLE = 8
_LUMP_SIZE = 16


class BspError(Exception):
    """A map AutoPak cannot read."""


def detect_profile(path):
    """Guess which engine branch wrote this map.

    Only one branch needs telling apart from its version number: Left 4
    Dead 2 reorders the fields of every lump header, and shares version 21
    with Portal 2 and Alien Swarm. CompilePal's test is that the four bytes
    where a normal BSP keeps the first lump's offset are zero, because in
    an L4D2 header those bytes are the lump's version instead.

    :param path: the map to inspect.
    :type path: str
    :returns: a valvebsp profile name, or None to let valvebsp decide.
    :rtype: str or None
    """
    try:
        with open(path, 'rb') as handle:
            head = handle.read(_LUMP_TABLE + 4)
    except (IOError, OSError) as error:
        raise BspError('cannot read {}: {}'.format(path, error))

    if len(head) < _LUMP_TABLE + 4 or head[:4] != b'VBSP':
        raise BspError('not a bsp: ' + path)

    version, first = struct.unpack_from('<iI', head, 4)
    if version == 21 and first == 0:
        return 'L4D2'
    return None


def check_readable(path):
    """Fail early on a map whose lumps are compressed.

    Checked before anything else so the message is the first thing the user
    sees, rather than surfacing twenty seconds later as a construct
    traceback from somewhere deep in a lump reader.

    :raises BspError: when a lump AutoPak needs is LZMA compressed.
    """
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()

            handle.seek(0)
            head = handle.read(_LUMP_TABLE + 64 * _LUMP_SIZE)

            for lump in (LUMP_ENTITIES, LUMP_PAKFILE):
                at = _LUMP_TABLE + lump * _LUMP_SIZE
                if at + 4 > len(head):
                    continue
                offset = struct.unpack_from('<I', head, at)[0]
                if offset == 0 or offset + 4 > size:
                    continue
                handle.seek(offset)
                if handle.read(4) == LZMA_MAGIC:
                    raise BspError(
                        'this map has compressed lumps, which AutoPak '
                        'cannot read. Decompress it first:\n'
                        '    bspzip -repack ' + os.path.basename(path))
    except (IOError, OSError) as error:
        raise BspError('cannot read {}: {}'.format(path, error))


def read(path, profile=None):
    """Open the map.

    :param path: the map to read.
    :type path: str
    :param profile: a valvebsp profile name, or None to autodetect.
    :type profile: str, optional
    :rtype: valvebsp.Bsp
    :raises BspError: when the map is compressed or will not parse.
    """
    check_readable(path)

    if profile is None:
        profile = detect_profile(path)

    try:
        return Bsp(path, profile=profile)
    except BspError:
        raise
    except Exception as error:
        raise BspError('cannot read {}: {}'.format(os.path.basename(path),
                                                   error))


def worldspawn(bsp):
    """The map's worldspawn keyvalues.

    :returns: the first entity's keys, later duplicates losing to earlier
        ones, or an empty dict if the map somehow has no entities.
    :rtype: dict
    """
    entities = bsp[LUMP_ENTITIES]
    if not entities:
        return {}

    found = {}
    for key, value in entities[0]:
        found.setdefault(key.lower(), value)
    return found


def pakfile_names(bsp):
    """Every path already inside the map's pakfile.

    :returns: lowercase, forward-slashed paths. Empty when the map has no
        pakfile or it will not open as a zip.
    :rtype: set
    """
    try:
        raw = bytes(bsp[LUMP_PAKFILE])
    except Exception:
        return set()

    if not raw:
        return set()

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return set(name.replace('\\', '/').lower()
                       for name in archive.namelist())
    except (zipfile.BadZipFile, EOFError, ValueError):
        return set()


def pakfile_materials(bsp):
    """Materials referenced by the VMTs already inside the map.

    vbsp generates water, cubemap and blend materials straight into the
    pakfile. They are usually ``Patch`` materials naming a parent that does
    have to be packed, so the embedded ones have to be read even though they
    are already in the map.

    :returns: (internal path, origin) pairs.
    :rtype: list
    """
    from formats import vmt

    try:
        raw = bytes(bsp[LUMP_PAKFILE])
    except Exception:
        return []

    if not raw:
        return []

    found = []
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith('.vmt'):
                    continue
                try:
                    text = archive.read(name).decode('latin-1', 'replace')
                except (KeyError, RuntimeError, zipfile.BadZipFile):
                    continue
                origin = 'pakfile ' + name.replace('\\', '/')
                for reference in vmt.references(text):
                    found.append((reference, origin))
    except (zipfile.BadZipFile, EOFError, ValueError):
        return []

    return found


def brush_materials(bsp):
    """The materials named by the map's texdata string table.

    This is the brushwork: every face, displacement and tool texture the
    compiler recorded.

    :returns: (internal path, origin) pairs.
    :rtype: list
    """
    found = []
    for name in bsp[LUMP_TEXDATA_STRING_DATA]:
        if not name:
            continue

        # The table is not consistent about how it spells a name. A
        # material at the root of materials/ carries a leading slash, and
        # some maps record the '.vmt' suffix while most do not -- appending
        # it blindly gives 'water_2fort_beneath.vmt.vmt', which resolves
        # nowhere and turns into a missing-file report for content that is
        # sitting right there. Normalising first settles all of it.
        stem = paths.vmt_path(name)
        if not stem:
            continue

        internal = paths.internal_path('materials/' + stem + '.vmt').lower()
        found.append((paths.unpatch_wvt(internal), 'texdata'))

    return found


def skybox_materials(sky_name, origin='worldspawn skyname'):
    """The fourteen candidate faces of a skybox.

    Six sides plus the bare name, each with and without an ``_hdr`` infix.
    Most will not exist -- a skybox is either LDR or HDR, rarely both -- so
    every one of these is speculative and a miss is not worth reporting.

    :param sky_name: the value of ``skyname``.
    :type sky_name: str
    :returns: (internal path, origin) pairs.
    :rtype: list
    """
    sky_name = paths.vmt_path(sky_name)
    if not sky_name:
        return []

    found = []
    for side in keys.SKYBOX_SIDES:
        found.append(('materials/skybox/{}{}.vmt'.format(sky_name, side).lower(),
                      origin))
        found.append(('materials/skybox/{}_hdr{}.vmt'.format(sky_name, side).lower(),
                      origin))
    return found


def world_materials(bsp, mapname):
    """The materials worldspawn names, plus the map's menu photo.

    :returns: (internal path, origin, speculative) triples.
    :rtype: list
    """
    world = worldspawn(bsp)
    found = []

    sky_name = world.get('skyname')
    if sky_name:
        for internal, origin in skybox_materials(sky_name):
            found.append((internal, origin, True))

    detail = world.get('detailmaterial')
    if detail:
        internal = 'materials/' + paths.vmt_path(detail) + '.vmt'
        found.append((internal.lower(), 'worldspawn detailmaterial', False))

    # The loading-screen photo. Most maps do not have one, so a miss here
    # is not a problem worth telling anyone about.
    found.append(('materials/vgui/maps/menu_photos_{}.vmt'.format(mapname).lower(),
                  'map menu photo', True))

    return found


def detail_sprite_file(bsp):
    """The detail sprite definition worldspawn names, if any.

    :returns: (internal path, origin) or None.
    :rtype: tuple or None
    """
    world = worldspawn(bsp)
    value = world.get('detailvbsp')
    if not value:
        return None
    return (paths.internal_path(value).lower(), 'worldspawn detailvbsp')


def prop_models(bsp):
    """Every static and detail prop model, with the skins actually used.

    Collecting the skins in one pass matters: a model referenced by two
    hundred props must be added once, carrying every skin family any of
    them asked for, or the crawl either packs materials nothing uses or
    misses ones something does.

    :returns: {internal path: set of skin indices}
    :rtype: dict
    """
    found = {}

    static = _game_lump(bsp, STATIC_PROPS)
    if static is not None:
        names = list(getattr(static, 'dictLump', ()) or ())
        for prop in getattr(static, 'objectLump', ()) or ():
            index = getattr(prop, 'propType', None)
            if index is None or index < 0 or index >= len(names):
                continue
            internal = paths.internal_path(names[index]).lower()
            found.setdefault(internal, set()).add(getattr(prop, 'skin', 0) or 0)

        # A model in the dictionary that no prop points at is unusual but
        # harmless; pack it with skin 0 rather than reasoning about why.
        for name in names:
            found.setdefault(paths.internal_path(name).lower(), {0})

    detail = _game_lump(bsp, DETAIL_PROPS)
    if detail is not None:
        for name in getattr(detail, 'dictLump', ()) or ():
            if not name:
                continue
            found.setdefault(paths.internal_path(name).lower(), set()).add(0)

    return found


def _game_lump(bsp, identifier):
    """Read one game lump, or None when the map does not have it."""
    try:
        return bsp[identifier]
    except Exception:
        return None
