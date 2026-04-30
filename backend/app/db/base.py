from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. All ORM models inherit from this.

    Having a single Base means SQLAlchemy can discover all tables via
    Base.metadata, which lets us call create_all() or run Alembic migrations
    against every model at once.
    """

    pass
