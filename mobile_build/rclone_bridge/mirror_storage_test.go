// TEST_STAGE = TestStage.REGRESSION

// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
)

func TestPullStorageScanAllowsRemovedDescendantButPushFails(t *testing.T) {
	for _, push := range []bool{false, true} {
		root := canonicalTestDir(t)
		child := filepath.Join(root, "nested")
		if err := os.Mkdir(child, 0700); err != nil {
			t.Fatal(err)
		}
		check := mirrorStorageCheck(context.Background(), root, false, push)
		err := filepath.WalkDir(root, func(p string, d os.DirEntry, err error) error {
			if p == child && err == nil {
				// Remove after discovery, before the real WalkDir reads it.
				if e := os.Remove(child); e != nil {
					t.Fatal(e)
				}
			}
			return check(p, d, err)
		})
		if push && !os.IsNotExist(err) || !push && err != nil {
			t.Fatalf("push=%t: %v", push, err)
		}
	}
}

func TestPullStorageScanRetriesExistingDirectoryAndChecksItsChildren(t *testing.T) {
	root := canonicalTestDir(t)
	info, err := os.Lstat(root)
	if err != nil {
		t.Fatal(err)
	}
	entry := fs.FileInfoToDirEntry(info)
	missing := &os.PathError{Op: "readdirent", Path: root, Err: os.ErrNotExist}
	check := mirrorStorageCheck(context.Background(), root, false, false)
	if err := check(root, entry, missing); err != filepath.SkipDir {
		t.Fatalf("transient readdirent was not recovered: %v", err)
	}
	// The retry is bounded; an existing unreadable folder is never skipped.
	if err := check(root, entry, missing); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("repeated read failure was hidden: %v", err)
	}
	if err := os.Symlink(root, filepath.Join(root, "linked")); err != nil {
		t.Fatal(err)
	}
	check = mirrorStorageCheck(context.Background(), root, false, false)
	if err := check(root, entry, missing); err == nil || err == filepath.SkipDir {
		t.Fatal("retry bypassed link validation")
	}
}

func TestPullStorageScanPreservesRootPermissionAndCancellationErrors(t *testing.T) {
	root := canonicalTestDir(t)
	check := mirrorStorageCheck(context.Background(), root, false, false)
	denied := &os.PathError{Op: "readdirent", Path: root, Err: os.ErrPermission}
	if err := check(root, nil, denied); !errors.Is(err, os.ErrPermission) {
		t.Fatal("permission error hidden", err)
	}
	if err := os.Remove(root); err != nil {
		t.Fatal(err)
	}
	missing := &os.PathError{Op: "readdirent", Path: root, Err: os.ErrNotExist}
	if err := check(root, nil, missing); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("missing storage root hidden", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := mirrorStorageCheck(ctx, root, false, false)(root, nil, missing); !errors.Is(err, context.Canceled) {
		t.Fatal("cancellation hidden", err)
	}
}

func TestReadablePullGuardsDestinationsWhileRcloneSyncs(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:readable-pull"), ""); err != nil {
		t.Fatal(err)
	}
	cloud, err := remote(ctx, "Cloud")
	if err != nil {
		t.Fatal(err)
	}
	identity, err := connectionIdentity("Cloud")
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ name, leaf, remote string }{
		{"normal", "comic.cbz", "comic.cbz"},
		{"linked file", "comic.rclonelink", "comic.rclonelink"},
		{"linked directory", "nested", "nested/comic.cbz"},
	} {
		t.Run(test.name, func(t *testing.T) {
			stamp := time.Unix(1_700_000_000, 0)
			dst, outside := canonicalTestDir(t), canonicalTestDir(t)
			seedRemovableTestFile(t, outside, "kept.cbz", "outside", stamp)
			target := filepath.Join(dst, test.leaf)
			switch test.name {
			case "normal":
				seedRemovableTestFile(t, dst, test.leaf, "old", stamp)
			case "linked file":
				if err := os.Symlink(filepath.Join(outside, "kept.cbz"), target); err != nil {
					t.Fatal(err)
				}
			case "linked directory":
				if err := os.Symlink(outside, target); err != nil {
					t.Fatal(err)
				}
			}
			prefix := "readable/" + strings.ReplaceAll(test.name, " ", "-")
			data := "replacement"
			info := object.NewStaticObjectInfo(prefix+"/"+test.remote, stamp.Add(time.Hour), int64(len(data)), true, nil, cloud)
			if _, err := cloud.Put(ctx, strings.NewReader(data), info); err != nil {
				t.Fatal(err)
			}
			run := strings.Repeat("d", 32)
			_, err := mirrorSync(ctx, "Cloud", prefix, identity, dst, run, false)
			if test.name == "normal" {
				if got, readErr := os.ReadFile(target); err != nil || readErr != nil || string(got) != data {
					t.Fatalf("ordinary replacement failed: %q, sync=%v, read=%v", got, err, readErr)
				}
				return
			}
			if err == nil || !strings.Contains(err.Error(), "linked or unsupported pull destination") {
				t.Fatalf("expected a linked destination error, got %v", err)
			}
			if info, err := os.Lstat(target); err != nil || info.Mode()&os.ModeSymlink == 0 {
				t.Fatalf("link was changed: %v", err)
			}
			if got, err := os.ReadFile(filepath.Join(outside, "kept.cbz")); err != nil || string(got) != "outside" {
				t.Fatalf("file outside the copy was changed: %q %v", got, err)
			}
			if children, err := os.ReadDir(outside); err != nil || len(children) != 1 {
				t.Fatalf("link led to writes outside the copy: %v %v", children, err)
			}
		})
	}
}
