package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"
	"path"
	"strings"
	"time"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/object"
	"golang.org/x/sys/unix"
)

// Mirror requests remain scoped to an admitted named configuration. Ciphertext
// paths refer to the configured crypt root, never arbitrary backing locations.
func mirrorConnection(ctx context.Context, name, identity string) (fs.Fs, string, *crypt.Cipher, string, error) {
	current, err := connectionIdentity(name)
	if err != nil || current != identity {
		return nil, "", nil, "", errors.New("connection changed; reload its original credentials")
	}
	kind, _ := store.GetValue(name, "type")
	if kind != "crypt" {
		f, err := remote(ctx, name)
		return f, "", nil, "", err
	}
	cipher, backing, root, cipherID, err := cryptConnection(name)
	if err != nil {
		return nil, "", nil, "", err
	}
	f, err := remote(ctx, backing)
	return f, root, cipher, cipherID, err
}

func mirrorInfo(ctx context.Context, name, folder string) (map[string]any, error) {
	if !validPath(folder) {
		return nil, errors.New("invalid mirror folder")
	}
	identity, err := connectionIdentity(name)
	if err != nil {
		return nil, err
	}
	_, _, cipher, cipherID, err := mirrorConnection(ctx, name, identity)
	if err != nil {
		return nil, err
	}
	prefix := folder
	if cipher != nil {
		prefix = cipher.EncryptDirName(folder)
	}
	return map[string]any{"identity": identity, "cipher_identity": cipherID, "crypt": cipher != nil, "prefix": prefix}, nil
}

func mirrorPlain(cipher *crypt.Cipher, p string, directory bool) (string, error) {
	if !validPath(p) {
		return "", errors.New("invalid mirror path")
	}
	plain := p
	var err error
	if cipher != nil {
		if directory {
			plain, err = cipher.DecryptDirName(p)
		} else {
			plain, err = cipher.DecryptFileName(p)
		}
	}
	if err != nil || !validPath(plain) {
		return "", errors.New("invalid encrypted mirror name")
	}
	for _, component := range strings.Split(plain, "/") {
		if component == ".logistics-backups" {
			return "", errors.New("backup paths are excluded from mirrors")
		}
	}
	return plain, nil
}

func mirrorList(ctx context.Context, name, p, identity string) ([]entry, error) {
	f, root, cipher, _, err := mirrorConnection(ctx, name, identity)
	if err != nil {
		return nil, err
	}
	if _, err = mirrorPlain(cipher, p, true); err != nil {
		return nil, err
	}
	folder := path.Join(root, p)
	if folder == "." {
		folder = ""
	}
	rows, err := f.List(ctx, folder)
	if err != nil {
		return nil, err
	}
	if len(rows) > 1000 {
		return nil, errors.New("folder exceeds 1000 entries")
	}
	result := []entry{}
	for _, row := range rows {
		key := row.Remote()
		if root != "" {
			key = strings.TrimPrefix(key, root+"/")
		}
		_, file := row.(fs.Object)
		plain, e := mirrorPlain(cipher, key, !file)
		if e != nil {
			// Only the reserved backup folder may be omitted. Corrupt names fail closed.
			backup := ".logistics-backups"
			if cipher != nil {
				backup = cipher.EncryptDirName(backup)
			}
			if key == backup || strings.HasPrefix(key, backup+"/") {
				continue
			}
			return nil, e
		}
		_ = plain
		if path.Dir(key) != p && !(p == "" && path.Dir(key) == ".") {
			return nil, errors.New("invalid mirror entry scope")
		}
		result = append(result, entry{key, row.Size(), !file})
	}
	return result, nil
}

func mirrorRead(ctx context.Context, name, p, identity string, fd int) (int64, error) {
	f, root, cipher, _, err := mirrorConnection(ctx, name, identity)
	if err != nil {
		return 0, err
	}
	if p == "" {
		return 0, errors.New("select a file")
	}
	if _, err = mirrorPlain(cipher, p, false); err != nil {
		return 0, err
	}
	obj, err := f.NewObject(ctx, path.Join(root, p))
	if err != nil {
		return 0, err
	}
	output, err := privateOutput(fd)
	if err != nil {
		return 0, err
	}
	defer output.Close()
	reader, err := obj.Open(ctx)
	if err != nil {
		return 0, err
	}
	defer reader.Close()
	var source io.Reader = contextReader{ctx, reader}
	if cipher != nil {
		decrypted, e := cipher.DecryptData(io.NopCloser(io.TeeReader(source, output)))
		if e != nil {
			return 0, e
		}
		defer decrypted.Close()
		_, err = io.Copy(io.Discard, contextReader{ctx, decrypted})
	} else {
		_, err = io.Copy(output, source)
	}
	if err != nil || ctx.Err() != nil {
		return 0, errors.New("mirror download failed or cancelled")
	}
	info, err := output.Stat()
	if err != nil {
		return 0, err
	}
	if info.Size() != obj.Size() {
		return 0, errors.New("remote file changed during pull")
	}
	return info.Size(), nil
}

func mirrorDigest(ctx context.Context, obj fs.Object) (string, error) {
	stream, err := obj.Open(ctx)
	if err != nil {
		return "", err
	}
	defer stream.Close()
	hash := sha256.New()
	_, err = io.Copy(hash, contextReader{ctx, stream})
	if err != nil {
		return "", err
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}

func mirrorStat(ctx context.Context, name, p, identity string) (string, error) {
	f, root, cipher, _, err := mirrorConnection(ctx, name, identity)
	if err != nil {
		return "", err
	}
	if p == "" {
		return "", errors.New("select a file")
	}
	if _, err = mirrorPlain(cipher, p, false); err != nil {
		return "", err
	}
	obj, err := f.NewObject(ctx, path.Join(root, p))
	if errors.Is(err, fs.ErrorObjectNotFound) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return mirrorDigest(ctx, obj)
}

// Changed destinations get a verified remote backup before explicit writeback.
// No delete or arbitrary command endpoint is exposed. Concurrent external changes
// are checked before backup and again immediately before writing.
func mirrorWrite(ctx context.Context, name, p, identity, expected, run string, fd int) (string, error) {
	f, root, cipher, _, err := mirrorConnection(ctx, name, identity)
	if err != nil {
		return "", err
	}
	plain, err := mirrorPlain(cipher, p, false)
	if err != nil || p == "" {
		return "", errors.New("invalid push file")
	}
	if len(run) != 32 || strings.Trim(run, "0123456789abcdef") != "" {
		return "", errors.New("invalid push transaction")
	}
	source, err := mirrorInput(fd)
	if err != nil {
		return "", err
	}
	defer source.Close()
	before, err := source.Stat()
	if err != nil {
		return "", err
	}
	if cipher != nil {
		decrypted, e := cipher.DecryptData(io.NopCloser(contextReader{ctx, source}))
		if e != nil {
			return "", e
		}
		_, e = io.Copy(io.Discard, contextReader{ctx, decrypted})
		decrypted.Close()
		if e != nil {
			return "", e
		}
		_, err = source.Seek(0, 0)
		if err != nil {
			return "", err
		}
	}
	current, err := mirrorStat(ctx, name, p, identity)
	if err != nil {
		return "", err
	}
	if current != expected {
		return "", errors.New("remote file changed; pull or review the conflict before pushing")
	}
	if expected != "" {
		old, e := f.NewObject(ctx, path.Join(root, p))
		if e != nil {
			return "", e
		}
		backup := path.Join(".logistics-backups", run, plain)
		if cipher != nil {
			backup = cipher.EncryptFileName(backup)
		}
		input, e := old.Open(ctx)
		if e != nil {
			return "", e
		}
		saved, e := f.Put(ctx, contextReader{ctx, input}, object.NewStaticObjectInfo(path.Join(root, backup), time.Now(), old.Size(), true, nil, f))
		input.Close()
		if e != nil {
			return "", errors.New("remote backup failed; destination was not replaced")
		}
		check, e := mirrorDigest(ctx, saved)
		if e != nil || check != expected {
			return "", errors.New("remote backup verification failed; destination was not replaced")
		}
		current, e = mirrorStat(ctx, name, p, identity)
		if e != nil || current != expected {
			return "", errors.New("remote changed during backup; destination was not replaced")
		}
	}
	result, err := f.Put(ctx, contextReader{ctx, source}, object.NewStaticObjectInfo(path.Join(root, p), time.Now(), before.Size(), true, nil, f))
	if err != nil {
		return "", errors.New("push failed or cancelled; inspect the destination and retained remote backup")
	}
	after, err := source.Stat()
	if err != nil || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return "", errors.New("push source changed; inspect destination and backup")
	}
	_, err = source.Seek(0, 0)
	if err != nil {
		return "", err
	}
	hash := sha256.New()
	_, err = io.Copy(hash, contextReader{ctx, source})
	if err != nil {
		return "", err
	}
	check, err := mirrorDigest(ctx, result)
	if err != nil || check != hex.EncodeToString(hash.Sum(nil)) {
		return "", errors.New("push verification failed; inspect destination and backup")
	}
	return check, nil
}

func mirrorInput(fd int) (*os.File, error) {
	if fd < 3 {
		return nil, errors.New("invalid push descriptor")
	}
	duplicate, err := unix.Dup(fd)
	if err != nil {
		return nil, err
	}
	file := os.NewFile(uintptr(duplicate), "push-source")
	info, err := file.Stat()
	var stat unix.Stat_t
	offset, seekErr := file.Seek(0, io.SeekCurrent)
	if err != nil || seekErr != nil || offset != 0 || !info.Mode().IsRegular() || unix.Fstat(duplicate, &stat) != nil || stat.Nlink != 1 {
		file.Close()
		return nil, errors.New("push requires an unchanged independent regular file")
	}
	return file, nil
}
