"""Lecture du seul corpus sélectionné ; aucun parcours du dépôt ni des secrets."""
from hashlib import sha256
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

SUFFIXES = {".md", ".txt", ".pdf"}


def corpus_files(folder: Path):
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError(f"Dossier de corpus absent : {folder}")
    result = []
    for file in sorted(folder.rglob("*")):
        relative = file.relative_to(folder)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if file.is_symlink() or file.suffix.lower() not in SUFFIXES or not file.is_file():
            continue
        if not file.resolve().is_relative_to(folder):
            continue
        result.append(file)
    return result


def fingerprint(folder: Path):
    folder = folder.resolve()
    return {str(p.relative_to(folder)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest()
            for p in corpus_files(folder)}


def chunks(folder: Path, chunk_size: int, chunk_overlap: int):
    docs = []
    folder = folder.resolve()
    for file in corpus_files(folder):
        source = file.relative_to(folder).as_posix()
        if file.suffix.lower() == ".pdf":
            for page_number, page in enumerate(PdfReader(file).pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    docs.append(Document(page_content=text, metadata={"source": source, "page": page_number}))
        else:
            text = file.read_text(encoding="utf-8-sig")
            if text.strip():
                docs.append(Document(page_content=text, metadata={"source": source, "page": None}))
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap,
                                              add_start_index=True)
    return splitter.split_documents(docs)