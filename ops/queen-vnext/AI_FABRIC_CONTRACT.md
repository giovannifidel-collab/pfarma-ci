# HIVE Universal AI Fabric vNext contract

Queen consumes one aggregate capability: `hive.ai.general`.

Backends are replaceable routes, not Queen identity. Each execution result must preserve the standard contract `agent.run(task) -> {status,text,metadata}` and include sanitized provenance fields sufficient for later certification and independence checks.

The public execution layer must not change Queen V1 release locks or self-promote a provider into managed/certified status.
