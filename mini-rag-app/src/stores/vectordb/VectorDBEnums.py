from enum import Enum


class VectorDBEnums(Enum):
    QDRANT = "QDRANT"
    PGVECTOR = "PGVECTOR"


class DistanceMethodEnums(Enum):
    COSINE = "cosine"
    DOT = "dot"


class PgVectorTableSchemeEnums(Enum):
    ID = "id"
    TEXT = "text"
    VECTOR = "vector"
    CHUNK_ID = "chunk_id"
    METADATA = "metadata"
    TEXT_TSV = "text_tsv"
    _PREFIX = "pgvector"


class PgVectorHybridSearchEnums(Enum):
    TS_CONFIG = "arabic"
    CANDIDATES = 50
    RRF_K = 60
    SEMANTIC_WEIGHT = 0.7
    KEYWORD_WEIGHT = 0.3
    EF_SEARCH = 100
    BM25_K1 = 1.2
    BM25_B = 0.75
    BM25_TERMS_SUFFIX = "bm25_terms"
    BM25_STATS_SUFFIX = "bm25_stats"


class PgVectorDistanceMethodEnums(Enum):
    COSINE = "vector_cosine_ops"
    DOT = "vector_ip_ops"


class PgVectorIndexTypeEnums(Enum):
    HNSW = "hnsw"
    IVFFLAT = "ivfflat"
