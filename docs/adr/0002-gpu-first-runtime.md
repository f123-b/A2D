# ADR-0002: GPU-first runtime

Status: Accepted

Decision:
Per-frame deformation is primarily GPU-side. CPU/WASM updates compact parameter and physics buffers.

Rejected:
CPU computes all deformed vertices and uploads full vertex buffers every frame.

Reason:
The rejected design scales poorly with vertex count and duplicates deformation logic across runtimes.
