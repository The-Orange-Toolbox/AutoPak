r""".. PCF - particle systems

A particle system names the material its sprites draw with, and sometimes a
model. Both are ordinary string attributes on the system or on one of its
operators:

.. code-block:: none

    material    "effects\bubble.vmt"

Note the backslashes and the explicit suffix -- the format stores what the
particle editor wrote, so the value goes through the usual normalisation
rather than being used as-is.

Systems can also spawn other systems as children. Those live in the same
file often enough that following them costs nothing, and the walk needs a
depth guard anyway because nothing stops a particle file from describing a
loop.
"""

import paths

#: Attribute type 5 is a string. Everything worth reading here is one.
STRING = 5

#: Attribute names whose value is a material.
MATERIAL_ATTRIBUTES = ('material',)

#: How deep to follow child systems. Real particle trees are two or three
#: levels; anything deeper is a cycle the child links do not forbid.
MAX_DEPTH = 16


class ParticleError(Exception):
    """A particle file that could not be read."""


def _operators(system):
    """Every operator list a system carries, plus the system itself."""
    yield system
    for group in ('renderers', 'operators', 'initializers', 'emitters',
                  'forces', 'constraints'):
        for operator in getattr(system, group, ()) or ():
            yield operator


def _strings(node):
    """The string attributes of one node, as (name, value)."""
    for attribute in getattr(node, 'attributes', ()) or ():
        if getattr(attribute, '_type', None) != STRING:
            continue
        value = getattr(attribute, '_data', None)
        if isinstance(value, bytes):
            value = value.decode('latin-1', 'replace')
        if not value:
            continue
        yield str(getattr(attribute, '_name', '')).lower(), str(value)


def system_references(system, seen=None, depth=0):
    """The materials and models one particle system needs.

    :returns: (materials, models) -- both lists of internal paths.
    :rtype: tuple
    """
    if seen is None:
        seen = set()

    identity = id(system)
    if identity in seen or depth > MAX_DEPTH:
        return [], []
    seen.add(identity)

    materials = []
    models = []

    for node in _operators(system):
        for name, value in _strings(node):
            lowered = value.lower()

            if name in MATERIAL_ATTRIBUTES or lowered.endswith(('.vmt', '.vtf')):
                stem = paths.vmt_path(value)
                if stem:
                    materials.append('materials/{}.vmt'.format(stem).lower())

            elif lowered.endswith('.mdl'):
                models.append(paths.internal_path(value).lower())

    for child in getattr(system, 'children', ()) or ():
        target = getattr(child, 'ref', None)
        if target is None:
            continue
        child_materials, child_models = system_references(target, seen,
                                                          depth + 1)
        materials.extend(child_materials)
        models.extend(child_models)

    return materials, models


def names(path):
    """The particle systems a file defines.

    Used to work out which files a map's named effects come from.

    :rtype: list
    """
    from valvepcf import Pcf

    try:
        pcf = Pcf(path)
    except Exception as error:
        raise ParticleError(str(error))

    return [str(getattr(system, '_name', '')) for system in pcf.systems
            if getattr(system, '_name', None)]


def dependencies(path):
    """Everything a particle file needs.

    :param path: an absolute path to a ``.pcf``.
    :type path: str
    :returns: (materials, models) -- both lists of internal paths.
    :rtype: tuple
    :raises ParticleError: when the file cannot be parsed.
    """
    from valvepcf import Pcf

    try:
        pcf = Pcf(path)
    except Exception as error:
        raise ParticleError(str(error))

    materials = []
    models = []

    try:
        for system in pcf.systems:
            found_materials, found_models = system_references(system)
            materials.extend(found_materials)
            models.extend(found_models)
    except Exception as error:
        raise ParticleError(str(error))

    return _unique(materials), _unique(models)


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
