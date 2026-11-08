"""Building small but genuinely valid BSPs to test against.

Shipping a real map as a fixture would mean a multi-megabyte binary in the
repository that nobody can review, and testing against an installed game
means the tests only pass on a machine that has one. So the tests build the
maps they need, one lump at a time.

Only the lumps AutoPak reads are filled in. valvebsp loads lumps lazily, so
the rest can stay empty and the file is still a map as far as anything here
is concerned.
"""

import io
import struct
import zipfile

#: 'VBSP', the version, 64 lump headers of 16 bytes, then the map revision.
LUMP_COUNT = 64
HEADER_SIZE = 4 + 4 + LUMP_COUNT * 16 + 4

LUMP_ENTITIES = 0
LUMP_GAME_LUMP = 35
LUMP_PAKFILE = 40
LUMP_TEXDATA_STRING_DATA = 43

WORLDSPAWN = [('classname', 'worldspawn')]


def entity_lump(entities):
    """Render entities the way the compiler writes them.

    :param entities: each a list of (key, value) pairs.
    :type entities: list
    :rtype: bytes
    """
    blocks = []
    for entity in entities:
        lines = ['{']
        for key, value in entity:
            lines.append('"{}" "{}"'.format(key, value))
        lines.append('}')
        blocks.append('\n'.join(lines))
    return ('\n'.join(blocks) + '\n').encode('latin-1') + b'\x00'


def texdata_lump(names):
    """The null-separated material name table."""
    if not names:
        return b'\x00'
    return b''.join(name.encode('latin-1') + b'\x00' for name in names)


def pakfile_lump(files):
    """A zip, the way the pakfile lump holds one.

    :param files: {internal path: bytes or str}
    :type files: dict
    :rtype: bytes
    """
    if not files:
        return b''

    buffer = io.BytesIO()
    # ZIP_STORED because that is what the engine expects of a pakfile.
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_STORED) as archive:
        for name, data in sorted(files.items()):
            if isinstance(data, str):
                data = data.encode('latin-1')
            archive.writestr(name, data)
    return buffer.getvalue()


def static_prop_lump(models, props=None, version=10):
    """A 'sprp' game lump: a model dictionary and the props using it.

    :param models: model paths, in dictionary order.
    :type models: list
    :param props: (model index, skin) pairs. Defaults to one prop per model.
    :type props: list
    :rtype: bytes
    """
    if props is None:
        props = [(index, 0) for index in range(len(models))]

    body = struct.pack('<i', len(models))
    for name in models:
        body += name.encode('latin-1').ljust(128, b'\x00')[:128]

    body += struct.pack('<i', 0)          # leaf entries, none needed
    body += struct.pack('<i', len(props))

    for index, skin in props:
        body += struct.pack('<fff', 0.0, 0.0, 0.0)   # origin
        body += struct.pack('<fff', 0.0, 0.0, 0.0)   # angles
        body += struct.pack('<H', index)             # propType
        body += struct.pack('<HH', 0, 0)             # first leaf, leaf count
        body += struct.pack('<BB', 6, 0)             # solidity, flags
        body += struct.pack('<i', skin)
        body += struct.pack('<ff', 0.0, 0.0)         # fade distances
        body += struct.pack('<fff', 0.0, 0.0, 0.0)   # lighting origin
        body += struct.pack('<f', 0.0)               # forced fade scale
        # min/max CPU and GPU levels: four single bytes, not two shorts.
        # Getting this wrong makes every prop after the first read from
        # four bytes off, which shows up as nonsense skins.
        body += struct.pack('<BBBB', 0, 0, 0, 0)
        body += struct.pack('<BBBB', 255, 255, 255, 255)   # diffuse modulation
        body += struct.pack('<I', 0)                 # flagsEx

    return body, version


def game_lump(static=None):
    """The game lump directory, holding at most a static prop lump."""
    if static is None:
        return b''

    body, version = static
    count = 1
    # Header: count, then one dgamelump_t of id, flags, version, offset,
    # length. The offset is from the start of the file, so it is patched in
    # by the writer once the lump's own position is known.
    header = struct.pack('<i', count)
    # The id is the FourCC 'sprp' stored as a little-endian int, so the
    # bytes on disk read forward as 'prps' -- which is the spelling
    # valvebsp indexes game lumps by.
    header += b'prps'
    header += struct.pack('<HH', 0, version)
    header += struct.pack('<ii', 0, len(body))   # offset patched later
    return header + body


def build_bsp(path, entities=None, textures=None, pakfile=None,
              static_props=None, version=20):
    """Write a map holding exactly what the caller asked for.

    :param entities: entity keyvalue lists. Defaults to a bare worldspawn.
    :type entities: list, optional
    :param textures: the brush material names.
    :type textures: list, optional
    :param pakfile: {internal path: content} already inside the map.
    :type pakfile: dict, optional
    :param static_props: model paths for the static prop dictionary.
    :type static_props: list, optional
    :returns: *path*
    :rtype: str
    """
    if entities is None:
        entities = [WORLDSPAWN]

    static = None
    if static_props:
        static = static_prop_lump(static_props)

    lumps = {
        LUMP_ENTITIES: entity_lump(entities),
        LUMP_TEXDATA_STRING_DATA: texdata_lump(textures or []),
        LUMP_PAKFILE: pakfile_lump(pakfile or {}),
        LUMP_GAME_LUMP: game_lump(static),
    }

    directory = {}
    body = bytearray()
    for index in sorted(lumps):
        data = lumps[index]
        if not data:
            directory[index] = (0, 0)
            continue
        offset = HEADER_SIZE + len(body)
        directory[index] = (offset, len(data))
        body += data
        # Lumps are four-byte aligned.
        while len(body) % 4:
            body += b'\x00'

    # The game lump's own entries carry absolute file offsets, so the one
    # inside it has to be fixed up now that the lump has a home.
    if static is not None:
        game_offset = directory[LUMP_GAME_LUMP][0]
        at = game_offset - HEADER_SIZE + 4 + 4 + 4      # count, id, flags+ver
        struct.pack_into('<i', body, at, game_offset + 20)

    header = bytearray()
    header += b'VBSP'
    header += struct.pack('<i', version)
    for index in range(LUMP_COUNT):
        offset, length = directory.get(index, (0, 0))
        header += struct.pack('<iii', offset, length, 0)
        header += b'\x00' * 4                            # fourCC
    header += struct.pack('<i', 1)                       # map revision

    with open(path, 'wb') as handle:
        handle.write(bytes(header))
        handle.write(bytes(body))

    return path
