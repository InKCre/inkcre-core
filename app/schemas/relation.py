import typing
from typing import Optional as Opt
import datetime
import sqlalchemy
import pgvector.sqlalchemy
import sqlmodel
from ..llm import get_embeddings
from ..schemas.block import BlockModel


class RelationModel(sqlmodel.SQLModel, table=True):
    __tablename__ = 'relations'  # type: ignore

    id: Opt[int] = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.Integer, primary_key=True, autoincrement=True),
        default=None
    )
    updated_at: datetime.datetime = sqlmodel.Field(
        default_factory=datetime.datetime.now, 
        sa_column=sqlalchemy.Column(
            sqlalchemy.TIMESTAMP(timezone=True), onupdate=datetime.datetime.now
        )
    )
    from_: int = sqlmodel.Field(
        sa_column=sqlalchemy.Column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey("blocks.id", ondelete="CASCADE", onupdate="CASCADE")
        )
    )
    to_: int = sqlmodel.Field(
        sa_column=sqlalchemy.Column(
            sqlalchemy.Integer,
            sqlalchemy.ForeignKey("blocks.id", ondelete="CASCADE", onupdate="CASCADE")
        )
    )
    content: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    )

    def get_embedding(self) -> list[float] | None:
        return get_embeddings(self.content)


class RelationEmbeddingModel(sqlmodel.SQLModel, table=True):
    __tablename__ = 'relation_embeddings'  # type: ignore

    id: int = sqlmodel.Field(foreign_key="relations.id", primary_key=True, nullable=False)
    embedding: tuple[float, ...] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(pgvector.sqlalchemy.VECTOR(1024), nullable=False)
    )
