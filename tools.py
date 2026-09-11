# tools.py
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

import pixeltable as pxt

# Bind to the chunk view built by pipeline.ipynb (documents -> document_chunks split/embedded)
chunks_t = pxt.get_table("context_engineering.document_chunks")


@pxt.query
def financial_tool(query: str) -> dict:
    """Return top 3 chunks from financial documents most similar to the query."""
    sim = chunks_t.text.similarity(string=query)
    return (
        chunks_t.order_by(sim, asc=False)  # most similar first
        .select(chunks_t.text, similarity=sim)
        .limit(3)
    )