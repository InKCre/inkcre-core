
from app.engine import SessionLocal
from app.schemas.block import BlockID
from app.schemas.relation import RelationModel


class RelationManager:

    @classmethod
    def create(cls, from_: BlockID, to_: BlockID, content: str) -> RelationModel:
        """Create a relation
        """
        relation = RelationModel(from_=from_, to_=to_, content=content)
        with SessionLocal() as db:
            db.add(relation)
            db.commit()
            db.refresh(relation)

        return relation

