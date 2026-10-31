package main

import (
	"context"
	"errors"
	"os"
	"path"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/config/configmap"
	"github.com/rclone/rclone/fs/filter"
	"github.com/rclone/rclone/fs/operations"
	rclonesync "github.com/rclone/rclone/fs/sync"
)

// Downloads sync only into a new, empty staging directory. The Python owner
// publishes the selected item exclusively, so unrelated local files are never
// in the destination of rclone's destructive Sync operation.
func downloadSync(ctx context.Context, request bridgeRequest) (int64, error) {
	if request.Push || !validPath(request.Path) || request.Path == "" ||
		len(request.Run) != 32 || strings.Trim(request.Run, "0123456789abcdef") != "" {
		return 0, errors.New("invalid single-item download")
	}
	identity, err := connectionIdentity(request.Remote)
	if err != nil || identity != request.Identity {
		return 0, errors.New("source connection changed")
	}
	localPath := request.LocalPath
	resolved, err := filepath.EvalSymlinks(localPath)
	if err != nil || !filepath.IsAbs(localPath) || resolved != localPath {
		return 0, errors.New("download requires an independent local staging folder")
	}
	entries, err := os.ReadDir(localPath)
	if err != nil || len(entries) != 0 {
		return 0, errors.New("download staging folder must be empty")
	}
	ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
	ctx, config := fs.AddConfig(ctx)
	config.BackupDir, config.Suffix = "", ""
	config.DryRun, config.TrackRenames = false, false
	config.Transfers = 10
	config.MaxStatsGroups = 8
	if request.BWLimit < 0 {
		return 0, errors.New("invalid download bandwidth limit")
	}
	if request.BWLimit > 0 {
		if err := config.BwLimit.Set(strconv.Itoa(request.BWLimit) + "M"); err != nil {
			return 0, err
		}
		accounting.TokenBucket.StartTokenBucket(ctx)
		defer accounting.TokenBucket.SetBwLimit(fs.BwPair{})
	}
	rules, err := filter.NewFilter(nil)
	if err != nil {
		return 0, err
	}
	ctx = filter.ReplaceConfig(ctx, rules)
	ctx = accounting.WithStatsGroup(ctx, request.Run)
	stats := accounting.Stats(ctx)
	defer stats.ResetCounters()
	remoteRoot := request.Path
	if !request.Directory {
		remoteRoot = path.Dir(remoteRoot)
	}
	if remoteRoot == "." {
		remoteRoot = ""
	}
	source, err := fs.NewFs(ctx, request.Remote+":"+remoteRoot)
	if err != nil {
		return 0, err
	}
	var destination fs.Fs
	if request.DestinationRemote == "" {
		destination, err = fs.NewFs(ctx, localPath)
	} else {
		_, _, _, identity, e := cryptConnection(request.DestinationRemote)
		if e != nil || identity != request.DestinationIdentity {
			return 0, errors.New("destination crypt changed or is locked")
		}
		info, e := fs.Find("crypt")
		if e != nil {
			return 0, e
		}
		values := configmap.Simple{"remote": localPath}
		connection := store.connection(request.DestinationRemote)
		for _, option := range info.Options {
			if option.Name != "remote" {
				if value, ok := connection.Get(option.Name); ok {
					values[option.Name] = value
				}
			}
		}
		options := fs.ConfigMap(info.Prefix, info.Options, "", nil)
		options.ClearGetters(configmap.PriorityNormal)
		options.AddGetter(values, configmap.PriorityNormal)
		destination, err = crypt.NewFs(ctx, "download-local-crypt", "", options)
	}
	if err != nil {
		return 0, err
	}
	mirrorPhase(request.Run, "Discovering / checking files", 0)
	done, stopped := make(chan struct{}), make(chan struct{})
	go func() {
		defer close(stopped)
		ticker := time.NewTicker(200 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				mirrorSyncStats(request.Run, stats)
			}
		}
	}()
	defer func() { close(done); <-stopped; mirrorSyncStats(request.Run, stats) }()
	attempt := func() error { return rclonesync.Sync(ctx, destination, source, true) }
	if !request.Directory {
		name := path.Base(request.Path)
		attempt = func() error { return operations.CopyFile(ctx, destination, source, name, name) }
	}
	err = syncWithRetries(ctx, request.Run, stats, attempt)
	if err != nil {
		return 0, err
	}
	return stats.GetTransfers(), nil
}
