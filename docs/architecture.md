# Architecture

```mermaid
flowchart LR
  S[Versioned sources and figures] --> P[Prompt and source bundle]
  P --> G[Bounded generation]
  G --> V[Mechanical validation]
  V --> R[Independent source review]
  R --> T[Translation]
  T --> B[Bilingual review]
  B --> H[Human attestation]
  H --> U[Strict publication]
  G --> L[Local attempt ledger and recovery]
```

The default demo replays synthetic content; live generation is optional. Source evidence and questions stay outside reader prose. Source and reader hashes invalidate stale acceptance. Only generated static output enters the deployment artifact.
