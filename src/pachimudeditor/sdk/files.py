"""Scrittura atomica di file per gli adapter (SDK 1.2)."""

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    """Scrive `data` su `path` in modo atomico (temporaneo nella stessa cartella + `fsync` + `os.replace`).

    Se `path` e' un symlink scrive sul target reale (il symlink resta tale). Preserva i permessi e, quando
    il processo ha i privilegi, proprietario e gruppo del file esistente; fa `fsync` del file e della cartella.
    Il temporaneo e' rimosso in caso di errore.
    """
    target = Path(os.path.realpath(path))
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            try:
                st = target.stat()
            except FileNotFoundError:
                os.fchmod(fh.fileno(), 0o644)
            else:
                os.fchmod(fh.fileno(), st.st_mode & 0o7777)
                with contextlib.suppress(OSError):  # senza privilegi non si puo' cambiare proprietario
                    os.fchown(fh.fileno(), st.st_uid, st.st_gid)
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        dfd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
