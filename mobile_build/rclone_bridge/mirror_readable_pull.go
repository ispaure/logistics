// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/fserrors"
	"github.com/rclone/rclone/lib/encoder"
)

// Use rclone's own directory listing. Check the paths it touches, including
// writes where a skipped link could otherwise be mistaken for a missing file.
type readablePullFS struct {
	fs.Fs
	features    fs.Features
	missingRoot bool // A read-only preview can target a directory not yet created.
}

func newReadablePullFS(local fs.Fs, missingRoot bool) *readablePullFS {
	pull := &readablePullFS{Fs: local, features: *local.Features(), missingRoot: missingRoot}
	// Local server-side Copy is unnecessary for cloud Pull. Keep Move for
	// publishing finished partial files and for rclone's rename tracking.
	pull.features.Copy = nil
	pull.features.DirMove = nil
	if move := pull.features.Move; move != nil {
		pull.features.Move = func(ctx context.Context, src fs.Object, remote string) (fs.Object, error) {
			if err := pull.checkPath(remote); err != nil {
				return nil, err
			}
			return move(ctx, src, remote)
		}
	}
	if mkdir := pull.features.MkdirMetadata; mkdir != nil {
		pull.features.MkdirMetadata = func(ctx context.Context, dir string, meta fs.Metadata) (fs.Directory, error) {
			if err := pull.checkPath(dir); err != nil {
				return nil, err
			}
			return mkdir(ctx, dir, meta)
		}
	}
	if setModTime := pull.features.DirSetModTime; setModTime != nil {
		pull.features.DirSetModTime = func(ctx context.Context, dir string, stamp time.Time) error {
			if err := pull.checkPath(dir); err != nil {
				return err
			}
			return setModTime(ctx, dir, stamp)
		}
	}
	if writer := pull.features.OpenWriterAt; writer != nil {
		pull.features.OpenWriterAt = func(ctx context.Context, remote string, size int64) (fs.WriterAtCloser, error) {
			if err := pull.checkPath(remote); err != nil {
				return nil, err
			}
			return writer(ctx, remote, size)
		}
	}
	if pull.features.PutStream != nil {
		pull.features.PutStream = pull.Put
	}
	return pull
}

func (f *readablePullFS) Features() *fs.Features { return &f.features }

func (f *readablePullFS) checkPath(remote string) error {
	root := f.Root()
	name := filepath.FromSlash(encoder.OS.FromStandardPath(remote))
	if name != "" && !filepath.IsLocal(name) {
		return fserrors.FatalError(errors.New("pull path escaped local storage"))
	}
	for target := filepath.Join(root, name); ; target = filepath.Dir(target) {
		info, err := os.Lstat(target)
		switch {
		case target == root && os.IsNotExist(err) && f.missingRoot:
			return nil
		case os.IsNotExist(err) && target != root:
			continue
		case err != nil:
			return fserrors.FatalError(fmt.Errorf("checking pull destination: %w", err))
		case target == root && !info.IsDir():
			return fserrors.FatalError(errors.New("pull destination must be an unlinked directory"))
		case !info.IsDir() && !info.Mode().IsRegular():
			return fserrors.FatalError(fmt.Errorf("linked or unsupported pull destination: %s", remote))
		case target == root:
			return nil
		}
	}
}

func (f *readablePullFS) List(ctx context.Context, dir string) (fs.DirEntries, error) {
	if err := f.checkPath(dir); err != nil {
		return nil, err
	}
	return f.Fs.List(ctx, dir)
}

func (f *readablePullFS) NewObject(ctx context.Context, remote string) (fs.Object, error) {
	if err := f.checkPath(remote); err != nil {
		return nil, err
	}
	return f.Fs.NewObject(ctx, remote)
}

func (f *readablePullFS) Put(ctx context.Context, in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) (fs.Object, error) {
	if err := f.checkPath(src.Remote()); err != nil {
		return nil, err
	}
	return f.Fs.Put(ctx, in, src, opts...)
}

func (f *readablePullFS) Mkdir(ctx context.Context, dir string) error {
	if err := f.checkPath(dir); err != nil {
		return err
	}
	return f.Fs.Mkdir(ctx, dir)
}

func (f *readablePullFS) Rmdir(ctx context.Context, dir string) error {
	if err := f.checkPath(dir); err != nil {
		return err
	}
	return f.Fs.Rmdir(ctx, dir)
}
