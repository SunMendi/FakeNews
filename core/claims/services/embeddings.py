from functools import lru_cache

from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSIONS = 384


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    """
    Load the embedding model once and reuse it.
    This avoids downloading/loading it for every request.
    """
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """
    Convert text into a multilingual embedding vector.
    Works for Bangla, English, and mixed text.
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("Text for embedding cannot be empty.")

    model = get_embedding_model()
    vector = model.encode(cleaned_text, normalize_embeddings=True)
    return vector.tolist()
