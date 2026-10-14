package main

import (
	"context"
	"errors"
	"os"
	"path"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/rclone/rclone/backend/local"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/rc"
	rclonesync "github.com/rclone/rclone/fs/sync"
)

// Run the same rclone Sync routine as the CLI, inside the app rather than a
// child process. Only admitted connections and a host-validated private folder
// are accepted. LocalCrypt selects its backing ciphertext scope; Local uses
// the crypt filesystem's logical names and automatic encryption/decryption.
func mirrorSync(ctx context.Context, name, p, identity, localPath, run string, push bool) (int64, error) {
	if len(run) != 32 || strings.Trim(run, "0123456789abcdef") != "" {
		return 0, errors.New("invalid sync transaction")
	}
	_, root, cipher, _, err := mirrorConnection(ctx, name, identity)
	if err != nil {
		return 0, err
	}
	if _, err = mirrorPlain(cipher, p, true); err != nil {
		return 0, err
	}
	if !filepath.IsAbs(localPath) || filepath.Clean(localPath) != localPath {
		return 0, errors.New("sync requires a private absolute directory")
	}
	resolved, err := filepath.EvalSymlinks(localPath)
	if err != nil || resolved != localPath {
		return 0, errors.New("linked sync storage is not supported")
	}
	count := 0
	err = filepath.WalkDir(localPath, func(p string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if ctx.Err() != nil {
			return ctx.Err()
		}
		count++
		if count > 10001 || entry.Type()&os.ModeSymlink != 0 {
			return errors.New("linked storage or sync entry limit exceeded")
		}
		return nil
	})
	if err != nil {
		return 0, err
	}
	remoteName := name
	remoteRoot := p
	if cipher != nil {
		_, backing, _, _, e := cryptConnection(name)
		if e != nil {
			return 0, e
		}
		remoteName = backing
		remoteRoot = path.Join(root, p)
	}
	if remoteRoot == "." {
		remoteRoot = ""
	}
	ctx, config := fs.AddConfig(ctx)
	config.BackupDir = ""
	config.Suffix = ""
	config.DryRun = false
	config.MaxStatsGroups = 8
	config.Transfers = 10
	ctx = accounting.WithStatsGroup(ctx, run)
	stats := accounting.Stats(ctx)
	defer stats.ResetCounters()
	online, err := fs.NewFs(ctx, remoteName+":"+remoteRoot)
	if err != nil {
		return 0, err
	}
	local, err := fs.NewFs(ctx, localPath)
	if err != nil {
		return 0, err
	}
	source, destination := online, local
	if push {
		source, destination = local, online
	}
	mirrorPhase(run, "Discovering / checking files", 0)
	done := make(chan struct{})
	stopped := make(chan struct{})
	defer func() {
		close(done)
		<-stopped
		mirrorSyncStats(run, stats)
	}()
	go func() {
		defer close(stopped)
		ticker := time.NewTicker(200 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				mirrorSyncStats(run, stats)
			}
		}
	}()
	if err = rclonesync.Sync(ctx, destination, source, true); err != nil {
		return 0, err
	}
	return stats.GetTransfers(), nil
}

func mirrorSyncStats(run string, stats *accounting.StatsInfo) {
	values, err := stats.RemoteStats(false)
	if err != nil {
		return
	}
	transfers, _ := values["transferring"].([]rc.Params)
	mirrorProgressState.Lock()
	defer mirrorProgressState.Unlock()
	if mirrorProgressState.Run != run {
		return
	}
	mirrorProgressState.Done = values["bytes"].(int64)
	mirrorProgressState.Total = values["totalBytes"].(int64)
	mirrorProgressState.Files = values["transfers"].(int64)
	mirrorProgressState.TotalFiles = values["totalTransfers"].(int64)
	mirrorProgressState.Checks = values["checks"].(int64)
	mirrorProgressState.Listed = values["listed"].(int64)
	mirrorProgressState.Active = int64(len(transfers))
	mirrorProgressState.Phase = "Discovering / checking files"
	if len(transfers) > 0 {
		mirrorProgressState.Phase = "Transferring"
	} else if mirrorProgressState.Files > 0 {
		mirrorProgressState.Phase = "Checking / finishing sync"
	}
}
