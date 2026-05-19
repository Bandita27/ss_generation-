from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Modern declarative base. Required for Mapped[] typing to work."""
    pass