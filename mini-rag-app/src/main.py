from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import quote_plus
from routes.base import base_router
from routes.data import data_router
from routes.nlp import nlp_router
from helpers.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from stores.llm.LLMProviderFactory import LLMProviderFactory
from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory
from stores.llm.templates.template_parser import TemplateParser
from stores.rerank.RerankProviderFactory import RerankProviderFactory
from helpers.security import verify_api_key
from utils.metrics import setup_metrics, initialize_metrics


app = FastAPI()
setup_metrics(app)

# Added last so it is the outermost middleware and answers browser preflight (OPTIONS) requests.
cors_origins = [o.strip() for o in (get_settings().CORS_ALLOWED_ORIGINS or "").split(",") if o.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
app.include_router(base_router)
app.include_router(data_router, dependencies=[Depends(verify_api_key)])
# The answer endpoint is public; the other NLP endpoints check the API key per route.
app.include_router(nlp_router)


@app.on_event("startup")
async def startup_span():
    settings = get_settings()

    postgres_conn = (
        f"postgresql+asyncpg://{settings.POSTGRES_USERNAME}:{quote_plus(settings.POSTGRES_PASSWORD)}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_MAIN_DATABASE}"
    )

    app.db_engine = create_async_engine(
        postgres_conn,
        connect_args={"ssl": "require"} if settings.POSTGRES_SSL else {},
    )
    app.db_client = sessionmaker(
        app.db_engine, class_=AsyncSession, expire_on_commit=False
    )

    llm_provider_factory = LLMProviderFactory(settings)

    app.generation_client = llm_provider_factory.create(provider=settings.GENERATION_BACKEND)
    app.generation_client.set_generation_model(model_id=settings.GENERATION_MODEL_ID)

    app.fallback_generation_client = None
    if settings.GENERATION_FALLBACK_BACKEND and settings.GENERATION_FALLBACK_MODEL_ID:
        app.fallback_generation_client = llm_provider_factory.create(provider=settings.GENERATION_FALLBACK_BACKEND)
        app.fallback_generation_client.set_generation_model(model_id=settings.GENERATION_FALLBACK_MODEL_ID)

    app.embedding_client = llm_provider_factory.create(provider=settings.EMBEDDING_BACKEND)
    app.embedding_client.set_embedding_model(model_id=settings.EMBEDDING_MODEL_ID,
                                             embedding_size=settings.EMBEDDING_MODEL_SIZE)

    vector_db_provider_factory = VectorDBProviderFactory(config=settings, db_client=app.db_client)

    app.vectordb_client = vector_db_provider_factory.create(provider=settings.VECTOR_DB_BACKEND)
    await app.vectordb_client.connect()

    app.rerank_client = RerankProviderFactory(settings).create(provider=settings.RERANK_BACKEND)

    app.template_parser = TemplateParser(
        language=settings.PRIMARY_LANG,
        default_language=settings.DEFAULT_LANG,
    )

    model_ids = [settings.GENERATION_MODEL_ID, settings.GENERATION_FALLBACK_MODEL_ID]
    model_ids += [m.strip() for m in (settings.GEMINI_FALLBACK_MODELS or "").split(",")]
    initialize_metrics(app, [m for m in model_ids if m])


@app.on_event("shutdown")
async def shutdown_span():
    await app.db_engine.dispose()
    await app.vectordb_client.disconnect()
    if app.rerank_client:
        await app.rerank_client.close()
