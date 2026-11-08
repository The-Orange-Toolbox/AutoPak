"""A Valve-style progress pacifier.

Reproduces the progress bar printed by the Source compile tools (vvis, vrad):

    0...1...2...3...4...5...6...7...8...9...10

The bar is 40 ticks wide. Every 4th tick prints its tens digit (0..10); the
other three print a dot. This mirrors Valve's ``pacifier.cpp`` so VICI output
sits naturally alongside vvis/vrad logs.
"""

import sys


class Pacifier(object):
    def __init__(self, prefix="", width=20, stream=None, enabled=True):
        self.prefix = prefix
        self.width = width
        self.stream = stream if stream is not None else sys.stdout
        self.enabled = enabled
        self.started = False
        self._last = -1

    def start(self):
        if not self.enabled:
            return
        self.stream.write(self.prefix.ljust(self.width))
        self.started = True
        self._last = -1
        self.update(0.0)

    def update(self, fraction):
        if not self.enabled:
            return
        cur = int(fraction * 40.0)
        if cur > 40:
            cur = 40
        if cur <= self._last:
            return
        for i in range(self._last + 1, cur + 1):
            if i % 4 == 0:
                self.stream.write(str(i // 4))
            elif i != 40:
                self.stream.write(".")
        self._last = cur
        self.stream.flush()

    def end(self, suffix=""):
        if not self.enabled:
            return
        self.update(1.0)  # guarantee we finish on "10"
        self.stream.write(suffix + "\n")
        self.started = False
        self.stream.flush()

    def abort(self):
        """Close a half-drawn line (e.g. before an error/traceback)."""
        if self.enabled and self.started:
            self.stream.write("\n")
            self.started = False
            self.stream.flush()
