package main

import (
	"context"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
)

// Match the CLI command retry policy using this operation's stats group, without
// invoking cmd.Run (which owns process signals/exit and global progress). Retry
// waits remain cancellable so a user never waits out a server's Retry-After.
func syncWithRetries(ctx context.Context, run string, stats *accounting.StatsInfo, work func() error) error {
	config := fs.GetConfig(ctx)
	maximum := max(1, config.Retries)
	var err error
	for attempt := 1; attempt <= maximum; attempt++ {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		mirrorAttempt(run, attempt, maximum, false)
		err = fs.CountError(ctx, work())
		if err == nil {
			err = stats.GetLastError()
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if !stats.Errored() || stats.HadFatalError() || !stats.HadRetryError() || attempt == maximum {
			return err
		}
		delay := max(time.Duration(0), time.Until(stats.RetryAfter())) + time.Duration(config.RetriesInterval)
		mirrorAttempt(run, attempt+1, maximum, true)
		timer := time.NewTimer(delay)
		select {
		case <-ctx.Done():
			timer.Stop()
			return ctx.Err()
		case <-timer.C:
		}
		stats.ResetErrors()
	}
	return err
}

func mirrorAttempt(run string, attempt, maximum int, retrying bool) {
	mirrorProgressState.Lock()
	defer mirrorProgressState.Unlock()
	if mirrorProgressState.Run == run {
		mirrorProgressState.Attempt, mirrorProgressState.MaxAttempts = attempt, maximum
		mirrorProgressState.Retrying = retrying
	}
}
