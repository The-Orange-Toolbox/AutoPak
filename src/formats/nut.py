r""".. NUT - VScript

A script can precache content the map never mentions anywhere else:

.. code-block:: none

    IncludeScript("shared/util.nut")
    self.PrecacheModel("models/custom/thing.mdl")
    self.PrecacheSound("custom/beep.wav")

and, for anything a scanner cannot work out, it can say so outright:

.. code-block:: none

    // !CompilePal::IncludeFile("materials/custom/thing.vmt")
    // !CompilePal::IncludeDirectory("materials/custom/set")

That hint spelling is CompilePal's, and it is the portable one -- scripts
in the wild already carry it, and a script written with it works in both
tools. ``!AutoPak::`` is accepted as an alias for people who would rather
name the tool they are using.

This is a line scanner, not a Squirrel parser. It wants the argument of
each interesting call and skips whatever it cannot read, which is the right
trade for a language whose full grammar has no bearing on what a map needs.
"""

import re

import paths

#: Calls whose first argument names a script.
SCRIPT_CALLS = ('includescript', 'doincludescript')
#: Calls whose first argument names a model.
MODEL_CALLS = ('precachemodel',)
#: Calls whose first argument names a sound.
SOUND_CALLS = ('precachesound',)

#: The packing hints, matched on the part after '::' so both prefixes share
#: one path.
HINT_PREFIXES = ('!compilepal::', '!autopak::')
HINT_FILE = 'includefile'
HINT_DIRECTORY = 'includedirectory'

_CALL = re.compile(r'([A-Za-z_][A-Za-z_0-9.]*)\s*\(([^)]*)\)')
_ARGUMENT = re.compile(r'''["'`]([^"'`]*)["'`]''')


class References(object):
    """What one script asks for."""

    def __init__(self):
        self.scripts = []
        self.models = []
        self.sounds = []
        self.files = []
        self.directories = []


def references(text):
    """Read a VScript.

    :param text: the contents of a ``.nut``.
    :type text: str
    :rtype: References
    """
    found = References()

    for line in text.splitlines():
        stripped = line.strip()

        comment = stripped.find('//')
        if comment >= 0:
            _read_hint(found, stripped[comment + 2:].strip())
            stripped = stripped[:comment]

        if not stripped:
            continue

        for name, arguments in _CALL.findall(stripped):
            call = name.rpartition('.')[2].lower()
            argument = _first_argument(arguments)
            if not argument:
                continue

            if call in SCRIPT_CALLS:
                found.scripts.append(
                    'scripts/vscripts/' + _script_name(argument))
            elif call in MODEL_CALLS:
                found.models.append(paths.internal_path(argument).lower())
            elif call in SOUND_CALLS:
                found.sounds.append(paths.sound_path(argument))

    return found


def _read_hint(found, comment):
    """Read a ``!CompilePal::IncludeFile`` style directive."""
    lowered = comment.lower()
    for prefix in HINT_PREFIXES:
        if not lowered.startswith(prefix):
            continue

        rest = comment[len(prefix):]
        name, _, arguments = rest.partition('(')
        argument = _first_argument(arguments.rstrip().rstrip(')'))
        if not argument:
            return

        directive = name.strip().lower()
        if directive == HINT_FILE:
            found.files.append(paths.internal_path(argument).lower())
        elif directive == HINT_DIRECTORY:
            found.directories.append(
                paths.internal_path(argument).lower().rstrip('/'))
        return


def _first_argument(text):
    """The first quoted argument of a call."""
    match = _ARGUMENT.search(text)
    if match is not None:
        return match.group(1).strip()

    # An unquoted argument is unusual but readable.
    first = text.split(',')[0].strip()
    if first and not first.startswith(('{', '[')):
        return first
    return ''


def _script_name(argument):
    """Scripts are named without their extension as often as with it."""
    name = paths.internal_path(argument).lower().strip()
    if not name.endswith('.nut'):
        name += '.nut'
    return name


def dependencies(path):
    """Read a VScript off disk.

    :rtype: References
    """
    try:
        with open(path, 'r', encoding='latin-1', errors='replace') as handle:
            return references(handle.read())
    except (IOError, OSError):
        return References()
