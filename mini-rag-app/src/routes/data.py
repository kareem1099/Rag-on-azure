from fastapi import APIRouter, UploadFile, Depends, status, Request
from fastapi.responses import JSONResponse
from helpers.config import get_settings, Settings
from controllers.DataController import DataController
from controllers.ProjectController import ProjectController
from controllers.ProcessingController import ProcessingController
from models.ProjectModel import ProjectModel
from models.ParentModel import ParentModel
from models.AssetModel import AssetModel
from models.dbschemas import DataChunk, Asset, Parent
from models.enums.AssetTypeEnum import AssetTypeEnum
from models import ResponseSignal
from .scheams.data import processingRequest
import aiofiles
import logging
import os

logger = logging.getLogger("uvicorn.error")

data_router = APIRouter()

data_controller = DataController()
project_controller = ProjectController()


@data_router.post("/upload/{project_id}")
async def upload_data(request: Request, project_id: int, file: UploadFile,
                      app_settings: Settings = Depends(get_settings)):

    is_valid, result_signal = data_controller.validate_uploaded_file(file=file)

    if not is_valid:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                            content={"signal": result_signal.value})

    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(project_id=project_id)

    file_path, file_id = data_controller.generate_unique_filepath(
        orig_file_name=file.filename, project_id=project_id)

    try:
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(app_settings.FILE_DEFAULT_CHUNK_SIZE):
                await f.write(chunk)
    except Exception as e:
        logger.error(f"Error while uploading file: {e}")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                            content={"signal": ResponseSignal.FILE_UPLOAD_FAILED.value})

    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)

    asset_resource = Asset(
        asset_project_id=project.project_id,
        asset_type=AssetTypeEnum.FILE.value,
        asset_name=file_id,
        asset_size=os.path.getsize(file_path),
        asset_config={
            "orig_name": file.filename,
            "content_type": file.content_type,
        },
    )

    asset_record = await asset_model.create_asset(asset=asset_resource)

    return JSONResponse(content={
        "signal": ResponseSignal.FILE_UPLOAD_SUCCESS.value,
        "file_id": file_id,
        "asset_id": str(asset_record.asset_id),
    })


@data_router.post("/process/{project_id}")
async def process_data(request: Request, project_id: int,
                       process_request: processingRequest):

    project_model = await ProjectModel.create_instance(db_client=request.app.db_client)
    project = await project_model.get_project_or_create_one(project_id=project_id)

    asset_model = await AssetModel.create_instance(db_client=request.app.db_client)

    project_files_ids = {}

    if process_request.file_id:
        asset_record = await asset_model.get_asset_record(
            asset_project_id=project.project_id,
            asset_name=process_request.file_id,
        )

        if asset_record is None:
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                                content={"signal": ResponseSignal.FILE_ID_NOT_FOUND.value})

        project_files_ids = {asset_record.asset_id: asset_record.asset_name}

    else:
        project_files = await asset_model.get_all_project_assets(
            asset_project_id=project.project_id,
            asset_type=AssetTypeEnum.FILE.value,
        )

        project_files_ids = {record.asset_id: record.asset_name for record in project_files}

    if len(project_files_ids) == 0:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                            content={"signal": ResponseSignal.NO_FILES_ERROR.value})

    processing_controller = ProcessingController(project_id=project_id)
    parent_model = await ParentModel.create_instance(db_client=request.app.db_client)

    if process_request.do_reset == 1:
        _ = await parent_model.delete_parents_by_project_id(project_id=project.project_id)

    no_parents = 0
    no_records = 0
    no_files = 0

    for asset_id, file_id in project_files_ids.items():

        parents = processing_controller.process_file(
            file_id=file_id,
            chunk_size=process_request.chunk_size,
            chunk_overlap=process_request.overlap_size,
        )

        if parents is None or len(parents) == 0:
            return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST,
                                content={"signal": ResponseSignal.PROCESSING_FAILED.value})

        parents_records = [
            Parent(
                parent_text=parent["text"],
                parent_metadata=parent["metadata"],
                parent_order=parent["order"],
                parent_project_id=project.project_id,
                parent_asset_id=asset_id,
            )
            for parent in parents
        ]

        chunk_order = 0
        parents_chunks_records = []
        for parent in parents:
            parent_chunks = []
            for child in parent["children"]:
                chunk_order += 1
                parent_chunks.append(DataChunk(
                    chunk_text=child["text"],
                    chunk_metadata=child["metadata"],
                    chunk_order=chunk_order,
                    chunk_project_id=project.project_id,
                    chunk_asset_id=asset_id,
                ))
            parents_chunks_records.append(parent_chunks)

        inserted_parents, inserted_chunks = await parent_model.insert_parents_with_chunks(
            parents=parents_records,
            parents_chunks=parents_chunks_records,
        )

        no_parents += inserted_parents
        no_records += inserted_chunks
        no_files += 1

    return JSONResponse(content={
        "signal": ResponseSignal.PROCESSING_SUCCESS.value,
        "inserted_parents": no_parents,
        "inserted_chunks": no_records,
        "processed_files": no_files,
    })
