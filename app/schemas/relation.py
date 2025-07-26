import typing
import datetime
import pydantic
import sqlalchemy.orm
import pgvector.sqlalchemy

from app.llm import get_embeddings
from app.schemas.block import BlockTable

Base = sqlalchemy.orm.declarative_base()


class RelationTable(Base):
    __tablename__ = 'relations'

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True)
    updated_at = sqlalchemy.Column(sqlalchemy.DateTime,
        default=datetime.datetime.now, onupdate=datetime.datetime.now, nullable=False
    )
    from_ = sqlalchemy.Column(sqlalchemy.Integer,
        sqlalchemy.ForeignKey(BlockTable.id), nullable=False
    )
    to_ = sqlalchemy.Column(sqlalchemy.Integer,
        sqlalchemy.ForeignKey(BlockTable.id), nullable=False
    )
    content = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    embedding = sqlalchemy.Column(pgvector.sqlalchemy.VECTOR(1024), nullable=True, default=None)

    @classmethod
    def to_model(cls, table: type[typing.Self]) -> 'RelationModel':
        return RelationModel.model_validate(table)


class RelationModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    id: int | None = None
    updated_at: datetime.datetime = pydantic.Field(default_factory=datetime.datetime.now)
    from_: int
    to_: int
    content: str

    def to_table(self) -> RelationTable:
        return RelationTable(
            embedding=self.get_embedding(),
            **self.model_dump()
        )

    def get_embedding(self) -> list[float] | None:
        return get_embeddings(self.content)
