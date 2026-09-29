from .BaseDataModel import BaseDataModel
from .dbschemas import Asset
from sqlalchemy.future import select


class AssetModel(BaseDataModel):

    def __init__(self, db_client: object):
        super().__init__(db_client=db_client)

    @classmethod
    async def create_instance(cls, db_client: object):
        return cls(db_client)

    async def create_asset(self, asset: Asset):
        async with self.db_client() as session:
            async with session.begin():
                session.add(asset)
            await session.commit()
            await session.refresh(asset)

        return asset

    async def get_all_project_assets(self, asset_project_id: int, asset_type: str):
        async with self.db_client() as session:
            query = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_type == asset_type,
            )
            result = await session.execute(query)
            return result.scalars().all()

    async def get_asset_record(self, asset_project_id: int, asset_name: str):
        async with self.db_client() as session:
            query = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_name == asset_name,
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()
