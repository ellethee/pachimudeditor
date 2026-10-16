"""Hash delle password degli account di gioco: Argon2id, stessi parametri e formato di `pachimud.account.security`.

`PasswordHasher()` con i default di argon2-cffi (time_cost=3, memory_cost=64 MiB, parallelism=4): l'hash e' la
stringa autodescrittiva `$argon2id$...`, quindi un hash fatto qui si verifica nel gioco e viceversa
(`tests/test_equivalence.py`). Dipendenza dichiarata in `pyproject.toml` (`argon2-cffi`).
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    """L'hash Argon2id (con salt casuale e parametri incorporati) della password in chiaro."""
    return _hasher.hash(plain_password)


def verify_password(stored_hash: str, plain_password: str) -> bool:
    """`True` se la password corrisponde all'hash; mai eccezioni per credenziali errate o hash non valido."""
    try:
        _hasher.verify(stored_hash, plain_password)
        return True
    except VerifyMismatchError, VerificationError, InvalidHash:
        return False
