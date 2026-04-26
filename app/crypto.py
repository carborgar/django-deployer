import os
from cryptography.fernet import Fernet

_KEY_PATH = os.environ.get("DEPLOYER_KEY_PATH", "/etc/deployer/secret.key")
_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        with open(_KEY_PATH, "rb") as f:
            key = f.read().strip()
        _fernet = Fernet(key)
    return _fernet


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


def generate_key() -> bytes:
    return Fernet.generate_key()
