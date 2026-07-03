# Isolated LightRAG ingest+query runner. One image, two compose services (method A / method B),
# each with its own working_dir volume. LLM+embeddings come from the host's Ollama over the
# container boundary (no in-image model, no API key).
FROM python:3.12-slim

WORKDIR /app

# lightrag-hku pinned to the version whose chunker behaviour the repo tests fix (1.5.4);
# google-genai + google-api-core = deps of the maintained lightrag.llm.gemini binding (LLM + embed);
# tiktoken = LightRAG's default tokenizer.
RUN pip install --no-cache-dir \
        "lightrag-hku==1.5.4" \
        "google-genai>=1.0" \
        "google-api-core>=2.0" \
        "tiktoken>=0.7" \
        "numpy>=1.26" \
        "nano-vectordb" \
        "networkx"

# Pre-cache tiktoken's cl100k_base BPE at build time so runtime needs no internet for tokenizing.
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

COPY ingest_query.py /app/ingest_query.py

ENTRYPOINT ["python", "/app/ingest_query.py"]
