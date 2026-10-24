from app.config import settings

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import declarative_base, sessionmaker

    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()

    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def init_db():
        from app.db import models  # noqa: F401
        Base.metadata.create_all(bind=engine)

except ImportError:
    # Minimal fallback session for test execution if sqlalchemy is not installed in local host
    class Base:
        metadata = None

    def get_db():
        yield None

    def init_db():
        pass
