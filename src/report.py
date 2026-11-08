"""What AutoPak tells the user while it works.

The list of files AutoPak could *not* find is the whole product. A packer
that quietly drops a broken reference produces a map that looks fine on the
machine that built it and is full of purple checkerboards everywhere else,
which is exactly the failure this tool exists to prevent. So anything
AutoPak decides on the mapper's behalf has to be visible here.

Warnings are collected rather than printed where they happen. A material
referenced by two hundred faces would otherwise print two hundred identical
lines in the middle of the crawl; grouped at the end, they read as one
finding with a count. Under ``-v`` they are printed as they occur as well,
because when you are debugging a specific map you want them in order next
to the asset that produced them.
"""

from totcommon.logger import stdout


class Report(object):
    """Phase lines, per-run statistics, and collected warnings."""

    def __init__(self, verbose=False, quiet=False):
        self.verbose = verbose
        self.quiet = quiet

        #: {message: count}, in first-seen order
        self.warnings = {}
        #: free-form counters the phases bump as they go
        self.stats = {}

    def say(self, message):
        """A phase line. Suppressed by ``-q``."""
        if not self.quiet:
            stdout(message)

    def tell(self, message):
        """Something the user asked for and must see even under ``-q``.

        The missing-file report goes through here: it is the main reason to
        run AutoPak, so silencing it would defeat the point of the run.
        """
        stdout(message)

    def detail(self, message, indent=1):
        """A per-asset line. Only under ``-v``."""
        if self.verbose and not self.quiet:
            stdout('  ' * indent + message)

    def warn(self, message):
        """Something the mapper needs to know about their map.

        Repeats are counted, not repeated.
        """
        self.warnings[message] = self.warnings.get(message, 0) + 1
        if self.verbose and not self.quiet:
            stdout('  warning: ' + message)

    def bump(self, name, amount=1):
        self.stats[name] = self.stats.get(name, 0) + amount

    def get(self, name):
        return self.stats.get(name, 0)

    @property
    def warning_count(self):
        return sum(self.warnings.values())

    def summary(self):
        """Print the collected warnings. Nothing if the run was clean."""
        if not self.warnings:
            return

        self.say('{} warning(s):'.format(self.warning_count))
        for message, count in self.warnings.items():
            suffix = ' (x{})'.format(count) if count > 1 else ''
            self.say('  ' + message + suffix)
