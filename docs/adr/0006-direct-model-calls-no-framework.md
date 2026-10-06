# 0006. Direct model calls with schema-validated JSON, no LLM framework

- Status: Accepted
- Date: 2026-10-06

## Context
Hamsa makes three kinds of model call: extraction (Ollama, vision), embeddings (Ollama, SigLIP), and verdict (Groq, OpenAI-compatible API). Each needs a strict output schema, retries, a fallback, and a record of which model ran, all of which have to be explained in the AI usage disclosure.

## Options considered
- **LangChain, LlamaIndex, or similar.** Ready-made retrievers and chains, but large dependency trees, fast-moving APIs, and indirection that makes "where exactly is the model output consumed?" harder to answer.
- **Thin clients written here,** using `httpx` and Pydantic.

## Decision
Call Ollama and Groq directly over HTTP. Request JSON with the schema derived from the Pydantic model, validate the response with the same model, and handle retries and fallback in one small module.

## Consequences
- Roughly a hundred lines of client code to own and test.
- Each model call is one function, which maps one-to-one onto the README disclosure table.
- No framework upgrade can change pipeline behaviour.
