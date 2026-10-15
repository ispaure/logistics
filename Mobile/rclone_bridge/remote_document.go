package main

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"path"

	"github.com/rclone/rclone/backend/crypt"
)

// Resolve one logical remote file without materializing a plaintext local copy.
func remoteDocument(ctx context.Context, name, p, identity string) (remoteReaderAt, int64, string, error) {
	var empty remoteReaderAt
	if err := ctx.Err(); err != nil {
		return empty, 0, "", err
	}
	current, err := connectionIdentity(name)
	if err != nil || identity != current || p == "" || !validPath(p) {
		return empty, 0, "", errors.New("connection changed or invalid remote path")
	}
	var cipher *crypt.Cipher
	backing, objectPath := name, p
	if kind, _ := store.GetValue(name, "type"); kind == "crypt" {
		var root string
		cipher, backing, root, _, err = cryptConnection(name)
		if err != nil {
			return empty, 0, "", err
		}
		objectPath = path.Join(root, cipher.EncryptFileName(p))
	}
	backend, err := remote(ctx, backing)
	if err != nil {
		return empty, 0, "", err
	}
	object, err := backend.NewObject(ctx, objectPath)
	if err != nil {
		return empty, 0, "", errors.New("remote file could not be opened")
	}
	size := object.Size()
	if cipher != nil {
		size, err = cipher.DecryptedSize(size)
	}
	if err != nil || size < 0 {
		return empty, 0, "", errors.New("remote file size unavailable")
	}
	stamp := fmt.Sprintf("%s:%d:%s", object.Remote(), object.Size(), object.ModTime(ctx).UTC().String())
	revision := fmt.Sprintf("%x", sha256.Sum256([]byte(stamp)))
	return remoteReaderAt{ctx, object, cipher}, size, revision, nil
}

func remoteDocumentRequest(ctx context.Context, action, name, p, identity, expected, password, member string, offset int64, count int) (any, error) {
	reader, size, revision, err := remoteDocument(ctx, name, p, identity)
	if err != nil {
		return nil, err
	}
	if expected != "" && expected != revision {
		return nil, errors.New("remote file changed; reopen it")
	}
	if action == "remote_stat" {
		return map[string]any{"size": size, "revision": revision}, nil
	}
	var result any
	if action == "remote_archive" {
		result, err = archiveContents(ctx, reader, size, password, member, 10000, 16*1024*1024)
	} else {
		if expected == "" || offset < 0 || count < 0 || count > 1024*1024 || offset > size || int64(count) > size-offset {
			return nil, errors.New("invalid remote read range")
		}
		data := make([]byte, count)
		if count > 0 {
			_, err = reader.ReadAt(data, offset)
			if err == io.EOF {
				err = errors.New("incomplete remote read")
			}
		}
		result = map[string]string{"data": base64.StdEncoding.EncodeToString(data)}
	}
	if err != nil {
		return nil, err
	}
	_, _, after, err := remoteDocument(ctx, name, p, identity)
	if err != nil || after != revision {
		return nil, errors.New("remote file changed while reading; reopen it")
	}
	return result, nil
}
