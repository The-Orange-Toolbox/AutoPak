"""The dependency walk.

One asset is one internal path. Adding a path resolves it, records what came
of it, and -- only if it turned out to be a loose file we are packing --
queues it to be opened and asked what *it* needs.

That last condition is the whole shape of the algorithm. A stock asset is a
leaf because its own dependencies are stock too; a missing asset is a leaf
because there is nothing to read. So the walk only ever descends through
content the mapper actually made, which is both correct and the reason it
finishes quickly on a map that mostly uses the base game.

The walk is an explicit queue rather than recursion. Real ``Patch`` chains
and ``$includemodel`` chains get deep enough to be uncomfortable against the
recursion limit in a frozen exe, a flat loop gives the progress bar
something to measure, and a ceiling on the number of assets is one line
instead of a stack overflow.
"""

import collections
import os

import content
import keys
import paths

KIND_MATERIAL = 'material'
KIND_TEXTURE = 'texture'
KIND_MODEL = 'model'
KIND_PARTICLE = 'particle'
KIND_SOUND = 'sound'
KIND_SCRIPT = 'script'
KIND_RESOURCE = 'resource'
KIND_MISC = 'misc'

#: A map that wants more than this many files is either generated or has
#: found a cycle the visited set cannot see. Stop and say so rather than
#: run until someone kills the process.
MAX_ASSETS = 100000


class PackList(object):
    """Every asset the map needs, and what became of each."""

    def __init__(self, index, report, pack_swvtx=True):
        """
        :param index: the resolver.
        :type index: content.ContentIndex
        :param report: where warnings and per-asset lines go.
        :type report: report.Report
        """
        self.index = index
        self.report = report
        self.pack_swvtx = pack_swvtx

        #: :type: (dict) - internal path -> asset, in discovery order. Also
        #: the visited set: presence here means "already decided", whatever
        #: the outcome was, so a cycle through a missing file terminates
        #: just as readily as one through a packed file.
        self.assets = collections.OrderedDict()

        #: :type: (deque) - (internal path, kind, extra) still to expand.
        self.queue = collections.deque()

        #: :type: (dict) - model path -> skin indices in use. Filled before
        #: the walk starts so a model is added once with all of them.
        self.model_skins = {}

        #: :type: (list) - (particle system name, origin). Particles are
        #: named rather than pathed, so they cannot be resolved until the
        #: map's manifest says which file defines each one.
        self.particle_names = []

        #: :type: (set) - internal paths the user excluded.
        self.excluded = set()
        #: :type: (list) - internal path prefixes the user excluded.
        self.excluded_prefixes = []

        self._hit_ceiling = False

    # -- building ---------------------------------------------------------

    def exclude(self, internal_paths=(), prefixes=()):
        """Refuse to pack these, however they are reached."""
        for path in internal_paths:
            self.excluded.add(paths.internal_path(path).lower())
        for prefix in prefixes:
            cleaned = paths.internal_path(prefix).lower().rstrip('/')
            if cleaned:
                self.excluded_prefixes.append(cleaned + '/')

    def is_excluded(self, key):
        if key in self.excluded:
            return True
        return any(key.startswith(prefix) for prefix in self.excluded_prefixes)

    def add(self, internal, kind, origin, speculative=False, extra=None,
            external=None):
        """Record one reference and queue it if it is ours to pack.

        :param internal: the engine path being referenced.
        :type internal: str
        :param kind: what sort of asset it is, for the summary.
        :type kind: str
        :param origin: what referenced it, so the report can say where a
            missing file came from.
        :type origin: str
        :param speculative: True for a guess -- a skybox face, a model
            sibling, a cross-product material. A guess that resolves
            nowhere is dropped silently; a definite reference that resolves
            nowhere is reported.
        :type speculative: bool
        :param external: a known path on disk, for ``--include`` where the
            user has already named the file.
        :type external: str, optional
        :returns: True if this was the first time the path was seen.
        :rtype: bool
        """
        key = paths.internal_path(internal).lower().lstrip('/')
        if not key or key in self.assets:
            return False

        if self.is_excluded(key):
            return False

        if len(self.assets) >= MAX_ASSETS:
            if not self._hit_ceiling:
                self._hit_ceiling = True
                self.report.warn(
                    'stopped after {} files; the map references more content '
                    'than a map plausibly can'.format(MAX_ASSETS))
            return False

        if external is not None:
            status, resolved, shadowed = content.PACKED, external, False
        else:
            status, resolved, shadowed = self.index.resolve(key)

        self.assets[key] = {
            'internal': key,
            'external': resolved,
            'kind': kind,
            'status': status,
            'origin': origin,
            'speculative': speculative,
        }

        if shadowed:
            self.report.warn('loose file shadows VPK content: ' + key)

        self.report.detail('{:9s} {}'.format(status, key))

        if status == content.PACKED:
            self.queue.append((key, kind, extra))
            return True

        return True

    def index_directory(self, directory):
        """Every file under an internal directory, across all content roots.

        Backs the ``IncludeDirectory`` packing hint, where a script author
        names a folder rather than listing its contents. Merged rather than
        first-hit, because a set of content can be split across a custom
        folder and the game's.

        :rtype: list
        """
        prefix = directory.strip('/').lower()
        if not prefix:
            return []

        found = []
        seen = set()

        for root in self.index.directories:
            folder = os.path.join(root, prefix.replace('/', os.sep))
            if not os.path.isdir(folder):
                continue

            for base, _, names in os.walk(folder):
                relative = os.path.relpath(base, root).replace(os.sep, '/')
                for name in names:
                    internal = '{}/{}'.format(relative, name).lower()
                    if internal in seen:
                        continue
                    seen.add(internal)
                    found.append(internal)

        return sorted(found)

    def add_scripted(self, name, origin):
        """Record a sound named through a soundscript rather than by path.

        Keys like ``message`` and ``startsound`` usually hold a soundscript
        entry (``Ambient.Wind``), not a filename. Treating those as files
        would report almost every one of them missing and bury the handful
        that genuinely are.
        """
        key = 'soundscript:' + name.lower()
        if key in self.assets:
            return False

        self.assets[key] = {
            'internal': name,
            'external': None,
            'kind': KIND_SOUND,
            'status': content.SCRIPTED,
            'origin': origin,
            'speculative': False,
        }
        return True

    # -- walking ----------------------------------------------------------

    def run(self, expanders, pacifier=None):
        """Expand everything queued, and everything that turns up.

        :param expanders: {kind: function(packlist, internal, external,
            extra)} -- what to do with each sort of packed asset.
        :type expanders: dict
        """
        while self.queue:
            internal, kind, extra = self.queue.popleft()
            expand = expanders.get(kind)
            if expand is None:
                continue

            asset = self.assets.get(internal)
            if asset is None or asset['external'] is None:
                continue

            try:
                expand(self, internal, asset['external'], extra)
            except Exception as error:
                # One unreadable file must not end the run. The map is
                # still mostly packable, and the warning says which file
                # to go and look at.
                self.report.warn('could not read {}: {}'.format(
                    internal, error))

            if pacifier is not None and self.assets:
                pacifier.update(
                    1.0 - len(self.queue) / float(len(self.assets)))

    # -- reading off the results ------------------------------------------

    def packed(self):
        """The assets that go in the file list, in discovery order."""
        return [a for a in self.assets.values()
                if a['status'] == content.PACKED]

    def missing(self):
        """Definite references that resolved nowhere.

        Speculative ones are left out: a skybox that is LDR-only is not a
        problem, and neither is a model with no ``.ani`` beside it.
        """
        return [a for a in self.assets.values()
                if a['status'] == content.MISSING and not a['speculative']]

    def counts(self):
        """How many of each status, for the summary line."""
        found = {}
        for asset in self.assets.values():
            found[asset['status']] = found.get(asset['status'], 0) + 1
        return found

    def by_kind(self):
        """How many packed assets of each kind."""
        found = {}
        for asset in self.packed():
            found[asset['kind']] = found.get(asset['kind'], 0) + 1
        return found

    def total_bytes(self):
        """How much the packed content adds up to."""
        total = 0
        for asset in self.packed():
            try:
                total += os.path.getsize(asset['external'])
            except (IOError, OSError):
                pass
        return total


def kind_for(internal):
    """Guess an asset's kind from its extension.

    Used for files that arrive without context -- ``--include``, VScript
    hints -- where all we have is a path.

    :rtype: str
    """
    lowered = internal.lower()
    if lowered.endswith('.vmt'):
        return KIND_MATERIAL
    if lowered.endswith(('.vtf', '.dds', '.png', '.jpg', '.jpeg', '.svg')):
        return KIND_TEXTURE
    # A model's siblings are model files too, and counting them as 'misc'
    # would make the summary say a map has ninety miscellaneous files when
    # what it has is eighteen models. Only the .mdl itself is ever opened;
    # see expand_model.
    if lowered.endswith(('.mdl', '.vvd', '.vtx', '.phy', '.ani')):
        return KIND_MODEL
    if lowered.endswith('.pcf'):
        return KIND_PARTICLE
    if lowered.endswith(keys.SOUND_EXTENSIONS):
        return KIND_SOUND
    if lowered.endswith(('.nut', '.txt', '.vsc')):
        return KIND_SCRIPT
    if lowered.endswith('.res'):
        return KIND_RESOURCE
    return KIND_MISC
