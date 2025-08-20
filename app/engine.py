__all__ = [
    'SQLDB_ENGINE',
    'get_db_session',
    'SessionLocal',
]

import os
import typing
import sqlalchemy.orm
import sqlalchemy.dialects.postgresql
# from sqlalchemy import create_engine
import sqlmodel


# configs
USERNAME = os.getenv('DB_USERNAME', 'root')
PASSWORD = os.getenv('DB_PASSWORD', '')
HOST = os.getenv('DB_HOST', 'localhost')
PORT = int(os.getenv('DB_PORT', '5432'))
DATABASE = os.getenv('DB_DATABASE', 'public')
SCHEMA = os.getenv('DB_SCHEMA', 'public')


SQLDB_ENGINE = sqlmodel.create_engine(
    f'postgresql+psycopg2://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}',
    connect_args={"options": f"-csearch_path={SCHEMA}"}
)

# SessionLocal = sqlalchemy.orm.sessionmaker(autocommit=False, autoflush=False, bind=SQLDB_ENGINE)
def SessionLocal():
    return sqlmodel.Session(SQLDB_ENGINE)

def get_db_session() -> typing.Generator:
    """A fastapi dependency to get a database session."""
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
