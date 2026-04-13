"""
RAG Motion Retriever
--------------------
Embeds hero motion descriptors once, then answers text queries with the
nearest matching pkl file path.

Usage (CLI):
    python rag_retrieve.py "punch forward hard"
    python rag_retrieve.py "wave goodbye"

Usage (API — import into Kim's orchestrator):
    from rag_retrieve import MotionRetriever
    retriever = MotionRetriever()                # loads model once
    pkl_path, score = retriever.query("smash downward")
    # pkl_path → "rag_dataset/hulk_smash_kinematics.pkl"  score → 0.91

Requires:
    pip install sentence-transformers
    (auto-installed on first run if missing)

Dataset: vinod_workspace/rag_dataset/descriptors.json + *_kinematics.pkl
"""

import json
import subprocess
import sys
from pathlib import Path

DATASET_DIR  = Path(__file__).parent / "rag_dataset"
DESC_FILE    = DATASET_DIR / "descriptors.json"
MODEL_NAME   = "all-MiniLM-L6-v2"   # 80MB, CPU-friendly, no API key


def _ensure_sentence_transformers():
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        print("[RAG] sentence-transformers not found — installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "sentence-transformers", "-q"])
        print("[RAG] Installed.")


class MotionRetriever:
    def __init__(self):
        _ensure_sentence_transformers()
        from sentence_transformers import SentenceTransformer
        import numpy as np

        if not DESC_FILE.exists():
            raise FileNotFoundError(
                f"Descriptor file not found: {DESC_FILE}\n"
                "Run generate_rag_dataset.py first."
            )

        print(f"[RAG] Loading model '{MODEL_NAME}'...")
        self._model = SentenceTransformer(MODEL_NAME)
        self._np    = np

        with open(DESC_FILE) as f:
            descriptors: dict[str, str] = json.load(f)

        self._names      = list(descriptors.keys())
        self._texts      = list(descriptors.values())
        self._pkl_paths  = [DATASET_DIR / f"{name}_kinematics.pkl" for name in self._names]

        # Embed all descriptors once at init
        print(f"[RAG] Embedding {len(self._texts)} motion descriptors...")
        self._embeddings = self._model.encode(self._texts, normalize_embeddings=True)
        print("[RAG] Ready.")

    def query(self, text: str, top_k: int = 1) -> list[tuple[Path, float, str]]:
        """
        Find the closest motion(s) to a text query.

        Returns list of (pkl_path, cosine_score, animation_name), sorted best-first.
        top_k=1 returns a single-element list.
        """
        q_vec   = self._model.encode([text], normalize_embeddings=True)
        scores  = (self._embeddings @ q_vec.T).flatten()
        indices = self._np.argsort(scores)[::-1][:top_k]

        return [
            (self._pkl_paths[i], float(scores[i]), self._names[i])
            for i in indices
        ]


def main():
    if len(sys.argv) < 2:
        print("Usage: python rag_retrieve.py \"your motion description\"")
        sys.exit(1)

    query_text = " ".join(sys.argv[1:])
    retriever  = MotionRetriever()

    print(f"\nQuery: \"{query_text}\"")
    print("-" * 40)

    results = retriever.query(query_text, top_k=3)
    for rank, (pkl_path, score, name) in enumerate(results, 1):
        exists = "✓" if pkl_path.exists() else "✗ MISSING"
        print(f"  #{rank}  {name:<30}  score={score:.3f}  {exists}")

    best_pkl, best_score, best_name = results[0]
    print(f"\nBest match: {best_pkl}  (score={best_score:.3f})")
    print("Feed this path to g1_arm_replay_airborne.py --pkl")


if __name__ == "__main__":
    main()
