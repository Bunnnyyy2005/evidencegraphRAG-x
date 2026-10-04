"""Page-grounded parsing, paragraph parents, sentence windows, two-stage ingestion."""
import hashlib
import re
import time
from pathlib import Path
import pymupdf
from .config import settings
from .utils import Store, digest


def parse_pdf(path: Path) -> tuple[list[dict], str]:
    cfg = settings()
    with pymupdf.open(path) as doc:
        if doc.needs_pass:
            raise ValueError('Encrypted PDFs are not supported')
        if len(doc) > cfg.max_pages:
            raise ValueError('PDF exceeds MAX_PAGES')
    if cfg.parser == 'docling':
        try:
            from docling.document_converter import DocumentConverter, PdfFormatOption
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
            converted = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(
                pipeline_options=options)}).convert(str(path)).document
            blocks = []
            section = 'Document'
            for item, _ in converted.iterate_items():
                label = str(item.label.value)
                if not item.prov:
                    continue
                # Never attach whole cross-page text to a single page citation.
                if len({p.page_no for p in item.prov}) > 1:
                    raise ValueError('Cross-page layout unit: use per-page fallback parsing')
                prov = item.prov[0]
                text = item.export_to_markdown(doc=converted) if label == 'table' else getattr(item, 'text', '')
                if label in ('section_header', 'title'):
                    section = text
                if text.strip():
                    blocks.append({'page_number': prov.page_no, 'section': section, 'text': text,
                        'metadata': {'kind': label, 'parser': 'docling',
                                     'provenance': [p.model_dump(mode='json') for p in item.prov]},
                        'bbox': prov.bbox.model_dump(mode='json') if prov.bbox else None})
            if blocks:
                return blocks, 'docling'
        except Exception as exc:
            Store().failure('parsing', exc)
    blocks = []
    with pymupdf.open(path) as doc:
        section = 'Document'
        for page_idx, page in enumerate(doc):
            tables = []
            try:
                for table in page.find_tables().tables:
                    tables.append((pymupdf.Rect(table.bbox), table.to_markdown()))
            except Exception as exc:
                Store().failure('parsing', exc)
            for box, text in tables:
                blocks.append({'page_number': page_idx+1, 'section': section, 'text': text,
                    'metadata': {'kind': 'table', 'parser': 'pymupdf'}, 'bbox': list(box)})
            for block in page.get_text('blocks', sort=True):
                if block[6] != 0 or any(pymupdf.Rect(block[:4]).intersects(b) for b, _ in tables):
                    continue
                text = block[4].strip()
                if not text:
                    continue
                if len(text.split()) < 18 and re.match(r'^(\d+(\.\d+)*\.?\s+\S|[A-Z][A-Z ]{5,})', text):
                    section = text.replace('\n', ' ')
                blocks.append({'page_number': page_idx+1, 'section': section, 'text': text,
                    'metadata': {'kind': 'paragraph', 'parser': 'pymupdf'}, 'bbox': list(block[:4])})
    if not blocks:
        raise ValueError('No extractable text. OCR the scanned PDF before uploading.')
    return blocks, 'pymupdf'


def make_chunks(blocks: list[dict], doc_id: str, name: str) -> list[dict]:
    """Never cross pages; contextual prefixes never replace original citation text."""
    cfg = settings()
    output = []
    for i, block in enumerate(blocks):
        paragraph_id = digest(f'{doc_id}:paragraph:{i}')
        section_id = digest(doc_id + ':' + block['section'])
        original = block['text']
        units = [original] if block['metadata']['kind'] == 'table' else re.split(r'(?<=[.!?])\s+|\n\s*\n', original)
        windows, pending = [], []
        for unit in units:
            # Long paragraphs are split at word boundaries; tables remain atomic.
            parts = [unit] if block['metadata']['kind'] == 'table' else [
                ' '.join(unit.split()[j:j+cfg.chunk_words]) for j in range(0, len(unit.split()), cfg.chunk_words)]
            for part in parts:
                if pending and len((' '.join(pending) + part).split()) > cfg.chunk_words:
                    windows.append(' '.join(pending)); pending = []
                pending.append(part)
        if pending:
            windows.append(' '.join(pending))
        for j, text in enumerate(windows):
            if not text.strip():
                continue
            cid = digest(f'{paragraph_id}:{j}:{text}')
            output.append({**block, 'document_id': doc_id, 'document_name': name,
                'chunk_id': cid, 'section_id': section_id, 'parent_id': paragraph_id,
                'text': text, 'parent_text': ' '.join(original.split()[:cfg.parent_words]),
                'context': f'Document: {name}. Section: {block["section"]}. Page: {block["page_number"]}.\n{text}'})
    return output


def ingest(doc_id: str, store: Store, retrieval, graph, graph_submit=None) -> None:
    doc = store.document(doc_id)
    started = time.perf_counter()
    def update(stage: str, **extra):
        doc.update(stage=stage, **extra)
        store.save_doc(doc)
    try:
        update('Parsing')
        blocks, parser = parse_pdf(store.root / 'uploads' / f'{doc_id}.pdf')
        update('Chunking', parser=parser)
        chunks = make_chunks(blocks, doc_id, doc['name'])
        update('Embedding', chunks=len(chunks))
        retrieval.index(chunks, lambda: update('Indexing'))
        store.save_chunks(doc_id, chunks)
        update('Searchable', searchable=True, revision=str(time.time()), stage1_seconds=time.perf_counter()-started)
        store.event('ingestion', {'document_id': doc_id, 'stage1_seconds': doc['stage1_seconds']})
    except Exception as exc:
        store.failure('parsing' if doc['stage'] == 'Parsing' else 'chunking' if doc['stage'] == 'Chunking' else 'retrieval', exc)
        update('Failed', error=f'{type(exc).__name__}: ingestion failed; inspect service configuration or PDF.')
        return
    if graph_submit is not None:
        update('Searchable — graph queued')
        graph_submit(doc_id, chunks)
        return
    enrich_document(doc_id, chunks, store, graph)


def enrich_document(doc_id: str, chunks: list[dict], store: Store, graph) -> None:
    """Stage 2 can use a separate queue so it never holds up later Stage 1 uploads."""
    doc = store.document(doc_id)
    def update(stage: str, **extra):
        doc.update(stage=stage, **extra)
        store.save_doc(doc)
    started = time.perf_counter()
    update('Graph extraction')
    try:
        result = graph.enrich(chunks)
        update(result['status'], graph=result, graph_revision=str(time.time()), stage2_seconds=time.perf_counter()-started)
    except Exception as exc:
        store.failure('entity extraction', exc)
        update('Searchable — graph unavailable', graph={'status': 'unavailable'}, stage2_seconds=time.perf_counter()-started)
    store.event('ingestion', {'document_id': doc_id, 'stage2_seconds': doc['stage2_seconds']})
