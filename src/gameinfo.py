"""Locating the game, and turning its gameinfo.txt into search paths.

Everything AutoPak decides about an asset comes back to this file. The
search paths gameinfo.txt names are what separate "custom content the mapper
made, which must be packed" from "the base game's, which must not be" -- so a
missing or mis-parsed search path does not produce a slightly worse pack, it
produces a wrong one.

Two differences from how CompilePal reads the same file, both required by
AutoPak reporting what it cannot find rather than silently dropping it:

* **VPK entries are kept.** CompilePal skips them because it only wants
  loose files. AutoPak needs them to answer "does the base game already
  have this?", which is the difference between a quiet skip and a false
  missing-file report.
* **``|all_source_engine_paths|`` is resolved, not skipped.** CompilePal
  ignores any path with a token it does not recognise; it can afford to,
  because an unresolved path just means "not packed". Here it would mean
  every HL2 base asset gets reported missing.
"""

import os

GAMEINFO = 'gameinfo.txt'

#: The gameinfo path token, replaced with the folder holding gameinfo.txt.
GAMEINFO_PATH = '|gameinfo_path|'
#: The shared-content token. It resolves against the folder above the mod,
#: which is the same base a bare relative path uses.
ALL_SOURCE_ENGINE_PATHS = '|all_source_engine_paths|'

#: Search path roles that never hold content a map can reference. Binaries
#: are the only ones worth skipping; the write paths are subsets of folders
#: already in the list.
SKIPPED_ROLES = ('gamebin',)


def find_game_dir(bsp_path):
    """Walk up from *bsp_path* to the game dir that holds gameinfo.txt.

    A map at ``.../Team Fortress 2/tf/maps/x.bsp`` resolves to ``.../tf``.

    :param bsp_path: the map being packed.
    :type bsp_path: str
    :returns: the absolute game directory, or None if there is no
        gameinfo.txt anywhere above the map.
    :rtype: str or None
    """
    directory = os.path.dirname(os.path.abspath(bsp_path))
    while True:
        if os.path.isfile(os.path.join(directory, GAMEINFO)):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def _resolve(value, game_dir, root_dir):
    """Expand one search path value to an absolute path.

    The tokens choose the base directory; everything else resolves against
    the folder above the mod, which is what the engine does with a bare
    relative path like ``tf/tf2_textures.vpk``.
    """
    path = value.strip().strip('"')

    base = root_dir
    if GAMEINFO_PATH in path:
        path = path.replace(GAMEINFO_PATH, '')
        base = game_dir
    elif ALL_SOURCE_ENGINE_PATHS in path:
        path = path.replace(ALL_SOURCE_ENGINE_PATHS, '')

    path = path.strip().replace('\\', '/')

    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(base, path))


def vpk_dir_file(path):
    """Find the directory half of a multi-part VPK.

    gameinfo.txt names ``tf2_textures.vpk``; what is on disk is
    ``tf2_textures_dir.vpk`` alongside numbered archives holding the actual
    bytes. Only the directory file is ever read.

    :returns: the readable path, or None if neither spelling exists.
    :rtype: str or None
    """
    if os.path.isfile(path):
        return path

    stem = path[:-4] if path.lower().endswith('.vpk') else path
    paired = stem + '_dir.vpk'
    if os.path.isfile(paired):
        return paired

    return None


def _expand_wildcard(path):
    """Everything a ``custom/*`` entry mounts.

    The engine mounts both the subfolders and any VPKs sitting directly in
    the wildcarded folder, in alphabetical order.

    :returns: (directories, vpks)
    """
    parent = os.path.dirname(path.replace('*', '').rstrip('/'))
    if not os.path.isdir(parent):
        return [], []

    directories = []
    vpks = []
    for name in sorted(os.listdir(parent)):
        entry = os.path.join(parent, name)
        if os.path.isdir(entry):
            directories.append(entry)
        elif name.lower().endswith('.vpk'):
            found = vpk_dir_file(entry)
            if found is not None:
                vpks.append(found)

    return directories, vpks


def search_paths(game_dir):
    """Read the mod's search paths out of its gameinfo.txt.

    :param game_dir: the folder holding gameinfo.txt.
    :type game_dir: str
    :returns: (directories, vpks) -- both absolute, deduplicated, in the
        order the engine would search them.
    :rtype: tuple
    :raises GameinfoError: when gameinfo.txt is missing or names no
        search paths at all.
    """
    from formats import kv1

    game_dir = os.path.abspath(game_dir)
    root_dir = os.path.dirname(game_dir)

    root = kv1.load(os.path.join(game_dir, GAMEINFO))
    if root is None:
        raise GameinfoError('cannot read ' + os.path.join(game_dir, GAMEINFO))

    block = None
    info = root.first_block('GameInfo')
    if info is not None:
        filesystem = info.first_block('FileSystem')
        if filesystem is not None:
            block = filesystem.first_block('SearchPaths')

    if block is None:
        raise GameinfoError(
            'no GameInfo/FileSystem/SearchPaths in '
            + os.path.join(game_dir, GAMEINFO))

    directories = []
    vpks = []

    for role, value in block.pairs:
        if isinstance(value, kv1.Node):
            continue
        if role.lower() in SKIPPED_ROLES:
            continue

        path = _resolve(value, game_dir, root_dir)

        if '*' in path:
            found_dirs, found_vpks = _expand_wildcard(path)
            directories.extend(found_dirs)
            vpks.extend(found_vpks)
        elif path.lower().endswith('.vpk'):
            found = vpk_dir_file(path)
            if found is not None:
                vpks.append(found)
        elif os.path.isdir(path):
            directories.append(path)

    return _unique(directories), _unique(vpks)


def _unique(paths):
    """Drop repeats, keeping first-seen order.

    gameinfo.txt names the mod folder more than once (once as ``mod``, once
    as ``game``), and searching it twice would only slow the crawl down.
    """
    seen = set()
    result = []
    for path in paths:
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


class GameinfoError(Exception):
    """gameinfo.txt is missing, unreadable, or names no search paths."""
