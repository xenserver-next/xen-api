---
title: "Parallel VM.build"
---

Summary of the xenopsd architecture when running micro-ops
in parallel:

See: [VM.build: Architecture](architecture.md)

Running multiple `VM.build` micro-ops in parallel can
run into two kinds of race conditions for NUMA placement:

- [Lazy scrubbing by the Xen hypervisor](lazy-scrubbing.md)