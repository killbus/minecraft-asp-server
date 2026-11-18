"""Scratch trees for tests, under the repository's gitignored ``.tmp/``."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".tmp"


def remove(path):
    """Remove *path*, tolerating Windows' delayed release of an emptied tree.

    A just-deleted entry can still be visible to ``rmdir`` for a few
    milliseconds under an indexer or a virus scanner. Retry instead of
    failing a test that already passed its assertions.
    """
    for attempt in range(6):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == 5:
                print(f"warning: left scratch tree at {path}", file=sys.stderr)
                return
            time.sleep(0.05 * 2**attempt)


@contextmanager
def directory(prefix="test-"):
    """Yield a unique directory under ``.tmp/`` and remove it afterwards."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=SCRATCH))
    try:
        yield path
    finally:
        remove(path)
