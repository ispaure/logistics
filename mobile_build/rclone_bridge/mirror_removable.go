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
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/fserrors"
	"github.com/rclone/rclone/lib/file"
)

// Android mounts public FAT and exFAT volumes under /storage/<FAT volume ID>.
// Internal emulated storage and other platforms keep their usual sync policy.
func androidRemovablePath(platform, localPath string) bool {
	mount, found := strings.CutPrefix(localPath, "/storage/")
	if platform != "android" || !found {
		return false
	}
	volume, _, _ := strings.Cut(mount, "/")
	return len(volume) == 9 && volume[4] == '-' &&
		strings.Trim(strings.ToLower(volume[:4]+volume[5:]), "0123456789abcdef") == ""
}

func diskFull(err error) bool {
	return errors.Is(err, syscall.ENOSPC) || errors.Is(err, file.ErrDiskFull)
}

const removablePullHeadroom int64 = 16 * 1024 * 1024

func configureRemovablePull(config *fs.ConfigInfo, readable, writing bool) {
	if readable {
		// The Boox exposes some odd-second Dropbox mtimes rounded down by one
		// second. Rclone compares strictly inside its modify window.
		config.ModifyWindow = max(config.ModifyWindow, fs.Duration(time.Second+time.Nanosecond))
	}
	if writing {
		config.MultiThreadStreams = 0
		config.Inplace = false
	}
}

// rclone writes a replacement next to its old file. Check space immediately
// before staging it and reserve space against the other concurrent writers.
type removablePullFS struct {
	fs.Fs
	features  fs.Features
	mu        sync.Mutex
	journal   func() (string, error)
	changed   chan struct{}
	reserved  int64
	writers   int
	exclusive bool
	stages    map[string]func()
}

func newRemovablePullFS(local fs.Fs) *removablePullFS {
	destination := &removablePullFS{Fs: local, features: *local.Features(), changed: make(chan struct{}), stages: make(map[string]func())}
	destination.journal = sync.OnceValues(func() (string, error) { return sdRecoveryDirectory(sdReplacementRoot(local.Root())) })
	// Route every ordinary file through Put or PutStream instead of a clone
	// or an alternate segmented writer.
	destination.features.Copy = nil
	destination.features.OpenWriterAt = nil
	destination.features.OpenChunkWriter = nil
	if move := destination.features.Move; move != nil {
		destination.features.Move = func(ctx context.Context, src fs.Object, remote string) (fs.Object, error) {
			if staged, ok := src.(*removableStagedObject); ok {
				obj, err := destination.publish(ctx, staged.Object, remote)
				if err == nil {
					staged.release()
				}
				if err != nil && !errors.Is(err, context.Canceled) {
					return obj, fserrors.FatalError(fmt.Errorf("publishing SD replacement %s: %w", remote, destination.writeError(err)))
				}
				return obj, err
			}
			if direct, ok := src.(*removableDirectObject); ok {
				src = direct.Object
			}
			return move(ctx, src, remote)
		}
	}
	if putStream := destination.features.PutStream; putStream != nil {
		destination.features.PutStream = func(ctx context.Context, in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) (fs.Object, error) {
			return destination.put(ctx, putStream, in, src, opts...)
		}
	}
	return destination
}

func (f *removablePullFS) Features() *fs.Features {
	return &f.features
}

func (f *removablePullFS) freeSpace(ctx context.Context) (int64, error) {
	usage, err := f.features.About(ctx)
	if err != nil {
		return 0, fserrors.FatalError(fmt.Errorf("checking free space on SD card: %w", err))
	}
	if usage == nil || usage.Free == nil {
		return 0, fserrors.FatalError(errors.New("could not determine free space on SD card"))
	}
	return *usage.Free, nil
}

func (f *removablePullFS) reserve(ctx context.Context, size int64, stage string) (func(), error) {
	amount := max(size, 0)
	for {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		f.mu.Lock()
		// Rclone can retry the same partial after a source close fails.
		if release := f.stages[stage]; release != nil {
			f.mu.Unlock()
			return release, nil
		}
		if !f.exclusive && (size >= 0 || f.writers == 0) {
			free, err := f.freeSpace(ctx)
			if err != nil {
				f.mu.Unlock()
				return nil, err
			}
			if free >= removablePullHeadroom && f.reserved <= free-removablePullHeadroom &&
				amount <= free-removablePullHeadroom-f.reserved {
				f.reserved += amount
				f.exclusive = size < 0
				f.writers++
				release := sync.OnceFunc(func() {
					f.mu.Lock()
					f.reserved -= amount
					f.exclusive = false
					f.writers--
					delete(f.stages, stage)
					close(f.changed)
					f.changed = make(chan struct{})
					f.mu.Unlock()
				})
				if stage != "" {
					f.stages[stage] = release
				}
				f.mu.Unlock()
				return release, nil
			}
			if f.writers == 0 {
				f.mu.Unlock()
				return nil, fserrors.FatalError(fmt.Errorf(
					"insufficient free space on SD card to stage the next file safely (%s available)", fs.SizeSuffix(free)))
			}
		}
		// A replacement may free its old file when its staged copy is published.
		changed := f.changed
		f.mu.Unlock()
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-changed:
		}
	}
}

func (f *removablePullFS) Put(ctx context.Context, in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) (fs.Object, error) {
	return f.put(ctx, f.Fs.Put, in, src, opts...)
}

func (f *removablePullFS) List(ctx context.Context, dir string) (fs.DirEntries, error) {
	entries, err := f.Fs.List(ctx, dir)
	for i, entry := range entries {
		if obj, ok := entry.(fs.Object); ok && strings.HasSuffix(entry.Remote(), fs.LinkSuffix) {
			entries[i] = &removableDirectObject{Object: obj, destination: f}
		}
	}
	return entries, err
}

func (f *removablePullFS) NewObject(ctx context.Context, remote string) (fs.Object, error) {
	f.mu.Lock()
	release := f.stages[remote]
	f.mu.Unlock()
	obj, err := f.Fs.NewObject(ctx, remote)
	if release != nil {
		// Failed-copy cleanup opens its own handle before removing the partial.
		if err != nil || obj == nil {
			release()
		} else {
			obj = &removableStagedObject{Object: obj, release: release}
		}
	} else if err == nil && obj != nil && strings.HasSuffix(remote, fs.LinkSuffix) {
		obj = &removableDirectObject{Object: obj, destination: f}
	}
	return obj, err
}

func (f *removablePullFS) put(ctx context.Context, put func(context.Context, io.Reader, fs.ObjectInfo, ...fs.OpenOption) (fs.Object, error),
	in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) (fs.Object, error) {
	stage := ""
	if f.stagedName(ctx, src.Remote()) {
		stage = src.Remote()
	}
	release, err := f.reserve(ctx, src.Size(), stage)
	if err != nil {
		return nil, err
	}
	obj, err := put(ctx, in, src, opts...)
	if err == nil && obj != nil && stage != "" {
		return &removableStagedObject{Object: obj, release: release}, nil
	}
	release()
	return obj, f.writeError(err)
}

func (f *removablePullFS) stagedName(ctx context.Context, remote string) bool {
	config := fs.GetConfig(ctx)
	if config.Inplace || f.features.Move == nil || !f.features.PartialUploads {
		return false
	}
	return isRemovablePartial(remote, config.PartialSuffix)
}

func isRemovablePartial(remote, suffix string) bool {
	name, ok := strings.CutSuffix(remote, suffix)
	return ok && len(name) >= 9 && name[len(name)-9] == '.' &&
		strings.Trim(name[len(name)-8:], "0123456789abcdef") == ""
}

type removableStagedObject struct {
	fs.Object
	release func()
}

func (o *removableStagedObject) Remove(ctx context.Context) error {
	defer o.release()
	return o.Object.Remove(ctx)
}

// Rclone treats its special link suffix as an in-place copy even without
// --inplace. Account for an existing object explicitly on an SD destination.
type removableDirectObject struct {
	fs.Object
	destination *removablePullFS
}

func (o *removableDirectObject) Update(ctx context.Context, in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) error {
	release, err := o.destination.reserve(ctx, src.Size(), "")
	if err != nil {
		return err
	}
	defer release()
	return o.destination.writeError(o.Object.Update(ctx, in, src, opts...))
}

func (f *removablePullFS) writeError(err error) error {
	if diskFull(err) {
		return fserrors.FatalError(fmt.Errorf("SD card ran out of space: %w", err))
	}
	if errors.Is(err, syscall.EIO) || errors.Is(err, syscall.ENODEV) ||
		errors.Is(err, syscall.EROFS) || errors.Is(err, syscall.ETIMEDOUT) {
		// Put also returns errors from the source reader. Only stop for a
		// storage error whose path belongs to this SD destination.
		var pathErr *os.PathError
		var linkErr *os.LinkError
		var path string
		if errors.As(err, &pathErr) {
			path = pathErr.Path
		} else if errors.As(err, &linkErr) {
			path = linkErr.New
		}
		if relative, relErr := filepath.Rel(f.Root(), path); relErr == nil && filepath.IsLocal(relative) {
			return fserrors.FatalError(fmt.Errorf("SD card I/O failed. Check the card before retrying: %w", err))
		}
	}
	return err
}
