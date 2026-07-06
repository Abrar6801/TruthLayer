"""TruthLayer: an agentic RAG fact-checker.

Given a claim, TruthLayer searches the web for evidence, retrieves the most
relevant chunks with pgvector similarity search, and asks Claude for a
structured verdict (true / false / mixed / unverifiable) with citations.
"""

__version__ = "0.1.0"
