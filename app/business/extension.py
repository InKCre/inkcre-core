

import abc
import typing
import fastapi
import sqlmodel
import importlib
from typing import Optional as Opt
from app.engine import SessionLocal
from app.schemas.extension import ExtensionModel, ExtensionID


ConfigTV = typing.TypeVar("ConfigTV", bound=sqlmodel.SQLModel)
StateTV = typing.TypeVar("StateTV", bound=sqlmodel.SQLModel)
class ExtensionBase(abc.ABC, typing.Generic[ConfigTV, StateTV]):

    config: ConfigTV
    state: StateTV

    def __init_subclass__(
        cls,
        ext_id: ExtensionID,
        config_cls: type[ConfigTV],
        state_cls: type[StateTV],
        **kwargs
    ) -> None:
        cls.__extid__ = ext_id
        cls.__configcls__ = config_cls
        cls.__statecls__ = state_cls
        return super().__init_subclass__(**kwargs)

    @classmethod
    def on_start(cls, router: fastapi.APIRouter, config: dict, state: dict):
        cls.config = cls.__configcls__(**config)
        cls.state = cls.__statecls__(**state)
        cls._register_apis(router)
        cls._register_resolver()

    @classmethod
    async def on_close(cls):
        ExtensionManager.save_config_and_state(
            ext_id=cls.__extid__, config=cls.config, state=cls.state
        )

    @classmethod
    @abc.abstractmethod
    def _register_apis(cls, router: fastapi.APIRouter):
        ...

    @classmethod
    @abc.abstractmethod
    def _register_resolver(cls):
        ...


class ExtensionManager:

    extention_classes: list[type[ExtensionBase]] = []

    @classmethod
    def install(cls, git_url: str, version: Opt[str] = None) -> ExtensionModel:
        # TODO
        ...

    @classmethod
    def get_extensions(cls, enabled_only: bool = True) -> tuple[ExtensionModel, ...]:
        """Get installed extensions.
        """
        with SessionLocal() as db:
            return tuple(db.exec(
                sqlmodel.select(ExtensionModel).where(
                    ExtensionModel.disabled == (not enabled_only)
                )
            ).all())
        
    @classmethod
    def start_all(cls, app: fastapi.FastAPI):
        """Start enabled entensions."""
        for extension in cls.get_extensions():
            extension_module = importlib.import_module(f"extensions.{extension.id}")
            extension_class = typing.cast(type[ExtensionBase], extension_module.Extension)
            cls.extention_classes.append(extension_class)

            # Start the extension
            extension_router = fastapi.APIRouter(prefix=f"/{extension.id}")
            extension_class.on_start(
                router=extension_router,
                config=extension.config or {},
                state=extension.state or {}
            )
            app.include_router(extension_router, tags=["extension", extension.id])

            # Register resolver
            extension_class._register_resolver()

    @classmethod
    async def close_all(cls):
        """Close all extensions.
        
        It could involves closes of connections, so asynchronous.
        """
        for extension_class in cls.extention_classes:
            await extension_class.on_close()

    @classmethod
    def save_config_and_state(
        cls, ext_id: ExtensionID, 
        config: Opt[sqlmodel.SQLModel] = None, 
        state: Opt[sqlmodel.SQLModel] = None
    ) -> ExtensionModel:
        with SessionLocal() as db:
            extension_model = db.exec(
                sqlmodel.select(ExtensionModel).where(ExtensionModel.id == ext_id)
            ).one()
            if config:
                extension_model.config = config.model_dump()
            if state:
                extension_model.state = state.model_dump()
            db.add(extension_model)
            db.commit()
        
        return extension_model
