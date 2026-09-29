from pydantic import BaseModel
from typing import Optional
class processingRequest(BaseModel):
    file_id: Optional[str] = None
    chunk_size: Optional[int] = 350
    overlap_size: Optional[int] = 50
    do_reset: Optional[int] = 0
    