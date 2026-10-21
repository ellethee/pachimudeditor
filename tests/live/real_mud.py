"""Avvio di un MUD reale (Diku Modificato / DikuMod1) con il modulo `livectl`, su COPIE temporanee, per i test di conformita'.

Richiede: `DIKUMOD_SRC` (cartella `src` di DikuMod1), `DIKUMOD_LIB` (cartella `lib` dei dati), `g++`, `make`, `patch`.
Non tocca mai i sorgenti ne' i dati originali: copia tutto in una cartella temporanea sotto /tmp, applica la patch e il modulo,
compila con il Makefile reale (`-DLIVECTL`), crea un giocatore `Tester` con password nota, avvia il gioco su una porta libera e fa
entrare `Tester` con una connessione telnet che resta aperta.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[2] / "adapters" / "dikumod" / "mud-module"
TOKEN = "t" * 16 + "k" * 24
PASSWORD = "testpw"


def available() -> str | None:
    """None se si puo' costruire il MUD, altrimenti il motivo per cui no."""
    src, lib = os.environ.get("DIKUMOD_SRC"), os.environ.get("DIKUMOD_LIB")
    if not src or not lib:
        return "DIKUMOD_SRC/DIKUMOD_LIB non impostati"
    for tool in ("g++", "make", "patch"):
        if shutil.which(tool) is None:
            return f"{tool} non trovato"
    return None


def _crypt(word: str, salt: str) -> str:
    """`crypt(3)` tramite libcrypt (il modulo `crypt` di Python non esiste piu')."""
    lib = ctypes.CDLL("libcrypt.so.1")
    lib.crypt.restype = ctypes.c_char_p
    lib.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    return lib.crypt(word.encode(), salt.encode()).decode()


@dataclass
class RealMud:
    """Un MUD in esecuzione sulla copia temporanea."""

    root: Path
    port: int
    socket: str
    audit: Path
    proc: subprocess.Popen[bytes]
    telnet: asyncio.StreamWriter | None = None
    _drain: asyncio.Task[None] | None = field(default=None, repr=False)

    def stop(self) -> None:
        """Ferma il gioco e cancella la copia."""
        if self.telnet:
            self.telnet.close()
        if self._drain:
            self._drain.cancel()
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.root, ignore_errors=True)


def _build(root: Path) -> None:
    """Copia i sorgenti, applica patch e modulo, compila."""
    src = Path(os.environ["DIKUMOD_SRC"])
    shutil.copytree(src, root / "src", ignore=shutil.ignore_patterns("*.o", "leu", ".depend", "*~"))
    subprocess.run(["patch", "-p1", "-i", str(MODULE_DIR / "dikumod1-livectl.patch")], cwd=root, check=True, capture_output=True)
    for f in MODULE_DIR.glob("livectl*.[ch]"):
        shutil.copy(f, root / "src" / f.name)
    subprocess.run(["make", "depend"], cwd=root / "src", check=True, capture_output=True)
    subprocess.run(["make", "-j8", "leu", "LIVECTL_FLAGS=-DLIVECTL"], cwd=root / "src", check=True, capture_output=True, timeout=600)


def _make_tester(lib: Path) -> None:
    """Crea `players/tester.dat` partendo da un giocatore esistente, con nome e password noti."""
    donor = next(p for p in sorted((lib / "players").glob("*.dat")) if p.stat().st_size == 3036)
    data = bytearray(donor.read_bytes())
    data[0:4] = (1 << 1).to_bytes(4, "little")  # iClass: solo chierico
    data[5:25] = bytes([0, 3]) + bytes(18)  # level[]: chierico 3
    data[2924:2944] = b"Tester".ljust(20, b"\0")
    data[2974:2985] = _crypt(PASSWORD, "ab")[:10].encode().ljust(11, b"\0")
    (lib / "players" / "tester.dat").write_bytes(data)
    (lib / "rent" / "tester").unlink(missing_ok=True)


async def _login(port: int) -> tuple[asyncio.StreamWriter, asyncio.Task[None]]:
    """Entra in gioco come Tester e mantiene aperta la connessione (lettura in background)."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    async def drain() -> None:
        while await reader.read(4096):
            pass

    await asyncio.sleep(0.5)
    for line in ("Tester", PASSWORD, "", "", "1"):
        writer.write(line.encode() + b"\r\n")
        await writer.drain()
        await asyncio.sleep(0.7)
    return writer, asyncio.ensure_future(drain())


async def start() -> RealMud:
    """Costruisce e avvia il MUD; restituisce l'oggetto da fermare con `stop()`."""
    root = Path(tempfile.mkdtemp(prefix="lc-", dir="/tmp"))
    try:
        _build(root)
        shutil.copytree(os.environ["DIKUMOD_LIB"], root / "lib")
        _make_tester(root / "lib")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        sock, audit = str(root / "l.sock"), root / "lib" / "livectl.audit"
        env = {**os.environ, "LIVECTL_SOCKET": sock, "LIVECTL_TOKEN": TOKEN, "LIVECTL_CLASSES": "read,write", "LIVECTL_AUDIT": str(audit)}
        proc = subprocess.Popen([str(root / "src" / "leu"), "-d", str(root / "lib"), str(port)], cwd=root / "src", env=env,
                                stdout=(root / "mud.log").open("wb"), stderr=subprocess.STDOUT)  # fmt: skip
        mud = RealMud(root, port, sock, audit, proc)
        deadline = time.monotonic() + 90
        while not Path(sock).exists():
            if proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("il MUD non si e' avviato: vedi " + str(root / "mud.log"))
            await asyncio.sleep(0.3)
        mud.telnet, mud._drain = await _login(port)
        return mud
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
