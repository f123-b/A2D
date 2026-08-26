# Phase 1 — R4 Status

Status: **IMPLEMENTED / CONTRACT FROZEN**

Completed:
- GPU deformation logical buffer contract
- variable per-vertex morph influence table
- parameter normalization contract
- pseudo3d_head reference equations
- dirty parameter upload contract
- CPU reference evaluator
- binary morph pack/unpack helpers
- WebGL2 GPU deformation renderer
- WebGL2 dynamic parameter texture updates
- WebGL2 morph influence GPU texture
- static proxy-Z vertex attribute
- R4 golden `.a2d`
- CPU golden vectors
- correctness tolerance `1e-4`

Important WebGL2 decision:
- no CPU per-frame vertex deformation
- Parameter State -> R32F texture
- Parameter Definition -> RGBA32F texture
- Morph Influence -> RGBA32F texture
- influence ranges -> static integer vertex attribute

Current WebGL2 v1 cap:
- max 8 morph influences per vertex
- Avatar IR itself does not inherit this cap; WebGPU may support more

Next:
R5 — deterministic spring-chain physics and physics-to-parameter outputs.
