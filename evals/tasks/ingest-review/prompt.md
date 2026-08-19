Review ingest.go for production readiness under load.

Context: one Process call receives a batch of up to 20000 messages. The
enrichment service starts shedding load above ~500 concurrent requests. db is a
*sql.DB with a pool of 8 connections. POST /v1/enrich is not idempotent.

Report your findings. Do not modify any files.
