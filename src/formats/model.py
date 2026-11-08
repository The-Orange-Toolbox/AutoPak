""".. MDL - models, and everything a model drags in with it

A model is the most expensive thing to get wrong, because it is never one
file. Every ``.mdl`` has a handful of siblings holding its vertices and its
per-detail-level meshes, and if any of them is left out the model either
fails to load or loads with no geometry -- both of which look, to a player,
exactly like the map being broken.

Then there are the materials. A model does not name them outright; it names
a list of directories and a list of bare texture names, and the engine tries
every combination until one exists. AutoPak has to do the same, which means
generating a cross product most of whose entries will not resolve. That is
fine, and it is why they are speculative.

Skins narrow that down. A model with fifteen skin families and one mesh
names fifteen materials, of which a map placing it with skin 3 needs
exactly one. Packing all fifteen is not wrong, only wasteful, so when the
skin table cannot be read confidently this falls back to packing everything.

Everything here is wrapped: ValveMDL is a young library being asked to parse
whatever a decade of third-party model exporters produced, and one bad model
must cost a warning, not the run.
"""

import os

import keys
import paths


class ModelError(Exception):
    """A model that could not be read."""


def siblings(internal, pack_swvtx=True):
    """The files that have to travel with a ``.mdl``.

    The extension is replaced, not appended: ``x.mdl`` becomes
    ``x.dx90.vtx``. Most models have only some of these, so every one is a
    guess and a miss is not worth reporting.

    :param internal: the model's engine path.
    :type internal: str
    :returns: internal paths, the ``.mdl`` itself excluded.
    :rtype: list
    """
    found = []
    for extension in keys.MODEL_SIBLINGS:
        if extension == '.sw.vtx' and not pack_swvtx:
            continue
        found.append(paths.replace_extension(internal, extension).lower())
    return found


def _directories(mdl):
    """The model's material search directories, normalised.

    A model stores these with Windows separators and a trailing one, and
    occasionally with a leading one that would make the joined path
    absolute.
    """
    found = []
    for directory in mdl.cdtextures or ():
        cleaned = str(directory).replace('\\', '/').strip().lstrip('/')
        if cleaned and not cleaned.endswith('/'):
            cleaned += '/'
        found.append(cleaned)
    return found or ['']


def _used_material_indices(mdl):
    """Which entries of the skin table the model's meshes actually use.

    Without this the table's full width gets packed, which for a model with
    fifteen skins and one mesh is fourteen materials nothing references.
    """
    used = set()
    for mesh in getattr(mdl, 'meshes', ()) or ():
        index = getattr(mesh, 'material', None)
        if index is not None and index >= 0:
            used.add(index)
    return used


def texture_names(mdl, skins=None):
    """The texture names a model needs, narrowed to the skins in use.

    :param skins: the skin families the map actually places this model
        with. None or empty means "no information", and everything the
        model names is returned.
    :type skins: set, optional
    :rtype: list
    """
    names = [str(texture.name) for texture in getattr(mdl, 'textures', ()) or ()]
    if not names:
        return []

    table = getattr(mdl, 'skins', None)
    used = _used_material_indices(mdl)

    # No skin table, no mesh information, or nothing asked for in
    # particular: pack the lot. Over-packing a few materials is a much
    # better failure than missing one.
    if not skins or not table or not used:
        return names

    wanted = set()
    out_of_range = False

    for family in skins:
        if not isinstance(family, int) or family < 0 or family >= len(table):
            out_of_range = True
            continue
        wanted.add(family)

    # A prop asking for a skin the model does not have falls back to skin 0
    # in the engine, so pack that too rather than nothing.
    if out_of_range or not wanted:
        wanted.add(0)

    indices = set()
    for family in wanted:
        if family >= len(table):
            continue
        row = table[family]
        for index in used:
            if 0 <= index < len(row):
                indices.add(row[index])

    if not indices:
        return names

    return [names[i] for i in sorted(indices) if 0 <= i < len(names)]


def materials(mdl, skins=None):
    """Every material a model might name.

    The cross product of its search directories and its texture names. Most
    combinations will not exist; the engine tries them all too.

    :rtype: list
    """
    found = []
    for directory in _directories(mdl):
        for name in texture_names(mdl, skins):
            stem = paths.vmt_path(directory + str(name))
            if not stem:
                continue
            found.append('materials/{}.vmt'.format(stem).lower())
    return _unique(found)


def replacement_materials(mdl):
    """Materials named by the model's detail-level replacement tables.

    The engine swaps to cheaper materials at distance, and those swaps name
    textures that appear nowhere else in the model.

    :rtype: list
    """
    try:
        vtx = mdl.get_vtx()
    except Exception:
        return []

    names = []
    try:
        for table in vtx.material_replacements or ():
            for replacement in getattr(table, 'replacements', ()) or ():
                name = getattr(replacement, 'name', None)
                if name:
                    names.append(str(name))
    except Exception:
        return []

    found = []
    for directory in _directories(mdl):
        for name in names:
            stem = paths.vmt_path(directory + name)
            if stem:
                found.append('materials/{}.vmt'.format(stem).lower())
    return _unique(found)


def include_models(mdl):
    """The models named by ``$includemodel``.

    Usually shared animation sets. The engine loads them alongside, so they
    have to be packed alongside.

    :rtype: list
    """
    found = []
    for group in getattr(mdl, 'includemodels', ()) or ():
        name = getattr(group, 'name', None)
        if name:
            found.append(paths.internal_path(str(name)).lower())
    return _unique(found)


def keyvalue_models(mdl):
    """Models named in a model's embedded keyvalues.

    Breakable props name their damaged replacements under
    ``door_options``. Nothing else in the map references them, so without
    this a door that breaks turns into an ERROR sign.

    :rtype: list
    """
    from formats import kv1

    header = getattr(mdl, 'header', None)
    if header is None:
        return []

    size = getattr(header, 'keyvaluesize', 0) or 0
    index = getattr(header, 'keyvalueindex', 0) or 0
    if size <= 0 or index <= 0:
        return []

    data = getattr(mdl, '_data', None)
    if not data:
        return []

    text = data[index:index + size].decode('latin-1', 'replace')
    text = text.split('\x00', 1)[0]

    root = kv1.parse(text)
    found = []
    for block in ('door_options',):
        options = root.first_block(block)
        if options is None:
            # The blob is usually wrapped in a 'mdlkeyvalue' block.
            for _, value in root.pairs:
                if isinstance(value, kv1.Node):
                    options = value.first_block(block)
                    if options is not None:
                        break
        if options is None:
            continue

        for key in ('damage1', 'damage2', 'damage3'):
            value = options.find_first(key)
            if not value:
                continue
            name = paths.internal_path(str(value)).lower()
            if not name.endswith('.mdl'):
                name += '.mdl'
            if not name.startswith('models/'):
                name = 'models/' + name
            found.append(name)

    return _unique(found)


def dependencies(path, skins=None):
    """Everything a model on disk needs.

    :param path: an absolute path to a ``.mdl``.
    :type path: str
    :param skins: the skin families the map places it with.
    :type skins: set, optional
    :returns: (materials, models) -- both lists of internal paths.
    :rtype: tuple
    :raises ModelError: when the model cannot be parsed at all. The caller
        still packs its siblings; only the materials are lost.
    """
    from valvemdl import Mdl

    try:
        mdl = Mdl(path)
    except Exception as error:
        raise ModelError(str(error))

    try:
        found_materials = materials(mdl, skins) + replacement_materials(mdl)
        found_models = include_models(mdl) + keyvalue_models(mdl)
    except Exception as error:
        raise ModelError(str(error))

    return _unique(found_materials), _unique(found_models)


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
