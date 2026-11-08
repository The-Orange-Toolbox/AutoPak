r""".. KeyValues1 - the text format most of Source is written in

``.vmt``, ``.res``, ``gameinfo.txt``, overview ``.txt``, detail ``.vbsp`` and
the keyvalues blob inside a ``.mdl`` are all the same grammar with different
vocabularies. One reader serves all of them, because six readers would mean
six different sets of bugs about where a ``//`` stops being a comment.

Two things about this reader are deliberate and easy to get wrong:

**Backslashes are not escapes.** Valve's parser only processes escape
sequences when the caller asks for it, and nothing that matters here does.
``$basetexture "metal\wall"`` means the file ``metal/wall`` -- reading
``\w`` as an escape would corrupt most of the material references in the
game.

**Duplicate keys are kept.** A node is a list of pairs, not a mapping. A
material may set ``$detail`` twice, a soundscript lists many ``wave`` lines
in one block, and a dict would silently keep only the last of each.

The reader never raises. Content in the wild is malformed often enough --
an unclosed brace at the end of a third-party VMT is routine -- and a packer
that dies on one bad file is worse than one that packs the other 99% of the
map and says so. A parse that ran out of input sets :attr:`Node.truncated`,
which the caller turns into a single warning.
"""

_WHITESPACE = ' \t\r\n'
_PUNCTUATION = '{}'


class Node(object):
    """One KeyValues block: an ordered list of key/value pairs."""

    def __init__(self):
        #: :type: (list) - (key, value) pairs in file order, keys not
        #: unique. A value is either a str or a nested Node.
        self.pairs = []
        #: :type: (list) - the files named by #base and #include
        #: directives. Resolving them needs search paths, so that is left
        #: to the caller.
        self.bases = []
        #: :type: (bool) - the text ended in the middle of a block.
        self.truncated = False

    def __iter__(self):
        return iter(self.pairs)

    def __len__(self):
        return len(self.pairs)

    def __repr__(self):
        return '<Node {} pairs>'.format(len(self.pairs))

    def find_all(self, names):
        """Every leaf value stored under one of *names*, at any depth.

        Depth matters: a material's texture keys can sit inside ``Proxies``
        or a ``>=DX90`` block, and those are ordinary nested blocks.

        :param names: the keys to look for, matched case-insensitively.
        :type names: iterable of str
        :returns: (key, value) pairs in file order, values only ever str.
        :rtype: list
        """
        wanted = set(name.lower() for name in names)
        found = []

        def walk(node):
            for key, value in node.pairs:
                if isinstance(value, Node):
                    walk(value)
                elif key.lower() in wanted:
                    found.append((key, value))

        walk(self)
        return found

    def find_first(self, name):
        """The first leaf value stored under *name*, at any depth.

        :rtype: str or None
        """
        for _, value in self.find_all([name]):
            return value
        return None

    def blocks(self, name):
        """Every nested block stored under *name*, at this level only.

        :rtype: list of Node
        """
        lowered = name.lower()
        return [value for key, value in self.pairs
                if isinstance(value, Node) and key.lower() == lowered]

    def first_block(self, name):
        """The first nested block under *name*, at this level only.

        :rtype: Node or None
        """
        for block in self.blocks(name):
            return block
        return None


def _tokenise(text):
    """Yield the tokens of *text*.

    Each token is ``(kind, value)`` where kind is 'punct' for a brace and
    'str' for anything else. Comments and ``[$condition]`` suffixes are
    dropped here so the parser never has to think about them.
    """
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if char in _WHITESPACE:
            index += 1
            continue

        # Comments. '//' is the documented one; some files use a bare '#'
        # at the start of a line for directives, which is handled as an
        # ordinary key below.
        if char == '/' and index + 1 < length and text[index + 1] == '/':
            newline = text.find('\n', index)
            index = length if newline < 0 else newline + 1
            continue

        # Conditional suffixes: [$WIN32], [!$X360]. The engine picks one
        # branch at load time; a packer wants the content of all of them,
        # so the marker is simply dropped.
        if char == '[':
            close = text.find(']', index)
            index = length if close < 0 else close + 1
            continue

        if char in _PUNCTUATION:
            yield ('punct', char)
            index += 1
            continue

        if char == '"':
            close = text.find('"', index + 1)
            newline = text.find('\n', index + 1)

            # A quoted token ends at the closing quote or at the end of the
            # line, whichever comes first. Valve's own parser would run on
            # to the next quote anywhere in the file, but every format this
            # reader handles puts one key and value per line, and no real
            # value contains a newline. Stopping at the line end means a
            # single missing quote costs one broken line instead of
            # swallowing the rest of the file and shifting every key after
            # it onto the wrong value.
            if close < 0 or (0 <= newline < close):
                close = length if newline < 0 else newline
                yield ('str', text[index + 1:close])
                index = close
                continue

            yield ('str', text[index + 1:close])
            index = close + 1
            continue

        # A bare token runs to the next thing that can end it.
        start = index
        while index < length:
            char = text[index]
            if char in _WHITESPACE or char in _PUNCTUATION or char == '"':
                break
            if char == '/' and index + 1 < length and text[index + 1] == '/':
                break
            index += 1
        yield ('str', text[start:index])


def parse(text):
    """Read KeyValues *text*.

    :param text: the file's contents.
    :type text: str
    :returns: the root node. Never None, never raises; check
        :attr:`Node.truncated` to know whether the text ran out early.
    :rtype: Node
    """
    root = Node()
    tokens = list(_tokenise(text))

    index = 0
    length = len(tokens)
    stack = [root]

    while index < length:
        kind, value = tokens[index]

        if kind == 'punct':
            if value == '}':
                # A stray close brace at the top level is malformed but
                # harmless; ignore it rather than unwinding past the root.
                if len(stack) > 1:
                    stack.pop()
                index += 1
                continue
            # A block with no key before it. Attach it under the empty key
            # so its contents are still reachable by find_all.
            block = Node()
            stack[-1].pairs.append(('', block))
            stack.append(block)
            index += 1
            continue

        key = value
        index += 1

        if index >= length:
            # A key with nothing after it. Keep it as an empty value: a
            # soundscript ending mid-line still has usable lines above.
            stack[-1].pairs.append((key, ''))
            root.truncated = True
            break

        next_kind, next_value = tokens[index]

        if next_kind == 'punct' and next_value == '{':
            block = Node()
            stack[-1].pairs.append((key, block))
            stack.append(block)
            index += 1
            continue

        if next_kind == 'punct' and next_value == '}':
            # Key with no value, block ends. Same treatment as above.
            stack[-1].pairs.append((key, ''))
            continue

        stack[-1].pairs.append((key, next_value))
        if key.lower() in ('#base', '#include'):
            root.bases.append(next_value)
        index += 1

    if len(stack) > 1:
        root.truncated = True

    return root


def load(path, encoding='latin-1'):
    """Read and parse the KeyValues file at *path*.

    ``latin-1`` rather than utf-8 because it cannot fail: Source content is
    a mix of encodings and a packer must not refuse a file over a stray
    byte in a comment.

    :returns: the root node, or None if the file could not be read.
    :rtype: Node or None
    """
    try:
        with open(path, 'r', encoding=encoding, errors='replace') as handle:
            return parse(handle.read())
    except (IOError, OSError):
        return None
