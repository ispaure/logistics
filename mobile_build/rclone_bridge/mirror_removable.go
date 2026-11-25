// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"strings"
	"syscall"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/fserrors"
	"github.com/rclone/rclone/fs/operations"
	"github.com/rclone/rclone/lib/file"
	"github.com/rclone/rclone/lib/readers"
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

// rclone writes a replacement next to its old file. Check space immediately
// before staging it, while the single writer can use an up-to-date free count.
type removablePullFS struct {
	fs.Fs
	features fs.Features
}

func newRemovablePullFS(local fs.Fs) *removablePullFS {
	destination := &removablePullFS{Fs: local, features: *local.Features()}
	// Route every ordinary file through Put or PutStream instead of a clone
	// or an alternate segmented writer.
	destination.features.Copy = nil
	destination.features.OpenWriterAt = nil
	if putStream := destination.features.PutStream; putStream != nil {
		destination.features.PutStream = func(ctx context.Context, in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) (fs.Object, error) {
			if err := destination.checkSpace(ctx, src.Size()); err != nil {
				return nil, err
			}
			obj, err := putStream(ctx, in, src, opts...)
			return obj, removablePullWriteError(err)
		}
	}
	return destination
}

func (f *removablePullFS) Features() *fs.Features {
	return &f.features
}

func (f *removablePullFS) checkSpace(ctx context.Context, size int64) error {
	usage, err := f.features.About(ctx)
	if err != nil {
		return fserrors.FatalError(fmt.Errorf("checking free space on SD card: %w", err))
	}
	if usage == nil || usage.Free == nil {
		return fserrors.FatalError(errors.New("could not determine free space on SD card"))
	}
	free := *usage.Free
	if free < removablePullHeadroom || max(size, 0) > free-removablePullHeadroom {
		return fserrors.FatalError(fmt.Errorf(
			"insufficient free space on SD card to stage the next file safely (%s available)",
			fs.SizeSuffix(free)))
	}
	return nil
}

func (f *removablePullFS) Put(ctx context.Context, in io.Reader, src fs.ObjectInfo, opts ...fs.OpenOption) (fs.Object, error) {
	if err := f.checkSpace(ctx, src.Size()); err != nil {
		return nil, err
	}
	obj, err := f.Fs.Put(ctx, in, src, opts...)
	return obj, removablePullWriteError(err)
}

func removablePullWriteError(err error) error {
	if diskFull(err) {
		return fserrors.FatalError(fmt.Errorf("SD card ran out of space: %w", err))
	}
	return err
}

// A timestamp mismatch on a provider such as SMB can force a full rewrite.
// For same-size files without a common provider checksum, compare the streams.
func sameRemovablePullFile(ctx context.Context, src fs.ObjectInfo, dst fs.Object) bool {
	source, ok := src.(fs.Object)
	if operations.Equal(ctx, src, dst) {
		return !ok || !operations.SameObject(source, dst)
	}
	size := src.Size()
	if !ok || size < 0 || size != dst.Size() || src.Fs().Hashes().Overlap(dst.Fs().Hashes()).Count() != 0 {
		return false
	}
	if !removablePullContentsMatch(ctx, source, dst, size) {
		return false
	}
	if !fs.GetConfig(ctx).NoUpdateModTime && ctx.Err() == nil {
		// Matching bytes do not need to be replaced even if the SD card cannot
		// represent the server's timestamp exactly.
		if err := dst.SetModTime(ctx, src.ModTime(ctx)); err != nil {
			fs.Debugf(dst, "Could not update timestamp after verifying file contents: %v", err)
		}
	}
	return true
}

func removablePullContentsMatch(ctx context.Context, src, dst fs.Object, size int64) bool {
	remote, err := operations.Open(ctx, src)
	if err != nil {
		return false
	}
	defer remote.Close()
	local, err := operations.Open(ctx, dst)
	if err != nil {
		return false
	}
	defer local.Close()
	counting := readers.NewCountingReader(pullNetworkReader{ctx: ctx, Reader: remote})
	same, err := operations.CheckEqualReaders(counting, local)
	return err == nil && same && counting.BytesRead() == uint64(size)
}

type pullNetworkReader struct {
	ctx context.Context
	io.Reader
}

func (r pullNetworkReader) Read(p []byte) (int, error) {
	if err := r.ctx.Err(); err != nil {
		return 0, err
	}
	n, err := r.Reader.Read(p)
	accounting.TokenBucket.LimitBandwidth(accounting.TokenBucketSlotAccounting, n)
	return n, err
}
