
__all__ = [
    'SQLDB_ENGINE',
    'get_db_session',
    'SessionLocal',
]

import os
import numpy as np
import typing
import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.dialects.postgresql


USERNAME = 'root'
# PASSWORD = ''
PASSWORD = "T8Yk1asmQDt5S76rpUhF4y0IEeP9d3C2"
# HOST = 'localhost'
HOST = "hkg1.clusters.zeabur.com"
# PORT = '5432'
PORT = 30581
# DATABASE = 'public'
DATABASE = "zeabur"
# SCHEMA = 'public'
SCHEMA = "public"

SQLDB_ENGINE = sqlalchemy.create_engine(
    f'postgresql+psycopg2://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}',
    connect_args={"options": f"-csearch_path={SCHEMA}"}
)

SessionLocal = sqlalchemy.orm.sessionmaker(autocommit=False, autoflush=False, bind=SQLDB_ENGINE)

def get_db_session() -> typing.Generator:
    """A fastapi dependency to get a database session."""
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
