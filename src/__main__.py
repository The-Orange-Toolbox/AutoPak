import argparse
import os
import sys

# Flush stdout/stderr on every line so the crawl's progress shows up
# immediately instead of sitting in a block buffer when the stream is piped
# into a compile chain rather than attached to a terminal.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

from _constants import ORGNAME, NAME, URL, VERSION, BUILD_DATE  # NOQA: E402

from totcommon.executable import TOTExecutable  # NOQA: E402
from totcommon.logger import stdout  # NOQA: E402

from gameinfo import find_game_dir  # NOQA: E402
from pack import PackError, pack  # NOQA: E402


def build_parser():
    p = argparse.ArgumentParser(
        description='Find every custom asset a compiled BSP depends on and '
                    'write the file list that bspzip -addlist consumes.',
        epilog='AutoPak never modifies the map and never runs bspzip. An '
               'asset that exists only inside a VPK belongs to the base game '
               'and is not packed; an asset found nowhere is reported.',
    )

    p.add_argument('bsp', metavar='map.bsp',
                   help='The compiled map to scan. Never modified.')

    content = p.add_argument_group('content')
    content.add_argument('-g', '--game', metavar='DIR', dest='game_dir',
                         help='The mod folder holding gameinfo.txt. Its '
                              'search paths decide what counts as custom '
                              'content. Default: walk up from the BSP.')
    content.add_argument('--source-directory', metavar='DIR',
                         action='append', dest='source_dirs',
                         help='An extra loose content root to search, on top '
                              'of the ones gameinfo.txt names. Repeatable.')
    content.add_argument('--profile', metavar='NAME',
                         help='The valvebsp profile to read the map with '
                              '(TF2, P2, L4D2...). Default: autodetect.')
    content.add_argument('--no-vpk', action='store_true',
                         help='Do not read the VPKs. Anything not found as a '
                              'loose file is then reported missing rather '
                              'than recognised as base-game content.')

    selection = p.add_argument_group('selection')
    selection.add_argument('-i', '--include', metavar='PATH',
                           action='append', dest='includes',
                           help='Force-pack this file even if nothing in the '
                                'map references it. Repeatable.')
    selection.add_argument('--include-dir', metavar='DIR',
                           action='append', dest='include_dirs',
                           help='Force-pack everything under this directory, '
                                'recursively. Repeatable.')
    selection.add_argument('--include-file-list', metavar='FILE',
                           action='append', dest='include_file_lists',
                           help='Force-pack the entries in this list. Same '
                                'alternating internal/external format that '
                                'AutoPak writes, so its own output can be '
                                'fed back in. Repeatable.')
    selection.add_argument('--exclude', metavar='PATH',
                           action='append', dest='excludes',
                           help='Never pack this file. Repeatable.')
    selection.add_argument('--exclude-dir', metavar='DIR',
                           action='append', dest='exclude_dirs',
                           help='Never pack anything under this directory. '
                                'Repeatable.')
    selection.add_argument('--exclude-vpk', metavar='VPK',
                           action='append', dest='exclude_vpks',
                           help='Never pack anything this VPK already '
                                'contains. Repeatable.')
    selection.add_argument('--no-swvtx', action='store_true',
                           help='Skip the .sw.vtx software-rendering meshes '
                                'that ship beside most models.')

    utility = p.add_argument_group('utility files')
    utility.add_argument('--rename-nav', action='store_true',
                         help='List the navigation mesh as maps/embed.nav so '
                              'it loads whatever the map is called.')
    utility.add_argument('--rename-particle-manifest', action='store_true',
                         help='List the particle manifest as particles.txt.')
    utility.add_argument('--no-utility-files', action='store_true',
                         help='Skip the pass that looks for the sidecar files '
                              'a map conventionally has: nav, soundscapes, '
                              'overviews, level sounds, language files.')

    out = p.add_argument_group('output')
    out.add_argument('-o', '--output', metavar='FILE', dest='output_path',
                     help='Where to write the file list. Default: '
                          '<map>_files.txt beside the BSP.')
    out.add_argument('--stdout', action='store_true', dest='to_stdout',
                     help='Write the list to stdout instead of a file.')
    out.add_argument('--report', choices=('summary', 'detailed', 'json'),
                     default='summary',
                     help='How much to print: counts only (default), a full '
                          'per-asset listing, or one JSON object.')
    out.add_argument('--strict', action='store_true',
                     help='Exit with an error if any referenced asset could '
                          'not be found.')

    p.add_argument('--verbose', action='store_true',
                   help='Print every asset as it resolves.')
    p.add_argument('-q', '--quiet', action='store_true',
                   help='Print only the missing-file report and errors.')
    p.add_argument('--version', action='version', version=VERSION)
    return p


def _existing_paths(parser, paths, what):
    """Fail on the first path that is not there.

    Checked up front rather than when the crawl reaches it: "file not found"
    twenty seconds into a scan, for a path the user typed on the command
    line, is a bad way to learn about a typo.
    """
    for path in paths or ():
        if not os.path.exists(path):
            parser.error('{} not found: {}'.format(what,
                                                   os.path.abspath(path)))


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose and args.quiet:
        parser.error('--verbose and --quiet ask for opposite things')

    if not os.path.isfile(args.bsp):
        parser.error('input not found: ' + os.path.abspath(args.bsp))
    if os.path.splitext(args.bsp)[1].lower() != '.bsp':
        parser.error('input is not a .bsp: ' + os.path.abspath(args.bsp))

    game_dir = args.game_dir
    if game_dir is None:
        game_dir = find_game_dir(args.bsp)
        if game_dir is None:
            parser.error(
                'no gameinfo.txt in any folder above '
                + os.path.abspath(args.bsp)
                + '; pass --game to say which mod this map belongs to')
    elif not os.path.isfile(os.path.join(game_dir, 'gameinfo.txt')):
        parser.error('no gameinfo.txt in ' + os.path.abspath(game_dir))

    _existing_paths(parser, args.source_dirs, 'content directory')
    _existing_paths(parser, args.includes, 'included file')
    _existing_paths(parser, args.include_dirs, 'included directory')
    _existing_paths(parser, args.include_file_lists, 'include list')
    _existing_paths(parser, args.exclude_vpks, 'excluded vpk')

    output_path = args.output_path
    if output_path is None:
        mapname = os.path.splitext(os.path.basename(args.bsp))[0]
        output_path = os.path.join(os.path.dirname(os.path.abspath(args.bsp)),
                                   mapname + '_files.txt')

    # A PackError is the user's problem to fix, not a crash to report, so
    # it is caught here and turned into a message. Letting it escape the
    # context manager would hand it to TOTExecutable's error reporter,
    # which would print a stack trace and ask them to file a bug about
    # their own compressed map.
    summary = None
    failure = None

    with TOTExecutable(NAME, ORGNAME, URL, VERSION, BUILD_DATE):
        try:
            summary = pack(
                bsp_path=args.bsp,
                game_dir=game_dir,
                source_dirs=args.source_dirs or [],
                profile=args.profile,
                use_vpk=not args.no_vpk,
                includes=args.includes or [],
                include_dirs=args.include_dirs or [],
                include_file_lists=args.include_file_lists or [],
                excludes=args.excludes or [],
                exclude_dirs=args.exclude_dirs or [],
                exclude_vpks=args.exclude_vpks or [],
                pack_swvtx=not args.no_swvtx,
                rename_nav=args.rename_nav,
                rename_particle_manifest=args.rename_particle_manifest,
                utility_files=not args.no_utility_files,
                output_path=output_path,
                to_stdout=args.to_stdout,
                report_style=args.report,
                verbose=args.verbose,
                quiet=args.quiet,
            )
        except PackError as error:
            failure = str(error)
            stdout(NAME + ': ' + failure)

    if failure is not None:
        raise SystemExit(1)

    if args.strict and summary['missing']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
