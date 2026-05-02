from typing import Annotated

from pydantic import AfterValidator, EmailStr


def _to_lower(v: str) -> str:
    return v.lower()


# Email type that lowercases at the schema boundary. Use everywhere the
# value identifies a User. Storage and downstream comparisons assume lowercase.
LowercaseEmail = Annotated[EmailStr, AfterValidator(_to_lower)]
