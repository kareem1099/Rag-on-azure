from enum import Enum


class RerankEnums(Enum):
    HTTP = "HTTP"
    COHERE = "COHERE"


class RerankTargetEnums(Enum):
    PARENT = "parent"
    CHUNK = "chunk"
