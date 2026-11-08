"""Writing the list bspzip reads.

The format is two lines per file -- what it is called inside the map, then
where it is on disk -- with no header and nothing else:

.. code-block:: none

    materials/foo/bar.vmt
    C:\\content\\materials\\foo\\bar.vmt
    models/props/x.mdl
    C:\\content\\models\\props\\x.mdl

Entries come out in discovery order, which makes two runs of the same map
byte-identical and a diff between two lists something you can actually read.

This is the end of AutoPak's job. Running ``bspzip -addlist`` with the
result is left to the caller, who is then also free to append their own
entries to it first.
"""

import os

#: bspzip's internal buffer for a path. Longer than this and it may write
#: the entry wrong, or not at all.
MAX_PATH_LENGTH = 256


def render(assets):
    """Turn packed assets into the text of a bspzip list.

    :param assets: dicts with 'internal' and 'external' keys.
    :type assets: iterable
    :rtype: str
    """
    lines = []
    for asset in assets:
        lines.append(asset['internal'].replace('\\', '/'))
        lines.append(os.path.normpath(asset['external']))
    if not lines:
        return ''
    return '\r\n'.join(lines) + '\r\n'


def check(assets, report):
    """Warn about entries bspzip is likely to mishandle.

    Neither of these stops the pack: the list is still written, and for a
    long path bspzip usually copes. But a map that loads for the author and
    not for anyone else is exactly what this tool exists to prevent, so a
    path the engine cannot load is worth saying out loud.
    """
    for asset in assets:
        external = asset['external'] or ''
        if len(external) > MAX_PATH_LENGTH:
            report.warn(
                'path is longer than bspzip handles reliably ({} chars): {}'
                .format(len(external), asset['internal']))

        try:
            asset['internal'].encode('ascii')
        except UnicodeEncodeError:
            report.warn('path is not plain ASCII and the engine will not '
                        'load it: ' + asset['internal'])


def write(assets, path):
    """Write the list to *path*.

    :returns: how many files it names.
    :rtype: int
    :raises IOError: if the file cannot be written -- which is worth
        failing on, since the list is the entire output of the run.
    """
    text = render(assets)

    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)

    # newline='' so the \r\n written above survives on every platform
    # rather than being translated a second time.
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)

    return len(assets)
