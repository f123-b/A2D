# ADR-0001: A2D owns the canonical Avatar IR

Status: Accepted

Decision:
`.a2d` / A2D Avatar IR is the canonical internal format.

Consequences:
- Runtime and Editor share one model.
- Exporters convert outward.
- Cubism/nijilive-specific fields cannot be required by the core schema.
- Format evolution uses explicit `formatVersion`.
