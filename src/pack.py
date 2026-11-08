"""The packing run, start to finish.

This is the only module the CLI talks to. It owns the order of the passes --
read the map, build the search paths, seed from the lumps, crawl the
dependencies, write the list -- and what the user is told about each.
Everything it calls is either a pure parser or a single-purpose helper; the
sequencing lives here so there is one place to read to know what a run does.
"""

import json
import os
import time

import bspseeds
import content
import entities
import filelist
import gameinfo
import graph
import paths
import utilityfiles

from report import Report
from utils.pacifier import Pacifier

from formats import (detailvbsp, manifest, model, nut, pcf, phy, radar,
                     res, soundscript, vmt)


class PackError(Exception):
    """A run that cannot sensibly continue.

    Raised for conditions the user can act on -- a compressed map, a game
    folder with no search paths -- and turned into a one-line message by the
    CLI. Anything else is a bug, and belongs in the traceback TOTExecutable
    prints.
    """


def expand_material(packlist, internal, external, extra):
    """A material needs its textures, and whatever it patches."""
    textures, references, truncated = vmt.dependencies(external)

    if truncated:
        packlist.report.warn('material ends mid-block: ' + internal)

    for texture in textures:
        packlist.add(texture, graph.KIND_TEXTURE, internal)

    for reference in references:
        packlist.add(reference, graph.KIND_MATERIAL, internal)


def expand_model(packlist, internal, external, extra):
    """A model needs its siblings, its materials, and whatever it includes.

    The siblings go in first and unconditionally. If the header will not
    parse we lose the materials, but the model itself still loads -- which
    is a far better outcome than dropping it entirely.
    """
    # The siblings are counted as model files so the summary reads
    # sensibly, but only the .mdl carries the header worth opening.
    if not internal.lower().endswith('.mdl'):
        return

    for sibling in model.siblings(internal, packlist.pack_swvtx):
        packlist.add(sibling, graph.kind_for(sibling), internal,
                     speculative=True)

    # The collision model names the gibs this breaks into. Nothing else in
    # the map does.
    collision = paths.replace_extension(internal, '.phy').lower()
    asset = packlist.assets.get(collision)
    if asset is not None and asset['external']:
        for gib in phy.dependencies(asset['external']):
            packlist.add(gib, graph.KIND_MODEL, collision)

    skins = packlist.model_skins.get(internal)

    try:
        materials, models = model.dependencies(external, skins)
    except model.ModelError as error:
        packlist.report.warn('could not read model {}: {}'.format(
            internal, error))
        return

    for material in materials:
        # Cross-product guesses: the engine tries every search directory
        # against every texture name, and so do we.
        packlist.add(material, graph.KIND_MATERIAL, internal,
                     speculative=len(materials) > 1)

    for included in models:
        packlist.add(included, graph.KIND_MODEL, internal)


def expand_particle(packlist, internal, external, extra):
    """A particle system needs the materials its sprites draw with."""
    try:
        materials, models = pcf.dependencies(external)
    except pcf.ParticleError as error:
        packlist.report.warn('could not read particles {}: {}'.format(
            internal, error))
        return

    for material in materials:
        packlist.add(material, graph.KIND_MATERIAL, internal)

    for name in models:
        packlist.add(name, graph.KIND_MODEL, internal)


def expand_script(packlist, internal, external, extra):
    """Scripts of several kinds share one entry, sorted out by extension."""
    lowered = internal.lower()

    if lowered.endswith('.nut'):
        _expand_vscript(packlist, internal, external)
    elif lowered.endswith('.pcf'):
        expand_particle(packlist, internal, external, extra)
    elif 'soundscapes_' in lowered or '_level_sounds' in lowered:
        for sound in soundscript.dependencies(external):
            packlist.add(sound, graph.KIND_SOUND, internal)
    elif 'overviews/' in lowered:
        materials, radars = radar.dependencies(external)
        for material in materials:
            packlist.add(material, graph.KIND_MATERIAL, internal)
        for image in radars:
            packlist.add(image, graph.KIND_TEXTURE, internal,
                         speculative=True)
    elif '_particles' in lowered or lowered.endswith('particles.txt'):
        for name in manifest.dependencies(external):
            packlist.add(name, graph.KIND_PARTICLE, internal)


def _expand_vscript(packlist, internal, external):
    found = nut.dependencies(external)

    for name in found.scripts:
        packlist.add(name, graph.KIND_SCRIPT, internal)

    for name in found.models:
        packlist.add(name, graph.KIND_MODEL, internal)

    for name in found.sounds:
        packlist.add(name, graph.KIND_SOUND, internal)

    # Explicit hints: the script author naming content no scanner could
    # have worked out.
    for name in found.files:
        packlist.add(name, graph.kind_for(name), internal + ' hint')

    for directory in found.directories:
        for name in packlist.index_directory(directory):
            packlist.add(name, graph.kind_for(name), internal + ' hint')


def expand_resource(packlist, internal, external, extra):
    """A vgui layout needs the images it draws."""
    images, bases = res.dependencies(external)

    for image in images:
        packlist.add(image, graph.KIND_MATERIAL, internal)

    for base in bases:
        packlist.add(base, graph.KIND_RESOURCE, internal)


def expand_misc(packlist, internal, external, extra):
    """The odds and ends that still carry references."""
    if internal.lower().endswith('.vbsp'):
        materials, models = detailvbsp.dependencies(external)
        for material in materials:
            packlist.add(material, graph.KIND_MATERIAL, internal)
        for name in models:
            packlist.add(name, graph.KIND_MODEL, internal)


#: What to do with each kind of packed asset. Kinds with no entry are
#: leaves: a .vtf or a .wav is recorded and the crawl stops there.
EXPANDERS = {
    graph.KIND_MATERIAL: expand_material,
    graph.KIND_MODEL: expand_model,
    graph.KIND_PARTICLE: expand_particle,
    graph.KIND_SCRIPT: expand_script,
    graph.KIND_RESOURCE: expand_resource,
    graph.KIND_MISC: expand_misc,
}


def pack(bsp_path=None, game_dir=None, source_dirs=None, profile=None,
         use_vpk=True, includes=None, include_dirs=None,
         include_file_lists=None, excludes=None, exclude_dirs=None,
         exclude_vpks=None, pack_swvtx=True, rename_nav=False,
         rename_particle_manifest=False, utility_files=True,
         output_path=None, to_stdout=False, report_style='summary',
         verbose=False, quiet=False):
    """Scan *bsp_path* and write the bspzip file list.

    :param bsp_path: the compiled map to scan. Never modified.
    :type bsp_path: str
    :param game_dir: the mod folder holding gameinfo.txt.
    :type game_dir: str
    :param output_path: where the file list is written.
    :type output_path: str
    :returns: counts for the run, a per-kind breakdown, and the references
        that resolved nowhere.
    :rtype: dict
    :raises PackError: when the map or the game folder cannot be read.
    """
    report = Report(verbose=verbose, quiet=quiet)
    mapname = os.path.splitext(os.path.basename(bsp_path))[0]

    report.say('reading ' + os.path.basename(bsp_path))
    try:
        bsp = bspseeds.read(bsp_path, profile=profile)
    except bspseeds.BspError as error:
        raise PackError(str(error))

    index = _build_index(game_dir, source_dirs, bsp, use_vpk, report)

    packlist = graph.PackList(index, report, pack_swvtx=pack_swvtx)
    packlist.exclude(internal_paths=_internal_excludes(index, excludes),
                     prefixes=_internal_excludes(index, exclude_dirs))
    _exclude_vpks(packlist, exclude_vpks, report)

    _seed(packlist, bsp, mapname, report)

    if utility_files:
        _seed_utility(packlist, index, mapname, rename_nav,
                      rename_particle_manifest)

    _apply_includes(packlist, index, includes, include_dirs,
                    include_file_lists, report)

    _check_particles(packlist, report)

    pacifier = Pacifier(prefix='crawling:', enabled=not quiet and not verbose)
    started = time.time()
    pacifier.start()
    try:
        packlist.run(EXPANDERS, pacifier=pacifier)
    except BaseException:
        pacifier.abort()
        raise
    pacifier.end(' ({:.1f})'.format(time.time() - started))

    packed = packlist.packed()
    filelist.check(packed, report)

    _report_missing(packlist, report)
    report.summary()

    written = _write(packed, output_path, to_stdout, report)

    summary = _summarise(packlist)
    _report_counts(summary, report, report_style, packlist)

    if written is not None:
        report.say('wrote ' + os.path.basename(written))

    return summary


def _build_index(game_dir, source_dirs, bsp, use_vpk, report):
    """Work out where content lives, and what is already in the map."""
    try:
        directories, vpks = gameinfo.search_paths(game_dir)
    except gameinfo.GameinfoError as error:
        raise PackError(str(error))

    # The user's own directories come first: if they went to the trouble of
    # naming one, they mean it to win.
    directories = list(source_dirs or ()) + directories

    if not directories:
        raise PackError('no content directories found for ' + game_dir)

    pakfile = bspseeds.pakfile_names(bsp)
    index, failures = content.build(directories=directories, vpk_paths=vpks,
                                    pakfile=pakfile, use_vpk=use_vpk)

    for path, reason in failures:
        report.warn('could not read vpk {}: {}'.format(
            os.path.basename(path), reason))

    report.say('search paths:       {} directories, {} vpks'.format(
        len(directories), len(index.vpks.sources) if index.vpks else 0))

    return index


def _seed(packlist, bsp, mapname, report):
    """Everything the map's own lumps ask for."""
    for internal, origin in bspseeds.brush_materials(bsp):
        packlist.add(internal, graph.KIND_MATERIAL, origin)

    for internal, origin, speculative in bspseeds.world_materials(bsp, mapname):
        packlist.add(internal, graph.KIND_MATERIAL, origin,
                     speculative=speculative)

    detail = bspseeds.detail_sprite_file(bsp)
    if detail is not None:
        packlist.add(detail[0], graph.KIND_MISC, detail[1], speculative=True)

    # Materials the compiler generated into the map. They are already
    # packed, but they patch materials that may not be.
    for internal, origin in bspseeds.pakfile_materials(bsp):
        packlist.add(internal, graph.KIND_MATERIAL, origin)

    # Skins are collected for every prop before any model is added, so a
    # model placed two hundred times is resolved once carrying every skin
    # family those props asked for.
    packlist.model_skins = bspseeds.prop_models(bsp)
    for internal in packlist.model_skins:
        packlist.add(internal, graph.KIND_MODEL, 'static prop')

    _seed_entities(packlist, bsp)


def _seed_entities(packlist, bsp):
    """Everything the map's entities ask for."""
    from valvebsp.lumps import LUMP_ENTITIES

    found = entities.collect(bsp[LUMP_ENTITIES])

    for internal, origin in found.materials:
        packlist.add(internal, graph.KIND_MATERIAL, origin)

    for internal, origin in found.models:
        packlist.add(internal, graph.KIND_MODEL, origin)

    for internal, origin in found.sounds:
        packlist.add(internal, graph.KIND_SOUND, origin)

    for name, origin in found.scripted_sounds:
        packlist.add_scripted(name, origin)

    for internal, origin in found.scripts:
        packlist.add(internal, graph.KIND_SCRIPT, origin)

    for internal, origin in found.misc:
        packlist.add(internal, graph.kind_for(internal), origin)

    # Particles are named, not pathed. Resolving them needs the map's
    # manifest, which arrives in the next milestone; until then they are
    # remembered so nothing is lost.
    packlist.particle_names = found.particles


def _seed_utility(packlist, index, mapname, rename_nav,
                  rename_particle_manifest):
    """The sidecar files a map has by convention rather than by reference."""
    found = utilityfiles.probe(index, mapname, rename_nav=rename_nav,
                               rename_particle_manifest=rename_particle_manifest)

    for probed, internal, kind, origin in found:
        if probed == internal:
            packlist.add(internal, kind, origin, speculative=True)
            continue

        # A renamed file: the bytes come from where it actually is, but it
        # goes into the map under the name the engine will look for.
        external = index.find_loose(probed)
        if external is None:
            continue
        packlist.add(internal, kind, origin, speculative=True,
                     external=external)


def _check_particles(packlist, report):
    """Say something when a map uses particles it has no manifest for.

    The engine only loads a map's custom particles if the manifest names
    the file, so a map with custom effects and no manifest shows nothing at
    all -- and looks, to the mapper who has the .pcf installed locally,
    like it works.
    """
    if not packlist.particle_names:
        return

    has_manifest = any('_particles' in key or key.endswith('particles.txt')
                       for key in packlist.assets)

    if not has_manifest:
        names = sorted(set(name for name, _ in packlist.particle_names))
        report.warn(
            'the map uses {} particle effect(s) but has no particle '
            'manifest, so none of them will load: {}'.format(
                len(names), ', '.join(names[:5])
                + ('...' if len(names) > 5 else '')))


def _apply_includes(packlist, index, includes, include_dirs,
                    include_file_lists, report):
    """Force-pack whatever the user named on the command line."""
    for external in includes or ():
        _include_file(packlist, index, external, report)

    for directory in include_dirs or ():
        for root, _, names in os.walk(directory):
            for name in names:
                _include_file(packlist, index, os.path.join(root, name),
                              report)

    for path in include_file_lists or ():
        for internal, external in _read_file_list(path, report):
            packlist.add(internal, graph.kind_for(internal),
                         'include list ' + os.path.basename(path),
                         external=external)


def _include_file(packlist, index, external, report):
    """Add one file the user named, working out what the engine calls it."""
    internal = index.internal_path_for(external)
    if internal is None:
        report.warn('not under any content directory, so the engine could '
                    'not load it either: ' + external)
        return

    packlist.add(internal, graph.kind_for(internal), 'include',
                 external=os.path.abspath(external))


def _read_file_list(path, report):
    """Read an alternating internal/external list, the format we write."""
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as handle:
            lines = [line.strip() for line in handle if line.strip()]
    except (IOError, OSError) as error:
        report.warn('could not read include list {}: {}'.format(path, error))
        return []

    if len(lines) % 2:
        report.warn('include list has an odd number of lines, so the last '
                    'entry has no path: ' + path)
        lines = lines[:-1]

    return list(zip(lines[0::2], lines[1::2]))


def _internal_excludes(index, values):
    """Turn user-supplied paths into internal paths where we can.

    A user may name either -- ``materials/foo.vmt`` or the full path to it
    on disk -- and both should exclude the same asset.
    """
    found = []
    for value in values or ():
        internal = index.internal_path_for(value) if os.path.isabs(value) else None
        found.append(internal or paths.internal_path(value).lower())
    return found


def _exclude_vpks(packlist, exclude_vpks, report):
    """Refuse to pack anything a named VPK already ships."""
    if not exclude_vpks:
        return

    import vpk as vpk_module

    for path in exclude_vpks:
        found = gameinfo.vpk_dir_file(path) or path
        try:
            packlist.exclude(internal_paths=vpk_module.read_paths(found))
        except vpk_module.VpkError as error:
            report.warn('could not read {}: {}'.format(path, error))


def _report_missing(packlist, report):
    """Say what could not be found. This is the point of the tool."""
    missing = packlist.missing()
    if not missing:
        return

    report.tell('{} missing file(s):'.format(len(missing)))
    for asset in missing:
        report.tell('  {:50s} ({})'.format(asset['internal'], asset['origin']))


def _summarise(packlist):
    counts = packlist.counts()
    return {
        'packed': counts.get(content.PACKED, 0),
        'stock': counts.get(content.STOCK, 0),
        'missing': len(packlist.missing()),
        'embedded': counts.get(content.EMBEDDED, 0),
        'scripted': counts.get(content.SCRIPTED, 0),
        'bytes': packlist.total_bytes(),
        'by_kind': packlist.by_kind(),
        'missing_list': [{'internal': a['internal'], 'kind': a['kind'],
                          'origin': a['origin']}
                         for a in packlist.missing()],
    }


def _report_counts(summary, report, style, packlist):
    if style == 'json':
        report.tell(json.dumps(summary, indent=2, sort_keys=True))
        return

    if style == 'detailed':
        for asset in packlist.packed():
            report.tell('  {:9s} {}'.format(asset['kind'], asset['internal']))

    kinds = summary['by_kind']
    if kinds:
        breakdown = ', '.join('{} {}s'.format(count, kind)
                              for kind, count in sorted(kinds.items()))
    else:
        breakdown = 'nothing'

    report.say('packed {} files: {}.'.format(summary['packed'], breakdown))
    report.say('skipped {} stock, {} already in bsp, {} soundscript '
               'references.'.format(summary['stock'], summary['embedded'],
                                    summary['scripted']))


def _write(packed, output_path, to_stdout, report):
    """Write the list, or print it. Returns the path written, or None."""
    if to_stdout:
        text = filelist.render(packed)
        if text:
            report.tell(text.replace('\r\n', '\n').rstrip('\n'))
        return None

    try:
        filelist.write(packed, output_path)
    except (IOError, OSError) as error:
        raise PackError('could not write {}: {}'.format(output_path, error))

    return output_path
