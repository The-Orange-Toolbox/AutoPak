r"""Entity outputs, and the assets hidden inside them.

An entity output in a *compiled* map does not look like it does in Hammer.
The commas become escape characters, so what the VMF wrote as::

    "OnTrigger" "relay,SetModel,models/x.mdl,0,-1"

is stored as::

    "OnTrigger" "relay\x1bSetModel\x1bmodels/x.mdl\x1b0\x1b-1"

Five fields, always. Anything else is not an output and is left alone.

This matters because an output is one of the few places a map names content
that appears nowhere else: a model swapped in at runtime, an overlay
material shown on a countdown, a sound played by name. None of it is
reachable by reading keyvalues.

Two inputs need unpacking further. ``AddOutput`` carries an entire output as
its parameter, and ``RunScriptCode`` carries VScript source. Both are parsed
here rather than in :mod:`entities`, so that module stays a table of rules.
"""

#: What the compiler replaces the commas in an output with.
SEPARATOR = '\x1b'

#: target, input, parameter, delay, times to fire.
FIELDS = 5


def parse_output(value):
    """Split one compiled output into its five fields.

    :param value: the raw keyvalue.
    :type value: str
    :returns: (target, input, parameter, delay, times), or None when the
        value is not an output at all.
    :rtype: tuple or None
    """
    if SEPARATOR not in value:
        return None

    parts = value.split(SEPARATOR)
    if len(parts) != FIELDS:
        return None

    return tuple(part.strip() for part in parts)


def resolve_addoutput(target_input, parameter):
    """Unwrap an ``AddOutput`` that carries another output.

    ``AddOutput`` has two forms. The simple one sets a keyvalue --
    ``"targetname newname"`` -- and is left alone. The complex one adds a
    whole output, colon-separated::

        OnUser1 relay:SetModel:models/x.mdl:0:-1

    and the model in there has to be packed like any other.

    :returns: the (input, parameter) to go on with.
    :rtype: tuple
    """
    if target_input.lower() != 'addoutput' or ':' not in parameter:
        return target_input, parameter

    # The output name is separated from the rest by whitespace; everything
    # after it is the colon-separated output.
    _, _, rest = parameter.partition(' ')
    parts = rest.split(':')
    if len(parts) < 3:
        return target_input, parameter

    return parts[1].strip(), parts[2].strip()


def console_command(parameter):
    """Split a ``Command`` parameter into its verb and argument.

    ``point_servercommand`` and friends carry console commands, a few of
    which name content: ``r_screenoverlay``, ``play``, ``playgamesound``.

    :returns: (verb lowercased, argument) or (None, None).
    :rtype: tuple
    """
    text = parameter.strip().strip('"')
    if not text:
        return None, None

    verb, _, argument = text.partition(' ')
    argument = argument.strip().strip('"')
    if not argument:
        return None, None

    return verb.lower(), argument


def script_calls(code):
    """The function calls in a VScript snippet.

    Deliberately crude: this is a scanner, not a Squirrel parser. It wants
    the name of each call and its arguments, and anything it cannot make
    sense of it skips.

    :param code: the body of a ``RunScriptCode`` parameter.
    :type code: str
    :returns: (function name, argument) pairs. A call with several
        arguments yields one pair per argument, because every function
        worth reading here takes its filename first.
    :rtype: list
    """
    # An odd number of backticks means the string was cut in half somewhere
    # and anything parsed out of it would be nonsense.
    if code.count('`') % 2:
        return []

    found = []
    for statement in _split_statements(code):
        name, _, arguments = statement.partition('(')
        name = name.strip()
        if not name or not arguments:
            continue

        arguments = arguments.rstrip().rstrip(')')

        # A table argument is one thing, not a list, and commas inside it
        # separate its fields rather than the call's arguments.
        if '{' in arguments:
            found.append((name, arguments.strip()))
            continue

        for argument in arguments.split(','):
            argument = _unquote(argument)
            if argument:
                found.append((name, argument))

    return found


def script_table(text):
    """Read a Squirrel table literal into a dict.

    ``EmitSoundEx`` takes one, and the sound is under ``sound_name``.

    :rtype: dict
    """
    inner = text[text.find('{') + 1:]
    inner = inner[:inner.rfind('}')] if '}' in inner else inner

    found = {}
    for field in inner.split(','):
        key, sign, value = field.partition('=')
        if not sign:
            continue
        found[_unquote(key).lower()] = _unquote(value)
    return found


def _split_statements(code):
    """Split on semicolons that are not inside a table or a string."""
    statements = []
    current = []
    depth = 0
    quote = None

    for char in code:
        if quote:
            if char == quote:
                quote = None
            current.append(char)
            continue

        if char in '"\'`':
            quote = char
            current.append(char)
            continue

        if char in '{[':
            depth += 1
        elif char in '}]':
            depth = max(0, depth - 1)

        if char == ';' and depth == 0:
            statements.append(''.join(current))
            current = []
            continue

        current.append(char)

    statements.append(''.join(current))
    return [s.strip() for s in statements if s.strip()]


def _unquote(text):
    """Strip whitespace and whichever quote style the author used."""
    return text.strip().strip('`').strip('"').strip("'").strip()
