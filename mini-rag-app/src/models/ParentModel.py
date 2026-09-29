from .BaseDataModel import BaseDataModel
from .dbschemas import Parent, DataChunk
from sqlalchemy.future import select
from sqlalchemy import delete


class ParentModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def insert_parents_with_chunks(self, parents: list, parents_chunks: list):
        async with self.db_client() as session:
            async with session.begin():
                session.add_all(parents)
                await session.flush()

                no_chunks = 0
                for parent, chunks in zip(parents, parents_chunks):
                    for chunk in chunks:
                        chunk.chunk_parent_id = parent.parent_id
                    session.add_all(chunks)
                    no_chunks += len(chunks)

        return len(parents), no_chunks

    async def get_parent(self, parent_id: int):
        async with self.db_client() as session:
            result = await session.execute(
                select(Parent).where(Parent.parent_id == parent_id))
            return result.scalar_one_or_none()

    async def delete_parents_by_project_id(self, project_id: int):
        async with self.db_client() as session:
            async with session.begin():
                await session.execute(
                    delete(DataChunk).where(DataChunk.chunk_project_id == project_id))
                result = await session.execute(
                    delete(Parent).where(Parent.parent_project_id == project_id))

        return result.rowcount
