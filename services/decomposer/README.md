# A2D Decomposer

Phase 1 integration target: See-through.

This service owns the adapter and normalization boundary:

flat image -> upstream decomposition -> normalized semantic layers

Downstream code must depend on the normalized layer contract, not directly on See-through names.
