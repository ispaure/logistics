// TEST_STAGE = TestStage.REGRESSION

// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/hash"
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

type hashlessInfo struct{ fs.Info }

func (hashlessInfo) Hashes() hash.Set { return hash.NewHashSet() }

type hashlessObject struct{ fs.Object }

func (o hashlessObject) Fs() fs.Info { return hashlessInfo{o.Object.Fs()} }

func TestRemovablePullComparesSameSizeWithDifferentTimes(t *testing.T) {
	ctx := operations.WithEqualFn(context.Background(), sameRemovablePullFile)
	sourceDir, destinationDir := canonicalTestDir(t), canonicalTestDir(t)
	dstTime := time.Unix(1_700_000_000, 0)
	srcTime := dstTime.Add(time.Hour)
	for _, tc := range []struct {
		name, source, destination string
		wantTransfer              bool
	}{
		{"equal.cbz", "same comic", "same comic", false},
		{"different.cbz", "new comic!", "old comic!", true},
	} {
		seedRemovableTestFile(t, sourceDir, tc.name, tc.source, srcTime)
		seedRemovableTestFile(t, destinationDir, tc.name, tc.destination, dstTime)
		src := openRemovableTestObject(t, ctx, sourceDir, tc.name)
		dst := openRemovableTestObject(t, ctx, destinationDir, tc.name)
		if got := operations.NeedTransfer(ctx, dst, hashlessObject{src}); got != tc.wantTransfer {
			t.Fatalf("%s: NeedTransfer = %t, want %t", tc.name, got, tc.wantTransfer)
		}
		if !tc.wantTransfer && !dst.ModTime(ctx).Equal(srcTime) {
			t.Fatal("verified equal file did not adopt the source timestamp")
		}
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

func openRemovableTestObject(t *testing.T, ctx context.Context, root, name string) fs.Object {
	t.Helper()
	f, err := fs.NewFs(ctx, root)
	if err != nil {
		t.Fatal(err)
	}
	o, err := f.NewObject(ctx, name)
	if err != nil {
		t.Fatal(err)
	}
	return o
}
