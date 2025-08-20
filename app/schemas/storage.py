import enum
import typing
import aiohttp
import pydantic
import sqlalchemy
from . import Base
from ..utils.base import enum_serializer, AIOHTTP_CONNECTOR_GETTER


class StorageType(enum.Enum):
    URL = "url"


class StorageTable(Base):
    __tablename__ = 'storages'

    name = sqlalchemy.Column(sqlalchemy.Text, primary_key=True, nullable=False)
    nickname = sqlalchemy.Column(sqlalchemy.Text, nullable=True, default=None)
    type = sqlalchemy.Column(
        sqlalchemy.Enum(StorageType, name='storage_type', values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )


class StorageModel(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(from_attributes=True)

    name: str
    nickname: str | None = None
    type: typing.Annotated[StorageType, enum_serializer]

    async def get_content(self, raw_content) -> bytes:
        if self.type == StorageType.URL:
            async with aiohttp.ClientSession(connector=AIOHTTP_CONNECTOR_GETTER()) as session:
                async with session.get(raw_content) as response:
                    response.raise_for_status()
                    return await response.read()
        else:
            raise NotImplementedError