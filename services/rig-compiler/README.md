# A2D Rig Compiler

Input:
- normalized semantic layer package

Output:
- A2D Avatar IR + binary buffers + QA report

Pipeline:
1. semantic validation
2. landmarks
3. adaptive mesh
4. deformer generation
5. physics generation
6. expression generation
7. QA
8. pack `.a2d`

The compiler must not contain renderer-specific code.
