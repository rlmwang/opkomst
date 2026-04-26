from nanoid import generate

# URL-safe alphabet, no easily-confused characters (no 0/O, 1/l/I).
_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"


def new_slug(length: int = 8) -> str:
    """Generate a short, public, URL-friendly event slug."""
    return generate(_ALPHABET, length)
