import hashlib
import random


class MockChat:
    """Mock chat model for development when Qwen API is unavailable."""

    def generate(self, prompt: str, system: str = "") -> str:
        return f"[Mock Mode] Based on your query, I found suitable products matching your criteria. Please see the product list for details."


class MockEmbedding:
    """Mock embedding — returns deterministic pseudo-vectors from text hash.

    NOT semantically meaningful. Used only for running the retriever pipeline
    during development when Qwen API is unavailable.
    """

    DIM = 128

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
            rng = random.Random(seed)
            vectors.append([rng.random() for _ in range(self.DIM)])
        return vectors
