package main

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/fserrors"
)

func TestSyncRetriesMatchCLIAndReportRecovery(t *testing.T) {
	ctx, config := fs.AddConfig(context.Background())
	config.Retries = 3
	config.RetriesInterval = 0
	ctx = accounting.WithStatsGroup(ctx, t.Name())
	stats := accounting.Stats(ctx)
	defer stats.ResetCounters()
	mirrorPhase(t.Name(), "Transferring", 0)
	calls := 0
	err := syncWithRetries(ctx, t.Name(), stats, func() error {
		calls++
		if calls < 3 {
			return errors.New("temporary network failure")
		}
		return nil
	})
	if err != nil || calls != 3 || stats.Errored() {
		t.Fatal(err, calls, stats.GetLastError())
	}
	raw, _ := json.Marshal(map[string]string{"run": t.Name()})
	// The wire uses snake_case for the maximum count.
	var data map[string]any
	if err := json.Unmarshal([]byte(mirrorProgress(string(raw))), &data); err != nil {
		t.Fatal(err)
	}
	result := data["result"].(map[string]any)
	if result["attempt"] != float64(3) || result["max_attempts"] != float64(3) || result["retrying"] != false {
		t.Fatal(result)
	}
}

func TestSyncRetriesStopForFatalNonRetryAndExhaustion(t *testing.T) {
	for _, test := range []struct {
		name    string
		failure error
		calls   int
	}{
		{"fatal", fserrors.FatalError(errors.New("invalid configuration")), 1},
		{"non-retry", fserrors.NoRetryError(errors.New("permission denied")), 1},
		{"exhausted", errors.New("network failure"), 3},
	} {
		t.Run(test.name, func(t *testing.T) {
			ctx, config := fs.AddConfig(context.Background())
			config.Retries = 3
			config.RetriesInterval = 0
			ctx = accounting.WithStatsGroup(ctx, t.Name())
			stats := accounting.Stats(ctx)
			defer stats.ResetCounters()
			calls := 0
			err := syncWithRetries(ctx, t.Name(), stats, func() error { calls++; return test.failure })
			if err == nil || calls != test.calls {
				t.Fatal(err, calls)
			}
		})
	}
}

func TestSyncRetryAfterWaitIsCancellable(t *testing.T) {
	base, stop := context.WithCancel(context.Background())
	defer stop()
	ctx, config := fs.AddConfig(base)
	config.Retries = 3
	config.RetriesInterval = 0
	ctx = accounting.WithStatsGroup(ctx, t.Name())
	stats := accounting.Stats(ctx)
	defer stats.ResetCounters()
	started := make(chan struct{})
	done := make(chan error, 1)
	calls := 0
	go func() {
		done <- syncWithRetries(ctx, t.Name(), stats, func() error {
			calls++
			close(started)
			return fserrors.NewErrorRetryAfter(time.Hour)
		})
	}()
	<-started
	stop()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) || calls != 1 {
			t.Fatal(err, calls)
		}
	case <-time.After(time.Second):
		t.Fatal("Cancellation waited for Retry-After")
	}
}

func TestSyncDefaultsAndDeadlineMatchDesktop(t *testing.T) {
	config := fs.GetConfig(context.Background())
	if config.Retries != 3 || config.LowLevelRetries != 10 || config.ConnectTimeout != fs.Duration(time.Minute) || config.Timeout != fs.Duration(5*time.Minute) {
		t.Fatal("Embedded defaults diverge from rclone CLI", config.Retries, config.LowLevelRetries, config.ConnectTimeout, config.Timeout)
	}
	ctx, done := operation("mirror_sync")
	defer done()
	if _, deadline := ctx.Deadline(); deadline {
		t.Fatal("Sync has a fixed deadline")
	}
	cancel()
	if !errors.Is(ctx.Err(), context.Canceled) {
		t.Fatal("Sync cancellation lost")
	}
}

func TestReviewRetryReplacesFailedAttemptRowsAndRevisions(t *testing.T) {
	ctx, config := fs.AddConfig(context.Background())
	config.Retries = 3
	ctx = accounting.WithStatsGroup(ctx, t.Name())
	stats := accounting.Stats(ctx)
	defer stats.ResetCounters()
	c := &comparison{}
	calls := 0
	err := syncWithRetries(ctx, t.Name(), stats, c.attempt(func() error {
		calls++
		if len(c.changes) != 0 || len(c.revisions) != 0 {
			t.Fatal("retry retained prior attempt")
		}
		if calls == 1 {
			c.changes["stale.txt"], c.revisions["stale.txt"] = "delete", "old revision"
			return errors.New("temporary listing failure")
		}
		c.changes["current.txt"], c.revisions["current.txt"] = "add", "current revision"
		return nil
	}))
	if err != nil || calls != 2 {
		t.Fatal(err, calls)
	}
	expected := &comparison{changes: map[string]string{"current.txt": "add"}, revisions: map[string]string{"current.txt": "current revision"}}
	if c.snapshot()["fingerprint"] != expected.snapshot()["fingerprint"] {
		t.Fatal("failed attempt tainted final review")
	}
}

func TestReviewHasCancellableDesktopDeadlinePolicy(t *testing.T) {
	ctx, finish := operation("mirror_review")
	defer finish()
	if _, deadline := ctx.Deadline(); deadline {
		t.Fatal("Review has a fixed deadline")
	}
	cancel()
	if ctx.Err() == nil {
		t.Fatal("Review cancellation lost")
	}
}
