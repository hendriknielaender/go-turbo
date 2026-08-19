# Graceful Shutdown

Signals, drain order, and the deadline after which you stop being graceful.

`signal.NotifyContext` gives the process one cancellation root and a stop
function that unregisters signal handling. Graceful shutdown needs a fresh,
bounded context because the signal-derived context is already canceled.

```go
func run(parent context.Context, srv *http.Server) error {
	runCtx, stop := signal.NotifyContext(
		parent,
		os.Interrupt,
		syscall.SIGTERM,
	)
	defer stop()

	serveErr := make(chan error, 1)
	go func() {
		serveErr <- srv.ListenAndServe()
	}()

	select {
	case err := <-serveErr:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case <-runCtx.Done():
	}
	stop() // restore normal signal handling while the bounded drain runs

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	shutdownErr := srv.Shutdown(shutdownCtx)
	if shutdownErr != nil {
		shutdownErr = errors.Join(shutdownErr, srv.Close())
	}

	err := <-serveErr
	if errors.Is(err, http.ErrServerClosed) {
		err = nil
	}
	return errors.Join(shutdownErr, err)
}
```

`Server.Shutdown` closes listeners, closes idle connections, and waits for
active HTTP connections to become idle. It does not wait for hijacked
connections such as WebSockets. Track those separately, signal their protocol
shutdown from `RegisterOnShutdown`, and wait for their owners within the same
shutdown budget. Stop accepting work first, and keep dependencies available
until admitted work has drained.
