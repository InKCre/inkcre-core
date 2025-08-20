import apscheduler.triggers.cron
import sqlalchemy
import typing
import sqlmodel
from typing import Optional as Opt


SourceID: typing.TypeAlias = int


class CollectAt(sqlmodel.SQLModel):
    day_of_week: Opt[int] = sqlmodel.Field(default=None, ge=0, le=6)
    """0-6, where 0 is Monday
    """
    hour: Opt[int] = sqlmodel.Field(default=None, ge=0, le=23)
    minute: Opt[int] = sqlmodel.Field(default=None, ge=0, le=59)

    def to_trigger(self) -> apscheduler.triggers.cron.CronTrigger:
        return apscheduler.triggers.cron.CronTrigger(
            day_of_week=self.day_of_week,
            hour=self.hour,
            minute=self.minute,
        )

class SourceModel(sqlmodel.SQLModel, table=True):
    __tablename__: str = 'sources'  # type: ignore

    id: Opt[SourceID] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, autoincrement=True),
        default=None,
    )
    type: str = sqlmodel.Field(sa_column=sqlalchemy.Column(sqlalchemy.Text))
    """Type of source.
    
    An absolute import path to the module where souce class at.
    """
    nickname: Opt[str] = sqlmodel.Field(nullable=True, default=None)
    config: Opt[dict] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.JSON),
        default=None, 
    )
    collect_at: Opt[CollectAt] = sqlmodel.Field(
        sa_column=sqlalchemy.Column(sqlalchemy.JSON),
        default=None,
    )
    """When to run collect method of this source.

    None for disabled.
    """