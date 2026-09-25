# 09 — Calculator Design (Deterministic)

```mermaid
flowchart LR
    I[User Input] --> V[Validation] --> RS[Rule Selection] --> RV[Regulation Version] --> F[Deterministic Formula] --> R[Result] --> LB[Legal Basis] --> E[Optional LLM Explanation]
```

Implementasi `app/services/calculator/engine.py`: `thr` (PP 36/2021) dan
`pesangon` (PP 35/2021 simplified), versioned + effective date + formula ID.
LLM hanya untuk penjelasan, tidak untuk angka. Unit-tested boundary.
