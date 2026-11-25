// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"

	rclone "github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/fserrors"
	"github.com/rclone/rclone/lib/encoder"
)

const removableRecoveryFolder = ".logistics-sd-recovery-v1"

// All replacements use the same lock and journal, including editor saves.
// This protects the checked-rename fallback on FAT drivers without renameat2.
var sdPublication sync.Mutex

func sdReplacementRoot(path string) string {
	if !androidRemovablePath(runtime.GOOS, path) {
		return path
	}
	parts := strings.Split(path, "/")
	if len(parts) >= 7 && parts[3] == "Android" && parts[4] == "data" && parts[6] == "files" {
		return strings.Join(parts[:7], "/") // App-specific removable storage has its own access boundary.
	}
	return strings.Join(parts[:3], "/")
}

// The old file lives on the same filesystem until the new name is durable.
// Recovery can roll back an uncommitted publication or finish committed cleanup.
type sdReplacement struct {
	Target  string `json:"target"`
	Partial string `json:"partial"`
	Size    int64  `json:"size"`
	Mtime   int64  `json:"mtime"`
}

func removableRelative(remote string) string {
	return filepath.FromSlash(encoder.OS.FromStandardPath(remote))
}

func (record sdReplacement) validate(ctx context.Context, root string) error {
	for _, name := range []string{record.Target, record.Partial} {
		if name == "." || !filepath.IsLocal(name) || name != filepath.Clean(name) {
			return errors.New("invalid SD replacement path")
		}
		for _, piece := range strings.Split(name, string(filepath.Separator)) {
			if strings.EqualFold(piece, removableRecoveryFolder) {
				return errors.New("replacement path enters the SD recovery folder")
			}
		}
	}
	if record.Size < 0 || record.Target == record.Partial || filepath.Dir(record.Target) != filepath.Dir(record.Partial) ||
		(!isRemovablePartial(record.Partial, rclone.GetConfig(ctx).PartialSuffix) && !sdEditorStage(record.Partial)) {
		return errors.New("invalid SD staged replacement")
	}
	parent := filepath.Join(root, filepath.Dir(record.Target))
	resolved, err := filepath.EvalSymlinks(parent)
	if err != nil || resolved != parent {
		return errors.New("SD replacement directory is missing or linked")
	}
	return nil
}

func sdEditorStage(path string) bool {
	name, ok := strings.CutPrefix(filepath.Base(path), ".save-")
	return ok && len(name) >= 32 && strings.Trim(name[:32], "0123456789abcdef") == "" &&
		(len(name) == 32 || name[32] == '.')
}

func sdRegular(path string) (fs.FileInfo, error) {
	info, err := os.Lstat(path)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err == nil && !info.Mode().IsRegular() {
		return nil, fmt.Errorf("SD replacement requires regular files: %s", filepath.Base(path))
	}
	return info, err
}

func sdCheckedRename(from, to string) error {
	_, err := os.Lstat(to)
	if err == nil {
		return &os.LinkError{Op: "rename", Old: from, New: to, Err: fs.ErrExist}
	}
	if !errors.Is(err, fs.ErrNotExist) {
		return err
	}
	return os.Rename(from, to)
}

func (record sdReplacement) matches(info fs.FileInfo) bool {
	return info != nil && info.Size() == record.Size && info.ModTime().UnixNano() == record.Mtime
}

func sdSync(path string) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	return errors.Join(file.Sync(), file.Close())
}

func sdWriteMarker(path string, data []byte) error {
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return err
	}
	_, err = file.Write(data)
	return errors.Join(err, file.Sync(), file.Close())
}

func sdRecoveryDirectory(root string) (string, error) {
	path := filepath.Join(root, removableRecoveryFolder)
	if err := os.Mkdir(path, 0700); err != nil && !errors.Is(err, fs.ErrExist) {
		return "", err
	}
	if info, err := os.Lstat(path); err != nil || !info.IsDir() {
		return "", errors.New("SD recovery location is not an unlinked directory")
	}
	return path, sdSync(root)
}

func (f *removablePullFS) publish(ctx context.Context, staged rclone.Object, remote string) (rclone.Object, error) {
	target := filepath.Join(f.Root(), removableRelative(remote))
	partial := filepath.Join(f.Root(), removableRelative(staged.Remote()))
	if err := publishSDFile(ctx, sdReplacementRoot(f.Root()), target, partial, nil, f.journal); err != nil {
		return nil, err
	}
	return f.Fs.NewObject(context.WithoutCancel(ctx), remote)
}

func publishSDFile(ctx context.Context, root, target, partial string, expected *sdReplacement,
	openJournal func() (string, error)) error {
	relTarget, err := filepath.Rel(root, target)
	if err != nil {
		return err
	}
	relPartial, err := filepath.Rel(root, partial)
	if err != nil {
		return err
	}
	record := sdReplacement{Target: relTarget, Partial: relPartial}
	if err := record.validate(ctx, root); err != nil {
		return err
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	sdPublication.Lock()
	defer sdPublication.Unlock()
	old, err := sdRegular(target)
	if err != nil {
		return err
	}
	if expected != nil && !expected.matches(old) {
		return errors.New("destination changed before SD publication; previous file preserved")
	}
	if old == nil {
		return sdRenameVacant(partial, target)
	}
	info, err := sdRegular(partial)
	if err != nil || info == nil {
		return errors.Join(errors.New("verified SD partial disappeared"), err)
	}
	record.Size, record.Mtime = info.Size(), info.ModTime().UnixNano()
	if err := sdSync(partial); err != nil {
		return err
	}
	journal, err := openJournal()
	if err != nil {
		return err
	}
	txn, err := os.MkdirTemp(journal, "replace-")
	if err != nil {
		return err
	}
	data, err := json.Marshal(record)
	if err != nil {
		return err
	}
	if err := sdWriteMarker(filepath.Join(txn, "record.json"), data); err != nil {
		return errors.Join(err, sdRemoveReplacement(txn))
	}
	if err := errors.Join(sdSync(txn), sdSync(journal)); err != nil {
		return errors.Join(err, sdRemoveReplacement(txn))
	}
	perform := func() error {
		if err := ctx.Err(); err != nil {
			return err
		}
		if err := sdRenameVacant(target, filepath.Join(txn, "old")); err != nil {
			return err
		}
		if err := errors.Join(sdSync(txn), sdSync(filepath.Dir(target)), ctx.Err()); err != nil {
			return err
		}
		if err := sdRenameVacant(partial, target); err != nil {
			return err
		}
		if err := sdSync(filepath.Dir(target)); err != nil {
			return err
		}
		return nil
	}
	if err := perform(); err != nil {
		return errors.Join(err, recoverSDReplacement(root, txn, record))
	}
	if err := sdWriteMarker(filepath.Join(txn, "committed"), nil); err != nil {
		return err
	}
	if err := sdSync(txn); err != nil {
		return err // Keep the old file while durability of the commit is uncertain.
	}
	return recoverSDReplacement(root, txn, record)
}

func (f *removablePullFS) recover(ctx context.Context) error {
	if err := recoverSDVolume(ctx, sdReplacementRoot(f.Root())); err != nil {
		return fserrors.FatalError(err)
	}
	return nil
}

func recoverSDVolume(ctx context.Context, root string) error {
	sdPublication.Lock()
	defer sdPublication.Unlock()
	return recoverSDReplacements(ctx, root)
}

func editorSDPublication(ctx context.Context, request bridgeRequest) error {
	target, partial := request.LocalPath, request.SourcePath
	if !androidRemovablePath(runtime.GOOS, target) || target != filepath.Clean(target) {
		return errors.New("SD publication requires an Android removable storage path")
	}
	root := sdReplacementRoot(target)
	if partial == "" {
		return recoverSDVolume(ctx, root)
	}
	if !filepath.IsAbs(partial) || partial != filepath.Clean(partial) || !sdEditorStage(partial) ||
		filepath.Dir(target) != filepath.Dir(partial) {
		return errors.New("invalid staged SD editor file")
	}
	if request.ExpectedSize == nil || request.ExpectedMtime == nil {
		return errors.New("SD editor publication needs the opened file revision")
	}
	return publishSDFile(ctx, root, target, partial,
		&sdReplacement{Size: *request.ExpectedSize, Mtime: *request.ExpectedMtime},
		func() (string, error) { return sdRecoveryDirectory(root) })
}

func recoverSDReplacements(ctx context.Context, root string) error {
	journal := filepath.Join(root, removableRecoveryFolder)
	info, err := os.Lstat(journal)
	if errors.Is(err, fs.ErrNotExist) {
		return nil
	}
	if err != nil || !info.IsDir() {
		return errors.Join(errors.New("could not open SD replacement recovery directory"), err)
	}
	entries, err := os.ReadDir(journal)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if err := ctx.Err(); err != nil {
			return err
		}
		if !entry.IsDir() || !strings.HasPrefix(entry.Name(), "replace-") {
			return errors.New("unexpected SD recovery entry; preserved for inspection")
		}
		txn := filepath.Join(journal, entry.Name())
		if err := loadSDReplacement(ctx, root, txn); err != nil {
			return fmt.Errorf("SD replacement needs recovery in %s: %w", txn, err)
		}
	}
	return nil
}

func loadSDReplacement(ctx context.Context, root, txn string) error {
	manifest := filepath.Join(txn, "record.json")
	info, err := sdRegular(manifest)
	if err != nil {
		return err
	}
	if info == nil {
		return os.Remove(txn) // Only an empty directory can be an unrecorded preparation.
	}
	if info.Size() > 16384 {
		return errors.New("invalid SD replacement record size")
	}
	data, err := os.ReadFile(manifest)
	if err != nil {
		return err
	}
	var record sdReplacement
	if err := json.Unmarshal(data, &record); err != nil {
		return err
	}
	if err := record.validate(ctx, root); err != nil {
		return err
	}
	return recoverSDReplacement(root, txn, record)
}

func recoverSDReplacement(root, txn string, record sdReplacement) error {
	target := filepath.Join(root, record.Target)
	old := filepath.Join(txn, "old")
	backup, err := sdRegular(old)
	if err != nil {
		return err
	}
	current, err := sdRegular(target)
	if err != nil {
		return err
	}
	if backup == nil {
		if current == nil {
			return errors.New("destination and previous file are missing; recovery record was preserved")
		}
		return sdRemoveReplacement(txn)
	}
	committed, err := sdRegular(filepath.Join(txn, "committed"))
	if err != nil {
		return err
	}
	if current != nil {
		if !record.matches(current) {
			return errors.New("destination changed; the previous file was preserved")
		}
		if committed != nil {
			if err := os.Remove(old); err != nil {
				return err
			}
			return sdRemoveReplacement(txn)
		}
		partial, err := sdRegular(filepath.Join(root, record.Partial))
		if err != nil || partial != nil {
			return errors.Join(errors.New("uncertain publication; the previous file was preserved"), err)
		}
		if err := sdRenameVacant(target, filepath.Join(txn, "new")); err != nil {
			return err
		}
	}
	if err := sdRenameVacant(old, target); err != nil {
		return err
	}
	if err := errors.Join(sdSync(txn), sdSync(filepath.Dir(target))); err != nil {
		return err
	}
	return sdRemoveReplacement(txn)
}

func sdRemoveReplacement(txn string) error {
	for _, name := range []string{"new", "committed", "record.json"} {
		if err := os.Remove(filepath.Join(txn, name)); err != nil && !errors.Is(err, fs.ErrNotExist) {
			return err
		}
	}
	return os.Remove(txn)
}
