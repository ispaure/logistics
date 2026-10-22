package main

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
)

// Pull's local tree is a destination, not a source snapshot. Android removable
// storage can invalidate a directory between listing it and reading its entries.
// Retry an existing directory once; skip a genuinely missing descendant only.
// Never turn loss of the root, permissions, or an unreadable existing tree into
// a successful scan. Push remains strict about its source.
func mirrorStorageCheck(ctx context.Context, root string, copyLinks, push bool) fs.WalkDirFunc {
	retried := map[string]bool{}
	var check fs.WalkDirFunc
	check = func(p string, entry os.DirEntry, walkErr error) error {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if walkErr != nil {
			if !push && os.IsNotExist(walkErr) {
				info, statErr := os.Lstat(p)
				if p != root && os.IsNotExist(statErr) {
					if entry != nil && entry.IsDir() {
						return filepath.SkipDir
					}
					return nil
				}
				if statErr == nil && info.IsDir() && !retried[p] {
					retried[p] = true
					if err := filepath.WalkDir(p, check); err != nil {
						return err
					}
					return filepath.SkipDir
				}
			}
			return walkErr
		}
		linked := entry.Type()&os.ModeSymlink != 0
		if linked && copyLinks {
			info, err := os.Stat(p)
			linked = err != nil || !info.Mode().IsRegular()
		}
		if linked {
			return errors.New("linked sync storage is not supported")
		}
		return nil
	}
	return check
}
