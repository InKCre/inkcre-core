import datetime
import enum
import typing

import pgvector.sqlalchemy
import pydantic
import sqlalchemy.orm

from app.llm import get_embeddings
from app.engine import SessionLocal
from app.utils import enum_serializer
from app.schemas.storage import StorageTable, StorageType, StorageModel

Base = sqlalchemy.orm.declarative_base()


class ResolverType(enum.Enum):
    IMAGE = "image"
    TEXT = "text"
    JSON = "json"


class BlockTable(Base):
    __tablename__ = 'blocks'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    updated_at = sqlalchemy.Column(sqlalchemy.DateTime,
        default=datetime.datetime.now, onupdate=datetime.datetime.now, nullable=False
    )
    storage = sqlalchemy.Column(sqlalchemy.ForeignKey(StorageTable.name), nullable=True, default=None)
    resolver = sqlalchemy.Column(sqlalchemy.Enum(
        ResolverType, name='resolver_type', values_callable=lambda x: [e.value for e in x]
    ), nullable=False)
    content = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    embedding = sqlalchemy.Column(pgvector.sqlalchemy.VECTOR(1024), nullable=True, default=None)

    @classmethod
    def to_model(cls, table: type[typing.Self]) -> 'BlockModel':
        return BlockModel.model_validate(table)


class BlockModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    id: int | None = None
    updated_at: datetime.datetime = pydantic.Field(default_factory=datetime.datetime.now)
    storage: str | None = None
    resolver: typing.Annotated[ResolverType, enum_serializer]
    content: str

    def to_table(self, embedding: bool = True) -> BlockTable:
        return BlockTable(
            embedding=self.get_embedding() if embedding else None,
            **self.model_dump()
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

