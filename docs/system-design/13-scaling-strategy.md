# 13 — Scaling Strategy

Stage 1 (now): 1 API + 1 worker + Neon + Supabase Storage + Upstash Redis/
Vector + Groq. Stage 2 (traffic naik): replikas API/worker, Redis
coordination, DB pool tuning, namespace/release management, CDN/browser
cache, pagination admin. Stage 3: pisah service hanya bila ada bukti
independent scaling / bottleneck / ownership / isolation. Tanpa K8s/Kafka/
service mesh/CQRS/microservices — managed services + modular monolith.
