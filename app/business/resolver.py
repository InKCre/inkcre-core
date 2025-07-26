import abc
import asyncio
import base64
import json
import time
import typing

import aiohttp
import tencentcloud.common.credential
import tencentcloud.lke.v20231130.lke_client
import tencentcloud.lke.v20231130.models

from app.engine import SessionLocal
from app.schemas.block import ResolverType, BlockModel, BlockTable
from app.schemas.relation import RelationModel, RelationTable
from app.schemas.storage import AIOHTTP_CONNECTOR_GETTER, StorageType


TENCENT_LKE_CLIENT = tencentcloud.lke.v20231130.lke_client.LkeClient(
    tencentcloud.common.credential.EnvironmentVariableCredential().get_credential(),
    "ap-guangzhou",
)


class Resolver(abc.ABC):

    @classmethod
    def new(cls, block: BlockModel) -> typing.Self:
        if block.resolver == ResolverType.IMAGE:
            return ImageResolver(block)
        elif block.resolver == ResolverType.TEXT:
            return TextResolver(block)
        else:
            raise NotImplementedError

    # TODO 拿整个 block，不只是 content，要不要用 storage 来获取真实数据也由 resolver 来判断
    def __init__(self, block: BlockModel):
        """

        :param block: Block to resolve.
        """
        self._block = block

    B_or_R_TV = typing.TypeVar('B_or_R_TV', BlockModel, RelationModel)
    @abc.abstractmethod
    async def extract_blocks_and_relations(self) -> \
            typing.Callable[[], typing.Generator[B_or_R_TV, B_or_R_TV, None]]:
        """Break down the block into smaller blocks and relations.

        :param block_id: The block the content to resolve belongs to.
        :return:
        """
        ...

    @abc.abstractmethod
    async def to_text(self) -> str:
        """Transform content to text"""
        ...


class TextResolver(Resolver):

    async def extract_blocks_and_relations(self) -> \
            typing.Callable[[], typing.Generator[Resolver.B_or_R_TV, Resolver.B_or_R_TV, None]]:

        return lambda : None


class Detail(typing.TypedDict):
    type: str
    content: str
    actions: list[str]

class Img2TextResult(typing.TypedDict):
    details: list[Detail]
    summary: str
class ImageResolver(Resolver):

    async def extract_blocks_and_relations(self) -> \
            typing.Callable[[], typing.Generator[Resolver.B_or_R_TV, Resolver.B_or_R_TV, None]]:
        img2text_result = await self.__img2text()
        return lambda: self.__interactively_extract_BaR(img2text_result)

    def __get_custom_variables(self) -> dict:
        if self._block.storage is None:
            return {
                "ImgSource": base64.b64encode(self._block.content.encode("utf-8")).decode("utf-8")
            }
        elif self._block.get_storage_type() != StorageType.URL:
            raise NotImplementedError
        else:
            return {
                "ImgURL": self._block.content
            }

    async def __img2text(self) -> Img2TextResult:
        """Transform image to text

        - summary of image
        - key infos image provided
          - actions that needs the info
        """
        return Img2TextResult(**(await self.__run_lke_workflow(
            "1948959057036216384",
            **self.__get_custom_variables()
        ))["result"])

    async def __run_lke_workflow(self, workflow_id: str, **kwargs) -> dict:
        req = tencentcloud.lke.v20231130.models.CreateWorkflowRunRequest()
        req.AppBizId = workflow_id
        req.CustomVariables = tuple(
            {"Name": k, "Value": v}
            for k, v in kwargs.items()
        )
        workflow_run_id = TENCENT_LKE_CLIENT.CreateWorkflowRun(req).WorkflowRunId

        workflow_finish = False
        req = tencentcloud.lke.v20231130.models.DescribeWorkflowRunRequest()
        req.WorkflowRunId = workflow_run_id
        resp = None
        while not workflow_finish:
            resp = TENCENT_LKE_CLIENT.DescribeWorkflowRun(req)
            if resp.WorkflowRun.State in (2, 3, 4):
                workflow_finish = True
            await asyncio.sleep(1)

        for node in resp.NodeRuns:
            if node.NodeType == 16:
                end_node_run_id = node.NodeRunId
                req = tencentcloud.lke.v20231130.models.DescribeNodeRunRequest()
                req.NodeRunId = end_node_run_id
                resp = TENCENT_LKE_CLIENT.DescribeNodeRun(req)
                # TODO extract to download()
                async with aiohttp.ClientSession(connector=AIOHTTP_CONNECTOR_GETTER()) as session:
                    async with session.get(resp.NodeRun.OutputRef) as response:
                        response.raise_for_status()
                        raw_res = await response.json()
                        return raw_res

        raise RuntimeError("Workflow did not complete successfully.")

    def __interactively_extract_BaR(self, img2text_result: Img2TextResult) -> \
            typing.Generator[Resolver.B_or_R_TV, Resolver.B_or_R_TV, None]:
        # alt:text
        alt_text_block = yield BlockModel(resolver=ResolverType.TEXT, content=img2text_result["summary"])
        yield RelationModel(from_=self._block.id, to_=alt_text_block.id, content="alt:text")

        # info (key information)
        for item in img2text_result["details"]:
            info_block = yield BlockModel(resolver=ResolverType.TEXT, content=item["content"])
            yield  RelationModel(from_=self._block.id, to_=info_block.id, content="has content")
            info_type_block = yield BlockModel(resolver=ResolverType.TEXT, content=item["type"])
            yield RelationModel(from_=info_block.id, to_=info_type_block.id, content="is")
            for action in item["actions"]:
                action_block = yield BlockModel(resolver=ResolverType.TEXT, content=action)
                yield RelationModel(from_=action_block.id, to_=info_type_block.id, content="needs")

    async def to_text(self):
        """find relation "alt:text" and return the to block content
        """
        with SessionLocal() as db_session:
            alt_text_relation = db_session.query(RelationTable).filter(
                RelationTable.content == "alt:text",
                RelationTable.from_ == self._block.id
            ).one_or_none()
            if alt_text_relation:
                alt_text_to_block = db_session.query(BlockTable).filter(
                    BlockTable.id == alt_text_relation.to_
                ).one()
                return alt_text_to_block.content

            img2text_result = await self.__img2text()
            alt_text_block_table = BlockModel(
                resolver=ResolverType.TEXT, content=img2text_result["summary"]
            ).to_table()
            db_session.add(alt_text_block_table)
            db_session.flush()
            alt_text_relation_table = RelationModel(
                content="alt:text", to_=alt_text_block_table.id, from_=self._block.id
            ).to_table()
            db_session.add(alt_text_relation_table)

            db_session.commit()

            return img2text_result["summary"]

