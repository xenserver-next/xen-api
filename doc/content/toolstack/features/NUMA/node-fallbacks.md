---
title: VM.build Use neighbouring NUMA nodes
mermaid:
    force: true
    theme: forest
    mermaidInitialize: '{ "theme": "base" }'
---

{{%include "topologies/2x2.md" %}}

This shows that the distance to remote memory on the same socket
is far lower than the distance to the other socket, which is twice
the local memory distance.

As a result, this means that using remote memory on the same socket
increases the distance by only by 1/10th than using the other socket.


Hence, for VMs builds where might not be enough NUMA memory on one
NUMA node, using same-socket memory would have only about 50% of the
than remote-socket memory would have.

At same time, if the memory is (roughly) equally spread over two
NUMA nodes on the same socket, it could make sense to move the
vCPU affinity between the two NUMA nodes depending on their CPU load.





In the simplest case, the vCPU affinity could be set to e.g. two
NUMA nodes on the same socket (specified as having low distance),
which would cause Xen to allocate the memory from both NUMA nodes.

If this is not done,


## 
| Node | RAM | used | free |
| ----:| ---:| ----:| ----:|
|    1 |  50 |   35 |   15 |
|    2 |  50 |   45 |    5 |
|    3 |  50 |   35 |   15 |
|    4 |  50 |   35 |   15 |
|  all | 200 |  150 |   50 |

<!---
This shows that the distance to remote memory on the same socket
is far lower than the distance to the other socket, which is twice
the local memory distance.

As a result, this means that using remote memory on the same socket
increases the distance by only by 1/10th than using the other socket.

Hence, for VMs builds where might not be enough NUMA memory on one
NUMA node, using same-socket memory would have only about 50% of the
than remote-socket memory would have.

At same time, if the memory is (roughly) equally spread over two
NUMA nodes on the same socket, it could make sense to move the
vCPU affinity between the two NUMA nodes depending on their CPU load.

In the simplest case, the vCPU affinity could be set to e.g. two
NUMA nodes on the same socket (specified as having low distance),
which would cause Xen to allocate the memory from both NUMA nodes.

If this is not done,

## 
| Node | RAM | used | free |
| ----:| ---:| ----:| ----:|
|    1 |  50 |   35 |   15 |
|    2 |  50 |   45 |    5 |
|    3 |  50 |   35 |   15 |
|    4 |  50 |   35 |   15 |
|  all | 200 |  150 |   50 |

--->