import sqlmodel
import typing
from typing import Optional as Opt


ExtensionID: typing.TypeAlias = str

class ExtensionModel(sqlmodel.SQLModel, table=True):
    """
    
    Globally, every extension has a unique ID.
    Only one instance of each extension on a deployment.
    If a record presents here, the extension is installed.
    """

    __tablename__: str = 'extensions'  # type: ignore

    id: ExtensionID = sqlmodel.Field(primary_key=True)
    version: str = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.Text, nullable=False)
    )
    """Version of extension.
    
    type: A tuple of (major, minor, patch) version numbers.
    """
    disabled: bool = sqlmodel.Field(default=False)
    nickname: Opt[str] = sqlmodel.Field(default=None)
    config: Opt[dict] = sqlmodel.Field(default=None, sa_column=sqlmodel.Column(sqlmodel.JSON))
    state: Opt[dict] = sqlmodel.Field(default=None, sa_column=sqlmodel.Column(sqlmodel.JSON))
    """Store simple K-V state.
    """
