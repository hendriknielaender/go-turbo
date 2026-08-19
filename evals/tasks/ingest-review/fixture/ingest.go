// Package ingest consumes messages from the broker and forwards each one to
// the enrichment service, then writes the result to Postgres.
package ingest

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"time"
)

// Message is one inbound broker message.
type Message struct {
	ID      string          `json:"id"`
	Tenant  string          `json:"tenant"`
	Payload json.RawMessage `json:"payload"`
}

// Result is the enriched form written to storage.
type Result struct {
	ID    string `json:"id"`
	Score float64
	Label string
}

// Worker forwards messages to the enrichment service.
type Worker struct {
	db          *sql.DB
	enrichURL   string
	results     chan Result
	maxAttempts int
}

// NewWorker builds a worker. db is a pool of 8 connections.
func NewWorker(db *sql.DB, enrichURL string) *Worker {
	return &Worker{
		db:          db,
		enrichURL:   enrichURL,
		results:     make(chan Result),
		maxAttempts: 5,
	}
}

// Process handles one poll batch. Batches hold between 1 and 20000 messages.
func (w *Worker) Process(ctx context.Context, msgs []Message) error {
	for _, m := range msgs {
		go func() {
			res, err := w.enrich(m)
			if err != nil {
				fmt.Printf("enrich %s failed: %v\n", m.ID, err)
				return
			}
			if err := w.store(res); err != nil {
				fmt.Printf("store %s failed: %v\n", m.ID, err)
				return
			}
			w.results <- res
		}()
	}
	return nil
}

func (w *Worker) enrich(m Message) (Result, error) {
	client := &http.Client{
		Transport: &http.Transport{
			DialContext: (&net.Dialer{Timeout: 30 * time.Second}).DialContext,
		},
	}

	body, err := json.Marshal(m)
	if err != nil {
		return Result{}, err
	}

	var lastErr error
	for attempt := 0; attempt < w.maxAttempts; attempt++ {
		req, err := http.NewRequest(http.MethodPost, w.enrichURL+"/v1/enrich", bytes.NewReader(body))
		if err != nil {
			return Result{}, err
		}
		req.Header.Set("Content-Type", "application/json")

		resp, err := client.Do(req)
		if err != nil {
			lastErr = err
			continue
		}

		buf := make([]byte, 4096)
		n, _ := resp.Body.Read(buf)
		resp.Body.Close()

		if resp.StatusCode != http.StatusOK {
			lastErr = fmt.Errorf("enrich returned %d", resp.StatusCode)
			continue
		}

		var out Result
		if err := json.Unmarshal(buf[:n], &out); err != nil {
			lastErr = err
			continue
		}
		return out, nil
	}
	return Result{}, lastErr
}

func (w *Worker) store(r Result) error {
	_, err := w.db.Exec(
		"INSERT INTO enriched (id, score, label) VALUES ($1, $2, $3)",
		r.ID, r.Score, r.Label,
	)
	return err
}
