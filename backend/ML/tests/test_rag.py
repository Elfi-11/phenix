from dataclasses import replace
from types import SimpleNamespace
import pytest
from langchain_core.embeddings import Embeddings
from rag.config import Config
from rag.documents import corpus_files, chunks
from rag.index import build, search
from rag.assistant import answer, embedding_client, chat_client


class FakeEmbeddings(Embeddings):
    """Double déterministe : ne mesure pas la pertinence du vrai modèle."""
    def embed_query(self, text):
        text = text.lower()
        return [float("prometheus" in text), float("paiement" in text), 0.01]

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


class FakeLLM:
    def __init__(self, content="Prometheus collecte les métriques [S1]."):
        self.content = content
        self.messages = None

    def invoke(self, messages):
        self.messages = messages.to_messages()
        return SimpleNamespace(content=self.content)


@pytest.fixture
def configured(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "infra.md").write_text("Prometheus collecte les métriques du backend.", encoding="utf-8")
    (corpus / "metier.txt").write_text("Un paiement est une opération fictive.", encoding="utf-8")
    return Config(corpus_dir=corpus, index_path=tmp_path / "data/index.json", min_similarity=0.7)


def test_full_retrieval_and_sourced_answer(configured):
    embeddings = FakeEmbeddings()
    assert build(configured, embeddings)["files"] == 2
    hits = search(configured, embeddings, "Que fait Prometheus ?")
    assert len(hits) == 1
    assert hits[0]["metadata"]["source"] == "infra.md"
    llm = FakeLLM()
    result = answer(configured, "Que fait Prometheus ?", embeddings, llm)
    assert result["status"] == "answered"
    assert result["sources"][0]["source"] == "infra.md"
    assert "CONTEXTE DOCUMENTAIRE" in llm.messages[1].content


def test_no_matching_passage_does_not_call_llm(configured):
    embeddings = FakeEmbeddings()
    build(configured, embeddings)
    class ForbiddenLLM:
        def invoke(self, *args):
            raise AssertionError("Le LLM ne doit pas être appelé sans passage pertinent")
    result = answer(configured, "Comment cuisiner ?", embeddings, ForbiddenLLM())
    assert result["status"] == "insufficient_context"
    assert result["sources"] == []


@pytest.mark.parametrize("content", ["Affirmation sans référence.", "Réponse [S999].", "Réponse [S1] [S99]."])
def test_invented_or_missing_citations_are_rejected(configured, content):
    embeddings = FakeEmbeddings()
    build(configured, embeddings)
    result = answer(configured, "Prometheus ?", embeddings, FakeLLM(content))
    assert result["status"] == "unverified_citations"
    assert result["sources"] == []


def test_changed_or_deleted_documents_force_reindex(configured):
    embeddings = FakeEmbeddings()
    build(configured, embeddings)
    (configured.corpus_dir / "infra.md").write_text("Nouvelle procédure Prometheus.")
    with pytest.raises(ValueError, match="Corpus modifié"):
        search(configured, embeddings, "Prometheus")
    build(configured, embeddings)
    (configured.corpus_dir / "metier.txt").unlink()
    with pytest.raises(ValueError, match="Corpus modifié"):
        search(configured, embeddings, "Prometheus")


def test_model_change_forces_reindex(configured):
    embeddings = FakeEmbeddings()
    build(configured, embeddings)
    with pytest.raises(ValueError, match="Configuration"):
        search(replace(configured, embedding_model="other-model"), embeddings, "Prometheus")


def test_failed_embedding_keeps_previous_index(configured):
    build(configured, FakeEmbeddings())
    previous = configured.index_path.read_bytes()
    class FailingEmbeddings(FakeEmbeddings):
        def embed_documents(self, texts):
            raise ConnectionError("Ollama indisponible")
    with pytest.raises(ConnectionError):
        build(configured, FailingEmbeddings())
    assert configured.index_path.read_bytes() == previous


def test_empty_corpus_and_missing_index_are_explicit(configured):
    with pytest.raises(ValueError, match="Index absent"):
        search(configured, FakeEmbeddings(), "Prometheus")
    for file in configured.corpus_dir.iterdir():
        file.unlink()
    with pytest.raises(ValueError, match="Corpus vide"):
        build(configured, FakeEmbeddings())


def test_hidden_files_and_links_are_not_read(configured, tmp_path):
    (configured.corpus_dir / ".secrets.md").write_text("secret")
    (configured.corpus_dir / ".env").write_text("PASSWORD=secret")
    outside = tmp_path / "outside.md"
    outside.write_text("secret")
    (configured.corpus_dir / "linked.md").symlink_to(outside)
    names = {p.name for p in corpus_files(configured.corpus_dir)}
    assert names == {"infra.md", "metier.txt"}


def test_pdf_source_page_metadata(configured):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 20 700 Td (Prometheus test document) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    with (configured.corpus_dir / "procedure.pdf").open("wb") as f:
        writer.write(f)
    docs = chunks(configured.corpus_dir, 1000, 150)
    pdf_docs = [d for d in docs if d.metadata["source"] == "procedure.pdf"]
    assert len(pdf_docs) == 1
    assert pdf_docs[0].metadata["page"] == 1
    assert "Prometheus" in pdf_docs[0].page_content


def test_real_langchain_client_configuration(configured):
    # Valide les interfaces installées ; aucune requête réseau.
    assert embedding_client(configured).model == "embeddinggemma:300m"
    assert chat_client(configured).model == "qwen3:4b-instruct"