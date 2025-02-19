---
title: "Parallel VM build"
categories:
  - NUMA
weight: 50
mermaid:
  force: true
---

## Introduction

When the `xenopsd` server receives a `VM.start` request, it:
1. splits the request it into micro-ops and
2. dispatches the micro-ops in one queue per VM.

When `VM.start` requests arrive faster than the thread pool
finishes them, the thread pool will run multiple
micro-ops for different VMs in parallel. This includes the
VM.build micro-op that does NUMA placement and VM memory allocation.

The [Xenopsd architecture](xenopsd/architecture/_index) and the
[walkthrough of VM.start](VM.start) provide more details.

This walkthrough dives deeper into the `VM_create` and `VM_build` micro-ops
and focusses on allocating the memory allocation for different VMs in
parallel with respect to the NUMA placement of the starting VMs.

## Architecture

This diagram shows the [architecture](../../../xenopsd/architecture/_index) of Xenopsd:

At the top of the diagram, two client RPCs have been sent:
One to start a VM and the other to fetch the latest events.
The `Xenops_server` module splits them into "micro-ops" (labelled "μ op" here).
These micro-ops are enqueued in queues, one queue per VM. The thread pool pulls
from the VM queues and runs the micro-ops:

![Inside xenopsd](../../../../xenopsd/architecture/xenopsd.svg)
<center><figcaption><i>Image 1: Xenopsd architecture</i></figcaption></center>

Overview of the micro-ops for creating a new VM:

- `VM.create`: create an empty Xen domain in the Hypervisor and the Xenstore
- `VM.build`: build a Xen domain: Allocate guest memory and load the firmware and `hvmloader`
- Several micro-ops to attach devices launch the device model.
- `VM.unpause`: unpause the domain

## Flowchart: Parallel VM start

When multiple `VM.start` run concurrently, an example could look like this:

{{% include "snippets/vm-build-parallel" %}}
