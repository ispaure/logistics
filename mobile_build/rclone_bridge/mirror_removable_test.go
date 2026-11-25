// TEST_STAGE = TestStage.REGRESSION

// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/fserrors"
	"github.com/rclone/rclone/fs/hash"
	"github.com/rclone/rclone/fs/object"
	"github.com/rclone/rclone/fs/operations"
	rclonesync "github.com/rclone/rclone/fs/sync"
)

func TestAndroidRemovablePullPath(t *testing.T) {
	for _, test := range []struct {
		platform, path string
		want           bool
	}{
		{"android", "/storage/6A9D-8789/Logistics/Rclone Copies/Comics", true},
		{"android", "/storage/aaaa-bb00/Logistics", true},
		{"android", "/storage/emulated/0/Logistics", false},
		{"android", "/storage/self/primary", false},
		{"android", "/storage/wxyz-1234/Logistics", false},
		{"darwin", "/storage/6A9D-8789/Logistics", false},
	} {
		if got := androidRemovablePath(test.platform, test.path); got != test.want {
			t.Errorf("%s %q: got %t, want %t", test.platform, test.path, got, test.want)
		}
	}
}

func TestRemovablePullTreatsDestinationIOErrorsAsFatal(t *testing.T) {
	root := canonicalTestDir(t)
	local, err := fs.NewFs(context.Background(), root)
	if err != nil {
		t.Fatal(err)
	}
	destination := newRemovablePullFS(local)
	target := filepath.Join(root, "comic.cbz.partial")
	for _, test := range []struct {
		failure error
		fatal   bool
	}{
		{&os.PathError{Op: "write", Path: target, Err: syscall.EIO}, true},
		{&os.PathError{Op: "open", Path: target, Err: syscall.EROFS}, true},
		{&os.LinkError{Op: "rename", Old: target, New: filepath.Join(root, "comic.cbz"), Err: syscall.ETIMEDOUT}, true},
		{&os.PathError{Op: "read", Path: root + "-other/comic.cbz", Err: syscall.EIO}, false},
		{&os.PathError{Op: "open", Path: target, Err: syscall.EACCES}, false},
		{syscall.ETIMEDOUT, false},
	} {
		err := destination.writeError(fmt.Errorf("copy: %w", test.failure))
		if fserrors.IsFatalError(err) != test.fatal || !errors.Is(err, test.failure) {
			t.Errorf("%v: expected fatal=%t, got %v", test.failure, test.fatal, err)
		}
	}
}

func TestRemovableReplacementRecoversInterruptedPublication(t *testing.T) {
	ctx := context.Background()
	for _, phase := range []string{"prepared", "old-moved", "new-moved", "committed", "racing-target"} {
		t.Run(phase, func(t *testing.T) {
			root := canonicalTestDir(t)
			target, partial := "a.cbz", "a.cbz.1234abcd.partial"
			previous, next := "old archive", "verified replacement"
			stamp := time.Unix(1_700_000_000, 0)
			seedRemovableTestFile(t, root, target, previous, stamp)
			seedRemovableTestFile(t, root, partial, next, stamp.Add(time.Hour))
			info, err := os.Stat(filepath.Join(root, partial))
			if err != nil {
				t.Fatal(err)
			}
			journal, err := sdRecoveryDirectory(root)
			if err != nil {
				t.Fatal(err)
			}
			txn, err := os.MkdirTemp(journal, "replace-")
			if err != nil {
				t.Fatal(err)
			}
			data, _ := json.Marshal(sdReplacement{Target: target, Partial: partial, Size: info.Size(), Mtime: info.ModTime().UnixNano()})
			must := func(err error) {
				t.Helper()
				if err != nil {
					t.Fatal(err)
				}
			}
			must(sdWriteMarker(filepath.Join(txn, "record.json"), data))
			if phase != "prepared" {
				must(sdRenameVacant(filepath.Join(root, target), filepath.Join(txn, "old")))
			}
			if phase == "new-moved" || phase == "committed" {
				must(sdRenameVacant(filepath.Join(root, partial), filepath.Join(root, target)))
			}
			if phase == "committed" {
				must(sdWriteMarker(filepath.Join(txn, "committed"), nil))
			}
			if phase == "racing-target" {
				seedRemovableTestFile(t, root, target, "external file", stamp)
				if err := recoverSDVolume(ctx, root); err == nil {
					t.Fatal("recovery accepted a changed destination")
				}
				data, err := os.ReadFile(filepath.Join(txn, "old"))
				if string(data) != previous || err != nil {
					t.Fatalf("recovery lost the previous file: %q %v", data, err)
				}
				return
			}
			must(recoverSDVolume(ctx, root))
			must(recoverSDVolume(ctx, root))
			want := previous
			if phase == "committed" {
				want = next
			}
			data, err = os.ReadFile(filepath.Join(root, target))
			if string(data) != want || err != nil {
				t.Fatalf("recovery left %q, want %q: %v", data, want, err)
			}
		})
	}
}

func TestRemovablePullStopsBeforeStagingWhenSpaceIsLow(t *testing.T) {
	ctx, config := fs.AddConfig(context.Background())
	config.Transfers = 1
	config.MultiThreadStreams = 0
	ctx = accounting.WithStatsGroup(ctx, t.Name())
	stats := accounting.Stats(ctx)
	defer stats.ResetCounters()
	srcDir, dstDir := canonicalTestDir(t), canonicalTestDir(t)
	oldTime := time.Unix(1_700_000_000, 0)
	seedRemovableTestFile(t, srcDir, "comic.cbz", "replacement", oldTime.Add(time.Hour))
	seedRemovableTestFile(t, dstDir, "comic.cbz", "old comic", oldTime)
	seedRemovableTestFile(t, dstDir, "old.cbz", "existing", oldTime)
	src, err := fs.NewFs(ctx, srcDir)
	if err != nil {
		t.Fatal(err)
	}
	local, err := fs.NewFs(ctx, dstDir)
	if err != nil {
		t.Fatal(err)
	}
	dst := newRemovablePullFS(local)
	if err := dst.recover(ctx); err != nil {
		t.Fatal(err)
	}
	dst.Features().About = func(context.Context) (*fs.Usage, error) {
		return &fs.Usage{Free: fs.NewUsageValue(removablePullHeadroom + 4)}, nil
	}
	err = syncWithRetries(ctx, t.Name(), stats, func() error {
		return rclonesync.Sync(ctx, dst, src, true)
	})
	if err == nil || !strings.Contains(err.Error(), "insufficient free space on SD card") {
		t.Fatalf("expected a staging-space error, got %v", err)
	}
	for name, want := range map[string]string{"comic.cbz": "old comic", "old.cbz": "existing"} {
		data, err := os.ReadFile(filepath.Join(dstDir, name))
		if string(data) != want || err != nil {
			t.Fatalf("%s changed on low-space failure: %q %v", name, data, err)
		}
	}
	files, err := os.ReadDir(dstDir)
	if err != nil || len(files) != 2 {
		t.Fatalf("staging left entries: %v %v", files, err)
	}
}

type blockedRemovableWrites struct {
	fs.Fs
	started chan string
	write   chan struct{}
}

func (f blockedRemovableWrites) Put(ctx context.Context, in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) (fs.Object, error) {
	f.started <- src.Remote()
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	case <-f.write:
		return f.Fs.Put(ctx, in, src, opts...)
	}
}

func TestRemovablePullStagesTenFilesConcurrentlyWithRoom(t *testing.T) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ctx, config := fs.AddConfig(ctx)
	config.Transfers = mirrorTransferConcurrency
	configureRemovablePull(config, true, true)
	srcDir, dstDir := canonicalTestDir(t), canonicalTestDir(t)
	for i := range mirrorTransferConcurrency {
		seedRemovableTestFile(t, srcDir, fmt.Sprintf("comic-%d.cbz", i), "comic", time.Unix(1_700_000_000, 0))
	}
	src, err := fs.NewFs(ctx, srcDir)
	if err != nil {
		t.Fatal(err)
	}
	local, err := fs.NewFs(ctx, dstDir)
	if err != nil {
		t.Fatal(err)
	}
	blocked := blockedRemovableWrites{Fs: local, started: make(chan string, mirrorTransferConcurrency), write: make(chan struct{})}
	dst := newRemovablePullFS(blocked)
	dst.Features().About = func(context.Context) (*fs.Usage, error) {
		return &fs.Usage{Free: fs.NewUsageValue(removablePullHeadroom + 50)}, nil
	}
	done := make(chan error, 1)
	go func() { done <- rclonesync.Sync(ctx, dst, src, true) }()
	for i := range mirrorTransferConcurrency {
		select {
		case <-blocked.started:
		case err := <-done:
			t.Fatalf("sync stopped after %d writers: %v", i, err)
		case <-ctx.Done():
			t.Fatalf("only %d writers were admitted", i)
		}
	}
	close(blocked.write)
	if err := <-done; err != nil {
		t.Fatal(err)
	}
	if dst.writers != 0 || dst.reserved != 0 {
		t.Fatalf("sync left %d writers and %d reserved bytes", dst.writers, dst.reserved)
	}
}

func TestRemovableStagesKeepReserveUntilPublishedOrRemoved(t *testing.T) {
	ctx, finish := context.WithTimeout(context.Background(), 3*time.Second)
	defer finish()
	local, err := fs.NewFs(ctx, canonicalTestDir(t))
	if err != nil {
		t.Fatal(err)
	}
	for _, publish := range []bool{true, false} {
		dst := newRemovablePullFS(local)
		dst.Features().About = func(context.Context) (*fs.Usage, error) {
			return &fs.Usage{Free: fs.NewUsageValue(removablePullHeadroom + 12)}, nil
		}
		data := "8 bytes!"
		info := object.NewStaticObjectInfo("comic.cbz.1234abcd.partial", time.Now(), int64(len(data)), true, nil, dst)
		staged, err := dst.Put(ctx, strings.NewReader(data), info)
		if err != nil {
			t.Fatal(err)
		}
		// A retry may reopen the same partial after the source failed to close.
		staged, err = dst.Put(ctx, strings.NewReader(data), info)
		if err != nil || dst.writers != 1 || dst.reserved != int64(len(data)) {
			t.Fatalf("retry did not reuse the original reserve: %v, %d writers, %d bytes", err, dst.writers, dst.reserved)
		}
		wait, cancel := context.WithTimeout(ctx, 30*time.Millisecond)
		_, err = dst.reserve(wait, int64(len(data)), "")
		cancel()
		if !errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("second writer should wait while first is staged, got %v", err)
		}
		if publish {
			if _, err := dst.Features().Move(ctx, staged, "comic.cbz"); err != nil {
				t.Fatal(err)
			}
		} else {
			failed, err := dst.NewObject(ctx, staged.Remote())
			if err != nil {
				t.Fatal(err)
			}
			if err := failed.Remove(ctx); err != nil {
				t.Fatal(err)
			}
		}
		release, err := dst.reserve(ctx, int64(len(data)), "")
		if err != nil {
			t.Fatal(err)
		}
		release()
	}
}

type hashlessDropboxFixture struct{ fs.Fs }

func (hashlessDropboxFixture) Hashes() hash.Set         { return 0 }
func (hashlessDropboxFixture) Precision() time.Duration { return time.Second }

func TestReadableRemovablePullAcceptsOnlyOneSecondOfRounding(t *testing.T) {
	ctx, config := fs.AddConfig(context.Background())
	root := canonicalTestDir(t)
	stamp := time.Unix(1_700_000_000, 0)
	seedRemovableTestFile(t, root, "comic.cbz", "comic", stamp)
	local, err := fs.NewFs(ctx, root)
	if err != nil {
		t.Fatal(err)
	}
	dst, err := local.NewObject(ctx, "comic.cbz")
	if err != nil {
		t.Fatal(err)
	}
	source := func(delta time.Duration, size int64) fs.ObjectInfo {
		return object.NewStaticObjectInfo("comic.cbz", stamp.Add(delta), size, true, nil, hashlessDropboxFixture{local})
	}
	if operations.Equal(ctx, source(time.Second, 5), dst) {
		t.Fatal("baseline unexpectedly skips a full-second mismatch")
	}
	configureRemovablePull(config, true, false)
	if !operations.Equal(ctx, source(time.Second, 5), dst) {
		t.Fatal("rounded timestamp still schedules a replacement")
	}
	if operations.Equal(ctx, source(time.Second+time.Nanosecond, 5), dst) || operations.Equal(ctx, source(time.Second, 6), dst) {
		t.Fatal("a larger timestamp or size difference was skipped")
	}
}

func seedRemovableTestFile(t *testing.T, dir, name, contents string, stamp time.Time) {
	t.Helper()
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte(contents), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Chtimes(p, stamp, stamp); err != nil {
		t.Fatal(err)
	}
}
