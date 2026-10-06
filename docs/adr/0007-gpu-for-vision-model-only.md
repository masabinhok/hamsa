# 0007. GPU reserved for the vision model; embedders on CPU

- Status: Accepted
- Date: 2026-10-06

## Context
The target machine has 8 GB of VRAM and 16 GB of RAM. Measured on 2026-10-06, Qwen3-VL-8B (Q4_K_M, 8k context) alone needs 8.0 GB and already spills about 29% to the CPU. Loading anything else on the GPU would push more of it off, or evict it and cost an 11-second reload per case.

## Options considered
- **Everything on the GPU, loaded and unloaded per stage.** Each swap costs seconds and fragments memory.
- **Smaller vision model (qwen3-vl:4b) to make room.** Fits fully, but may extract worse.
- **Vision model on the GPU, embedders on the CPU.** bge-m3 (via Ollama with `num_gpu: 0`) and SigLIP base are small enough for a 16-core CPU at desk volume.

## Decision
Only the vision model uses the GPU, kept warm with a 30-minute `keep_alive`. bge-m3 and SigLIP run on the CPU. The local verdict fallback reuses the vision model instead of loading a separate text model.

## Consequences
- Indexing the archive and corpus is slower on the CPU. It is a batch job run before the demo, not per case.
- qwen3-vl:4b remains an option, decided by comparing extraction quality on the eval set.
- Runs on any machine with about 8 GB of VRAM; with less, Ollama spills more to the CPU and it gets slower, but it still works.
