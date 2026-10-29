// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"testing"
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
