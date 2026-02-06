from sentence_transformers import SentenceTransformer, util
import torch

class TransformerRAG:
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        # Precompute query embedding for semantic matching
        self.query_text = "clean energy tax credit rebate incentive solar wind efficiency"
        self.query_embedding = self.model.encode(self.query_text, convert_to_tensor=True)

    def is_relevant(self, text: str, threshold: float = 0.6) -> bool:
        text_embedding = self.model.encode(text, convert_to_tensor=True)
        similarity = util.pytorch_cos_sim(self.query_embedding, text_embedding).item()
        return similarity >= threshold
