__all__ = [
    "BLOCK_ROUTER",
]

import json
import typing
import pydantic
import fastapi
import sqlalchemy.orm
import sqlmodel
from typing import Optional as Opt
from .resolver import Resolver
from ..engine import get_db_session, SessionLocal
from ..llm import one_chat, multi_chat
from ..schemas.block import BlockModel, ResolverType
from ..schemas.relation import RelationModel

BLOCK_ROUTER = fastapi.APIRouter(
    prefix="/blocks"
)

@BLOCK_ROUTER.get("/recent")
def get_recent_blocks(
    num: int = 10,
    db_session: sqlalchemy.orm.Session = fastapi.Depends(get_db_session),
) -> list[BlockModel]:
    """获取最新的块
    """
    return _get_recent_blocks(num=num, db_session=db_session)

def _get_recent_blocks(
    num: int,
    resolver: Opt[ResolverType] = None 
) -> tuple[BlockModel, ...]:
    """获取最新的块
    
    按创建时间倒序。

    :param num: 获取的块数量
    :param resolver: 限定解析器类型，None则不限定
    """
    with SessionLocal() as db_session:
        blocks = db_session.exec(
            sqlmodel.select(BlockModel)\
                .order_by(sqlmodel.desc(BlockModel.created_at))\
                .where(BlockModel.resolver == resolver if resolver else True)\
                .limit(num)
        ).all()

        return tuple(blocks)

@BLOCK_ROUTER.get("/{block_id}")
def get_block(
    block_id: int,
) -> BlockModel:
    block = _get_block(block_id)
    if block is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND,
            detail=f"Block with id {block_id} not found."
        )
    return block

def _get_block(block_id: int) -> Opt[BlockModel]:
    with SessionLocal() as db_session:
        block = db_session.exec(
            sqlmodel.select(BlockModel).where(BlockModel.id == block_id)
        ).one_or_none()
        return block


@BLOCK_ROUTER.post("")
def create_block(
    body: BlockModel,
    response: fastapi.Response,
    background_tasks: fastapi.BackgroundTasks,
    organize: bool = True,
):
    """创建块
    """
    body = _create_block(body)

    if organize:
        background_tasks.add_task(organize_block, body)

    response.status_code = 201
    return body


def _create_block(block: BlockModel) -> BlockModel:
    with SessionLocal() as db_session:
        db_session.add(block)
        db_session.commit()
        db_session.refresh(block)
    
    return block


async def organize_block(block: BlockModel):
    """整理块
    """
    with SessionLocal() as db_session:
        # if block.storage is not None:
        #     storage = db_session.query(StorageTable).filter(StorageTable.name == block.storage).one()
        #     storage_model = StorageModel.model_validate(storage)
        #     content = await storage_model.get_content(block.content)
        # else:
        #     content = block.content

        resolver = Resolver.new(block)
        generator = (await resolver.extract_blocks_and_relations())()
        try:
            i = generator.send(None)
            while True:
                table_i = i.to_table()
                db_session.add(table_i)
                db_session.flush()
                db_session.refresh(table_i)
                i = generator.send(i.__class__.model_validate(table_i))
        except StopIteration:
            pass

        db_session.commit()


@BLOCK_ROUTER.get("/embedding")
def query_from_block_by_embedding_h(
    block_id: int,
    num: int = 10,
    min_similarity: float = 0.5,
    type: typing.Literal['block', 'relation'] = 'block',
    db_session: sqlalchemy.orm.Session = fastapi.Depends(get_db_session),
):
    return _query_from_block_by_embedding(
        block_id=block_id,
        db_session=db_session,
        num=num,
        min_similarity=min_similarity,
        type=type
    )

def _query_from_block_by_embedding(
    block_id: int,
    db_session: sqlalchemy.orm.Session,
    num: int = 10,
    min_similarity: float = 0.5,
    type: typing.Literal['block', 'relation'] = 'block',
) -> tuple[BlockModel | RelationModel, ...]:
    """Query similar blocks or relations by embedding, query is a block.
    """
    block_table = db_session.query(BlockTable).filter(BlockTable.id == block_id).one()
    block = BlockTable.to_model(block_table)
    query_embedding = block.get_embedding()  # TODO what if None

    TypeTable = BlockTable if type == 'block' else RelationTable

    similars = db_session.execute(
        sqlalchemy
        .select(TypeTable)
        .where(TypeTable.embedding != None)
        .where(TypeTable.id != block.id)
        .filter()
        .order_by(TypeTable.embedding.cosine_distance(query_embedding))
        .limit(num)
    ).scalars().all()

    return tuple(
        TypeTable.to_model(i)
        for i in similars
    )


@BLOCK_ROUTER.get("/{block_id}/iteration")
async def iterate_from_block(
    block_id: int,
    max_depth: int = 2,
    exclude_start_block: bool = True,
    db_session: sqlalchemy.orm.Session = fastapi.Depends(get_db_session)
):
    return await _iterate_from_block(
        block_id=block_id,
        max_depth=max_depth,
        exclude_start_block=exclude_start_block,
        db_session=db_session
    )

async def _iterate_from_block(
    block_id: int,
    db_session: sqlalchemy.orm.Session,
    max_depth: int = 2,
    exclude_start_block: bool = True,
):

    depth = 0
    r_blocks: set[int] = set()
    r_relations: set[int] = set()

    if not exclude_start_block:
        r_blocks.add(block_id)

    def iterate_one(inner_block_id: int):
        nonlocal depth

        relations = db_session.query(RelationTable).filter(
            RelationTable.from_ == inner_block_id
        ).all()

        r_relations.update(relation.id for relation in relations)

        for relation in relations:
            block = db_session.query(BlockTable).filter(
                BlockTable.id == relation.to_
            ).one()
            r_blocks.add(block.id)

            if depth <= max_depth:
                iterate_one(block.id)

        depth += 1

    iterate_one(block_id)

    return {
        "relations": r_relations,
        "blocks": r_blocks
    }



class PickBaRBody(pydantic.BaseModel):
    blocks: set[int]
    relations: set[int]
    requirements: list[str] | None = None


@BLOCK_ROUTER.put("/pick")
def pick_blocks(
    body: PickBaRBody,
    method: typing.Literal['llm'] = 'llm',
    db_session: sqlalchemy.orm.Session = fastapi.Depends(get_db_session)
):
    if method == "llm":
        block_tables = db_session.query(BlockTable).filter(
            BlockTable.id.in_(body.blocks)
        ).all()
        blocks = tuple(
            BlockTable.to_model(block_table)
            for block_table in block_tables
        )

        relation_tables = db_session.query(RelationTable).filter(
            RelationTable.id.in_(body.relations)
        ).all()
        relations = tuple(
            RelationTable.to_model(relation_table)
            for relation_table in relation_tables
        )

        prompt = "下面有一组块和一组关系，根据关系对块的注释，选出最满足要求的几个块。"
        prompt += "块的内容即信息。关系描述块和块之间的联系，是块的动态属性。"
        prompt += "关系可以解读为：<to.content>是<from.content>的<relation.content>。"
        # prompt += "务必只返回JSON，格式如下：```json\n"
        # prompt += json.dumps({
        #     "relations": [1, 2],
        #     "blocks": [1, 2]
        # })
        # prompt += "```\n"
        prompt += "务必只返回JSON，格式为整数数组。"

        prompt += "## 块\n```csv\n"
        prompt += "id,content\n"
        for block in blocks:
            prompt += f"{block.id},{block.content}\n"

        prompt += "```\n## 关系\n```csv\n"
        prompt += "id,from,to,content\n"
        for relation in relations:
            prompt += f"{relation.id},{relation.from_},{relation.to_},{relation.content}\n"

        prompt += "```\n## 要求"
        if body.requirements:
            prompt += "\n- ".join(body.requirements)
        else:
            raise ValueError

        llm_res = one_chat(prompt)

        return json.loads(llm_res.strip("```")[4:])
    else:
        raise NotImplementedError


@BLOCK_ROUTER.get("/query/llm_driven")
async def llm_driven_block_query(
    block_id: int,
    prompt: str = "",
    scope: int = 1,  # 视野范围
    db_session: sqlalchemy.orm.Session = fastapi.Depends(get_db_session)
):
    meta_prompt = "沿着<块与关系局部视野>，找出信息库中满足<查询要求>的块。\n"
    # meta_prompt += "- 无效假设：默认推定这些信息都不符合要求。\n"
    meta_prompt += "每次回复都严格地只返回下列内容：\n"
    meta_prompt += "- `FOLLOW:<block_id>.` 表明你暂时没找到，但仍然可以沿着关系继续探索信息库；这会使<块和关系局部视野>移动到你指定关系的目标块。\n"
    meta_prompt += "- `FOUND:[<block_id1>, <block_id2>].` 表明你已找到**最**符合要求的块。\n"
    meta_prompt += "  - **最**表示你确定没有更符合要求的块了\n"
    meta_prompt += "- `NOTFOUND:<reason>.` 表明尽了所有努力，在整个信息库中的确找不到符合要求的块。\n"

    query_block = _get_block(block_id, db_session)
    # use embed to find a start block (see query block as external)
    start_block = _query_from_block_by_embedding(
        block_id=block_id, db_session=db_session,
        type="block", num=3
    )[0]

    query_prompt = "<查询要求>\n"
    query_prompt += f"- {prompt}\n"
    query_prompt += f"- {await query_block.get_context_as_text()}\n"
    query_prompt += "</查询要求>\n"

    chat = multi_chat(meta_prompt+query_prompt)

    async def llm_driven_query(current_block_id: int) -> typing.Iterable[int]:
        current_block = _get_block(current_block_id, db_session)

        raw_outgoing_relations = db_session.query(RelationTable).filter(
            RelationTable.from_ == current_block_id,
        ).all()
        outgoing_relations = tuple(
            RelationTable.to_model(relation)
            for relation in raw_outgoing_relations
        )

        context_prompt = "<块与关系局部视野>\n"
        # context_prompt += f"当前块内容：{await current_block.get_context_as_text()}\n"
        context_prompt += "当前块的外向关系：\n```csv\n关系ID,目标块是当前块的,目标块ID,目标块内容\n"
        for outgoing_relation in outgoing_relations:
            to_block = _get_block(outgoing_relation.to_, db_session)
            context_prompt += f"{outgoing_relation.id},{outgoing_relation.content},{to_block.id},{await to_block.get_context_as_text()}\n"
        context_prompt += "```\n"

        if not outgoing_relations:
            raw_incoming_relations = db_session.query(RelationTable).filter(
                RelationTable.to_ == current_block_id,
            ).all()
            incoming_relations = tuple(
                RelationTable.to_model(relation)
                for relation in raw_incoming_relations
            )
            context_prompt += "当前块的内向关系：\n```csv\n关系ID,当前块是来源块的,来源块ID,来源块内容\n"
            for incoming_relation in incoming_relations:
                from_block = _get_block(incoming_relation.from_, db_session)
                context_prompt += f"{incoming_relation.id},{incoming_relation.content},{incoming_relation.from_},{await from_block.get_context_as_text()}\n"
            context_prompt += "```\n"
        context_prompt += "</块与关系局部视野>\n不要忘记<查询要求>！"

        res = chat(context_prompt)
        command, params = res.split(":", 1)

        params = params.split(".", 1)[0]
        if command == "FOLLOW":
            return await llm_driven_query(int(params))
        elif command == "FOUND":
            return json.loads(params)
        elif command == "NOTFOUND":
            return []
        else:
            raise ValueError(f"unknown command from LLM, {command}")

    return await llm_driven_query(start_block.id)

