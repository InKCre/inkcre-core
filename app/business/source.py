import abc
import asyncio
import datetime
import importlib
import fastapi
from numpy import tri
import sqlmodel
import typing
from typing import Optional as Opt
from app.engine import SessionLocal
from app.schemas.block import BlockID, BlockModel
from app.schemas.relation import RelationModel
from app.schemas.source import SourceModel, SourceID
from app.task import scheduler
from app.utils.datetime_ import get_datetime


ConfigTV = typing.TypeVar("ConfigTV", bound=dict)
CollectGeneratedTV = typing.TypeVar("CollectGeneratedTV", bound=BlockModel)
class SourceBase(abc.ABC, typing.Generic[ConfigTV]):

    def __init__(self, _id: SourceID) -> None:
        self._id = _id

    async def collect(self, full: bool = False):
        """Collect new data from the source.

        :param full: 
            If True, collect all data, otherwise only new data.
            If True, collected data blocks will be inserted in reverse order.

        The order of collected blocks inserted into the database is the same
        as the order of blocks yielded by the generator.
        """
        collected: list[BlockModel] = []
        generator = self._collect(full=full)
        async for item in generator:  # type: ignore[assignment] pyright bug
            collected.append(item)
        
        with SessionLocal() as db:
            for i, block in enumerate((reversed(collected) if full else collected)):
                db.add(block)
                db.flush()
                db.refresh(block)
                # therotically, self._organize will be run after all committed
                scheduler.add_job(
                    func=self._organize,
                    kwargs={"block_id": block.id},
                    trigger="date",
                    run_date=get_datetime() + datetime.timedelta(seconds=i+1+6),
                )
            db.commit()

    @abc.abstractmethod
    async def _collect(
        self, full: bool = False
    ) -> typing.AsyncGenerator[BlockModel, None]:
        """The real collect implementation.
        """

    @abc.abstractmethod
    async def _organize(self, block_id: BlockID) -> None:
        """Organize the collected block.

        Organization to collected blocks are concurrently.
        """

    def get_config(self) -> ConfigTV:
        """Get the configuration of the source.
        """
        # TODO


class SourceManager:
    """
    
    - Run collect method of all configured sources
    - Add, remove and configure source instances
    - Add, remove sources
    """

    SOURCES: dict[SourceID, SourceBase] = {}

    @classmethod
    def set_up_collect_jobs(cls):
        with SessionLocal() as db:
            sources = db.exec(
                sqlmodel.select(SourceModel).where(SourceModel.collect_at is not None)
            ).all()

        for source in sources:
            if source.collect_at is None:
                continue
            scheduler.add_job(
                func=cls._get_source_ins(typing.cast(SourceID, source.id), source.type).collect,
                trigger=source.collect_at.to_trigger(),
                id=f"source.{source.id}.collect",
                replace_existing=True,
            )

    @classmethod
    def _get_source_ins(cls, source_id: SourceID, source_type: Opt[str] = None) -> SourceBase:
        ins = cls.SOURCES.get(source_id, None)
        if ins is None:
            if source_type is None:
                raise ValueError(f"Source {source_id} not instantiated and path to the class not defined.")
            source_module = importlib.import_module(source_type)
            source_class = typing.cast(type[SourceBase], getattr(source_module, "Source"))
            ins = source_class(_id=typing.cast(SourceID, source_id))
            cls.SOURCES[source_id] = ins
        return ins

    @classmethod
    async def run_a_collect(cls, source_id: int, full: bool = False):
        with SessionLocal() as db:
            source_model = db.exec(
                sqlmodel.select(SourceModel).where(SourceModel.id == source_id)
            ).one()

            await cls._get_source_ins(
                typing.cast(SourceID, source_model.id), source_model.type
            ).collect(full=full)
        
    @classmethod
    def create(cls, type_: str, nickname: Opt[str] = None) -> SourceModel:
        """Add a new source.
        """
        with SessionLocal() as db:
            source = SourceModel(type=type_, nickname=nickname)
            db.add(source)
            db.commit()
            db.refresh(source)
        
        return source
