from .BaseDataModel import BaseDataModel
from .dbschemas import Project
from sqlalchemy.future import select
from sqlalchemy import func


class ProjectModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def create_project(self, project: Project):
        async with self.db_client() as session:
            async with session.begin():
                session.add(project)
            await session.commit()
            await session.refresh(project)

        return project

    async def get_project_or_create_one(self, project_id: int):
        async with self.db_client() as session:
            async with session.begin():
                query = select(Project).where(Project.project_id == project_id)
                result = await session.execute(query)
                project = result.scalar_one_or_none()

            if project is not None:
                return project

        return await self.create_project(project=Project(project_id=project_id))

    async def get_all_projects(self, page: int = 1, page_size: int = 10):
        async with self.db_client() as session:
            async with session.begin():
                total_documents = await session.execute(select(func.count(Project.project_id)))
                total_documents = total_documents.scalar_one()

                total_pages = total_documents // page_size
                if total_documents % page_size > 0:
                    total_pages += 1

                query = select(Project).offset((page - 1) * page_size).limit(page_size)
                result = await session.execute(query)
                projects = result.scalars().all()

                return projects, total_pages
