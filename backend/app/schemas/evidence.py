from pydantic import BaseModel


class Evidence(BaseModel):
    evidence_id: str
    source_type: str  # review, policy, spec, visual, compatibility
    source_id: str
    product_id: str
    content: str
    modality: str = "text"  # text, image, structured
    confidence: float = 1.0
    metadata: dict = {}
