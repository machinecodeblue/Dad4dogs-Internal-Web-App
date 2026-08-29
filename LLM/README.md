# LLM Instruction & Specification Root

This directory contains all authoritative architecture, code governance, and domain specifications for Dad4dogs.

## Structure

- **`PROJECT.md`**: Tactical map — tech stack, package trees, implementation status matrix, quick CLI commands.
- **`PHILOSOPHY.md`**: Code governance — ~150–200 line limit, domain package standards, import layering matrix, state transition invariants.
- **`domains/`**: The Live Specifications (Single Source of Truth). All code and migrations must match the files in this folder.
- **`proposals/`**: Discussion and RFC sandbox. Open proposals evaluated across documents. Never implement code directly from here.
- **`decisions/`**: Immutable archive of resolved proposals (accepted, rejected, or partial). Read for historical rationale only.

## Read Order for LLM Sessions

1. `LLM/PROJECT.md`
2. `LLM/PHILOSOPHY.md` (for structural, architectural, or multi-file changes)
3. `LLM/domains/<domain>.md` (for the specific feature or view being modified)