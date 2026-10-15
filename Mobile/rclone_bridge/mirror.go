package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"io"
	"os"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs"
	"golang.org/x/sys/unix"
)

type mirrorLogicalKey struct{}

// Mirror requests remain scoped to an admitted named configuration. Ciphertext
// paths refer to the configured crypt root, never arbitrary backing locations.
func mirrorConnection(ctx context.Context, name, identity string) (fs.Fs, string, *crypt.Cipher, string, error) {
	current, err := connectionIdentity(name)
	if err != nil || current != identity {
		return nil, "", nil, "", errors.New("connection changed; reload its original credentials")
	}
	kind, _ := store.GetValue(name, "type")
	if kind != "crypt" || ctx.Value(mirrorLogicalKey{}) == true {
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

	return plain, nil
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

func mirrorValidate(ctx context.Context, name, p, identity string, fd int) (string, error) {
	current, err := connectionIdentity(name)
	if err != nil || current != identity {
		return "", errors.New("connection changed")
	}
	kind, _ := store.GetValue(name, "type")
	var cipher *crypt.Cipher
	if kind == "crypt" && ctx.Value(mirrorLogicalKey{}) != true {
		cipher, _, _, _, err = cryptConnection(name)
		if err != nil {
			return "", err
		}
	}
	if _, err = mirrorPlain(cipher, p, false); err != nil {
		return "", err
	}
	file, err := mirrorInput(fd)
	if err != nil {
		return "", err
	}
	defer file.Close()
	before, err := file.Stat()
	if err != nil {
		return "", err
	}
	hash := sha256.New()
	var reader io.Reader = contextReader{ctx, file}
	if cipher != nil {
		decrypted, e := cipher.DecryptData(io.NopCloser(io.TeeReader(reader, hash)))
		if e != nil {
			return "", e
		}
		defer decrypted.Close()
		_, err = io.Copy(io.Discard, contextReader{ctx, decrypted})
	} else {
		_, err = io.Copy(hash, reader)
	}
	if err != nil {
		return "", errors.New("ciphertext authentication or source inspection failed")
	}
	after, err := file.Stat()
	if err != nil || before.Size() != after.Size() || !before.ModTime().Equal(after.ModTime()) {
		return "", errors.New("push source changed during inspection")
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
