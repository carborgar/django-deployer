import re

_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_valid_env_key(key: str) -> bool:
    return bool(_ENV_KEY_RE.match(key))


def parse_env_text(env_text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Parsea texto tipo .env y devuelve (pares_validos, lineas_invalidas)."""
    pairs: list[tuple[str, str]] = []
    invalid_lines: list[str] = []

    for idx, raw_line in enumerate(env_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

        if "=" not in line:
            invalid_lines.append(f"L{idx}: {raw_line}")
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if not is_valid_env_key(key):
            invalid_lines.append(f"L{idx}: {raw_line}")
            continue

        pairs.append((key, value))

    return pairs, invalid_lines

