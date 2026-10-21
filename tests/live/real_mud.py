"""Avvio di un MUD reale (Diku Modificato, cartella ufficiale `leu`) con il modulo `livectl`, su COPIE temporanee, per i test di conformita'.

Richiede: `DIKUMOD_SRC` (radice del progetto: `Makefile`, `src/`; default `/dati/luca/muds/leu`), `DIKUMOD_LIB` (cartella `lib` dei dati;
default `<radice>/lib`), `g++`, `make`; `git` solo se il modulo non e' gia' installato nella radice.
Non tocca mai i sorgenti ne' i dati originali: copia la radice in una cartella temporanea sotto /tmp (senza `bin/`, `.o`, `lib/`), se `src/livectl.c`
manca applica `leu-livectl.patch` e copia i file del modulo, compila con il Makefile reale (`-DLIVECTL`), crea un giocatore `Tester` con password nota, avvia il gioco su una porta libera e fa
entrare `Tester` con una connessione telnet che resta aperta.
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from tests.support import real_data

MODULE_DIR = Path(__file__).resolve().parents[2] / "adapters" / "dikumod" / "mud-module"
SRC = real_data.DIKUMOD_SRC
"""Radice del progetto Diku Modificato (sola lettura): `DIKUMOD_SRC`, default `/dati/luca/muds/leu`."""
LIB = Path(os.environ.get("DIKUMOD_LIB") or SRC / "lib")
"""Cartella `lib/` con i dati (sola lettura): `DIKUMOD_LIB`, default `<DIKUMOD_SRC>/lib`."""
TOKEN = "t" * 16 + "k" * 24
PASSWORD = "testpw"


def available() -> str | None:
    """None se si puo' costruire il MUD, altrimenti il motivo per cui no."""
    if not (SRC / "Makefile").is_file() or not (SRC / "src").is_dir():
        return f"sorgenti di Diku Modificato non trovati in {SRC} (DIKUMOD_SRC)"
    if not LIB.is_dir():
        return f"dati di Diku Modificato non trovati in {LIB} (DIKUMOD_LIB)"
    for tool in ("g++", "make"):
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
    """Copia la radice (senza `bin/`, `.o`, `lib/`), installa il modulo se manca e compila in `root/bin/leu`."""
    ignore = shutil.ignore_patterns("*.o", "bin", "lib", ".git", ".depend", "*~", "gmon.out")
    shutil.copytree(SRC, root, ignore=ignore, dirs_exist_ok=True)
    if "livectl_init" not in (root / "src" / "comm.c").read_text(errors="replace"):  # agganci assenti: patch ai file del gioco
        subprocess.run(["git", "apply", str(MODULE_DIR / "leu-livectl.patch")], cwd=root, check=True, capture_output=True)
    for f in MODULE_DIR.glob(
        "livectl*.[ch]"
    ):  # il sorgente di riferimento del modulo e' sempre quello di mud-module/, non la copia nel gioco
        shutil.copy(f, root / "src" / f.name)
    subprocess.run(["make", "-j8", "LIVECTL_FLAGS=-DLIVECTL"], cwd=root, check=True, capture_output=True, timeout=600)


def _rent_elem(vnum: int, name: str, short: str, desc: str, values: tuple[int, ...], weight: int, wearpos: int, depth: int) -> bytes:
    """Un `obj_file_elem` da 592 byte (vedi docs/formats/dikumod.md)."""
    b = bytearray(592)
    struct.pack_into("<h2x4iiiii", b, 0, vnum, *values, 0, weight, -7000000, 0)
    b[36 : 36 + len(name)] = name.encode("latin-1")
    b[164 : 164 + len(short)] = short.encode("latin-1")
    b[292 : 292 + len(desc)] = desc.encode("latin-1")
    b[548], b[549] = wearpos, depth
    return bytes(b)


def _make_rent(lib: Path) -> None:
    """Rent di Tester: giubbotto indossato (slot 5), borsa con una bottiglia, una bottiglia sciolta."""
    bottle = ("birra bottiglia", "una bottiglia", "Una bottiglia di Moretti e' qui.")
    elems = [
        _rent_elem(9, "giubbotto pelle", "Un giubbotto di pelle", "C'e' un giubbotto di pelle per terra", (2, 2, 0, 0), 6, 6, 0),
        _rent_elem(14, "borsa piccola", "una piccola borsa", "C'e' una piccola borsa qui", (20, 0, 0, 0), 2, 0, 0),
        _rent_elem(3001, *bottle, (8, 8, 1, 0), 1, 0, 1),
        _rent_elem(3001, *bottle, (8, 8, 1, 0), 1, 0, 0),
    ]
    head = b"Tester".ljust(20, b"\0") + struct.pack("<5i", 100000, 0, int(time.time()), 0, len(elems))
    (lib / "rent" / "tester").write_bytes(head + b"".join(elems))


def _make_tester(lib: Path) -> None:
    """Crea `players/tester.dat` partendo da un giocatore esistente, con nome e password noti."""
    donor = next(p for p in sorted((lib / "players").glob("*.dat")) if p.stat().st_size == 3036)
    data = bytearray(donor.read_bytes())
    data[0:4] = (1 << 1).to_bytes(4, "little")  # iClass: solo chierico
    data[5:25] = bytes([0, 3]) + bytes(18)  # level[]: chierico 3
    data[2924:2944] = b"Tester".ljust(20, b"\0")
    data[2974:2985] = _crypt(PASSWORD, "ab")[:10].encode().ljust(11, b"\0")
    (lib / "players" / "tester.dat").write_bytes(data)
    _make_rent(lib)


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
        shutil.copytree(LIB, root / "lib")
        _make_tester(root / "lib")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        sock, audit = str(root / "l.sock"), root / "lib" / "livectl.audit"
        env = {**os.environ, "LIVECTL_SOCKET": sock, "LIVECTL_TOKEN": TOKEN, "LIVECTL_CLASSES": "read,write", "LIVECTL_AUDIT": str(audit)}
        proc = subprocess.Popen([str(root / "bin" / "leu"), "-d", "lib", str(port)], cwd=root, env=env,
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
