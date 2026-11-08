"""Minimal parsers for the file formats AutoPak has to read itself.

Every module in here is pure: it takes a path or bytes and returns engine
relative internal paths. None of them resolves a search path, touches the
report, or knows what a VPK is. That is what lets the whole CompilePal rule
port be tested with temporary files and no game installed.
"""
