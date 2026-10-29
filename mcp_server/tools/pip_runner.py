"""Run pip, working around the DSH-sandbox denial on tempfile.mkdtemp dirs.

On Windows, os.mkdir(path, 0o700) (what tempfile.mkdtemp uses) stamps a
creator-only ACL on the new directory. Under the sandbox's restricted token
that ACL rejects our own writes, so pip dies with
PermissionError: [Errno 13] writing 'pip-unpack-*/***.whl'.

We replace mkdtemp with a plain makedirs that inherits the parent ACL.

Usage:  python pip_runner.py install --target ... mcp
"""
import os
import sys
import tempfile

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp")
os.makedirs(BASE, exist_ok=True)
_seq = [0]


def _mkdtemp(suffix=None, prefix=None, dir=None):
    _seq[0] += 1
    parent = dir or BASE
    os.makedirs(parent, exist_ok=True)
    path = os.path.join(parent, "%s%05d%s" % (prefix or "tmp", _seq[0], suffix or ""))
    os.makedirs(path, exist_ok=True)
    return path


tempfile.mkdtemp = _mkdtemp

from pip._internal.cli.main import main  # noqa: E402

sys.exit(main(sys.argv[1:]))
