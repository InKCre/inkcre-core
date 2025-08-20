import datetime
import typing
import sqlalchemy
import pgvector.sqlalchemy
import sqlmodel
from typing import Optional as Opt
from ..llm import get_embeddings
from ..engine import SessionLocal
from ..schemas.storage import StorageTable, StorageType, StorageModel

ResolverType: typing.TypeAlias = str


BlockID: typing.TypeAlias = int

class BlockModel(sqlmodel.SQLModel, table=True):
    __tablename__ = 'blocks'  # type: ignore

    id: Opt[BlockID] = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.Integer, primary_key=True, autoincrement=True),
        default=None
    )
    created_at: datetime.datetime = sqlmodel.Field(
        default_factory=datetime.datetime.now,
        sa_column=sqlalchemy.Column(sqlalchemy.TIMESTAMP(timezone=True))
    )
    updated_at: datetime.datetime = sqlmodel.Field(
        default_factory=datetime.datetime.now,
        sa_column=sqlalchemy.Column(
            sqlalchemy.TIMESTAMP(timezone=True), onupdate=datetime.datetime.now
        )
    )
    storage: Opt[str] = sqlmodel.Field(
        default=None,
        sa_column=sqlalchemy.Column(
            sqlalchemy.ForeignKey(StorageTable.name), nullable=True
        )
    )
    resolver: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    )
    content: str = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.Text, nullable=False)
    )

    def get_embedding(self) -> list[float] | None:
        if self.storage is None:
            return get_embeddings(self.content)
        return None

    def get_storage_type(self) -> StorageType:
        if self.storage:
            with SessionLocal() as db_session:
                return db_session.query(StorageTable.type).filter(
                    StorageTable.name == self.storage
                ).one().type
        else:
            raise ValueError

    async def get_real_content(self):
        if self.storage is not None:
            with SessionLocal() as db_session:
                storage = db_session.query(StorageTable).filter(StorageTable.name == self.storage).one()
                storage_model = StorageModel.model_validate(storage)
                return await storage_model.get_content(self.content)
        else:
            return self.content

    async def get_context_as_text(self) -> str:
        if self.storage is not None:
            from app.business.resolver import Resolver
            resolver = Resolver.new(self)
            return await resolver.to_text()
        else:
            return self.content


class BlockEmbeddingModel(sqlmodel.SQLModel, table=True):
    __tablename__ = 'block_embeddings'  # type: ignore

    id: int = sqlmodel.Field(
        foreign_key="blocks.id", primary_key=True, nullable=False,
    )
    embedding: tuple[float, ...] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(pgvector.sqlalchemy.VECTOR(1024), nullable=False)
    )
