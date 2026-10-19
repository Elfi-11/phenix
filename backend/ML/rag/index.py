"""Petit index JSON et recherche cosinus exhaustive, adaptés à un corpus de workshop."""
import json
import math
import os
import tempfile

from rag.documents import chunks, fingerprint

FORMAT_VERSION = 1


def normalize(vector):
    values = [float(x) for x in vector]
    norm = math.sqrt(sum(x*x for x in values))
    if not values or not math.isfinite(norm) or norm == 0:
        raise ValueError("Vecteur d'embedding vide, nul ou non fini")
    return [x/norm for x in values]


def signature(config):
    return {"embedding_model": config.embedding_model, "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap}


def build(config, embeddings):
    before = fingerprint(config.corpus_dir)
    documents = chunks(config.corpus_dir, config.chunk_size, config.chunk_overlap)
    if not documents:
        raise ValueError("Corpus vide ou sans texte extractible. Ajouter des documents .md, .txt ou PDF texte.")
    vectors = []
    for offset in range(0, len(documents), 16):
        batch = documents[offset:offset+16]
        vectors.extend(embeddings.embed_documents([d.page_content for d in batch]))
    if len(vectors) != len(documents):
        raise ValueError("Nombre d'embeddings incompatible avec les passages")
    vectors = [normalize(v) for v in vectors]
    if len({len(v) for v in vectors}) != 1:
        raise ValueError("Dimensions d'embeddings incohérentes")
    after = fingerprint(config.corpus_dir)
    if before != after:
        raise ValueError("Le corpus a changé pendant l'indexation ; relancer ingest")
    data = {"format_version": FORMAT_VERSION, "config": signature(config), "files": after,
            "chunks": [{"text": d.page_content, "metadata": d.metadata, "vector": v}
                       for d, v in zip(documents, vectors)]}
    config.index_path.parent.mkdir(parents=True, exist_ok=True)
    # Remplacement atomique : une erreur ne détruit pas l'ancien index.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=config.index_path.parent,
                                         suffix=".json", delete=False) as f:
            temporary = f.name
            json.dump(data, f, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, config.index_path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    return {"files": len(after), "chunks": len(documents), "embedding_model": config.embedding_model}


def load(config):
    if not config.index_path.exists():
        raise ValueError("Index absent : lancer d'abord python -m rag ingest")
    data = json.loads(config.index_path.read_text(encoding="utf-8"))
    if data.get("format_version") != FORMAT_VERSION or data.get("config") != signature(config):
        raise ValueError("Configuration d'index modifiée : relancer ingest")
    if data.get("files") != fingerprint(config.corpus_dir):
        raise ValueError("Corpus modifié depuis l'indexation : relancer ingest")
    return data


def search(config, embeddings, question):
    data = load(config)
    vector = normalize(embeddings.embed_query(question))
    scored = []
    for chunk in data["chunks"]:
        if len(chunk["vector"]) != len(vector):
            raise ValueError("Dimension du modèle modifiée : relancer ingest")
        score = sum(x*y for x, y in zip(vector, chunk["vector"]))
        if score >= config.min_similarity:
            scored.append({"text": chunk["text"], "metadata": chunk["metadata"], "score": score})
    return sorted(scored, key=lambda item: item["score"], reverse=True)[:config.top_k]