// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"sync"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/hash"
	"golang.org/x/sys/unix"
)

const downloadChunk = 4 * 1024 * 1024

var downloadRangeUnavailable = errors.New("the source cannot supply a verified byte range")

var downloadConnections sync.Mutex

func downloadRemote(ctx context.Context, name string) (fs.Fs, error) {
	downloadConnections.Lock()
	defer downloadConnections.Unlock()
	return remote(ctx, name)
}

// A resumable plaintext object needs a provider-supplied content hash. Crypt
// supplies a fresh file nonce on every rewrite and authenticates each block.
func downloadRange(ctx context.Context, request bridgeRequest, read bool) (any, error) {
	return readDownload(ctx, request, read, false)
}

func readDownload(ctx context.Context, request bridgeRequest, read, streaming bool) (any, error) {
	reader, size, stamp, err := resolveRemoteDocument(ctx, request.Remote, request.Path, request.Identity, downloadRemote)
	if err != nil {
		return nil, err
	}
	kind, _ := store.GetValue(request.Remote, "type")
	encoded := request.DestinationRemote != ""
	unsupported := func() (any, error) {
		if read {
			return nil, downloadRangeUnavailable
		}
		return map[string]any{"supported": false, "size": size}, nil
	}
	fingerprint, algorithm, checksum := "", "", ""
	var header []byte
	if reader.cipher != nil {
		_, backing, _, identity, err := cryptConnection(request.Remote)
		if err != nil {
			return nil, err
		}
		if encoded {
			_, _, _, destID, err := cryptConnection(request.DestinationRemote)
			if err != nil || destID != request.DestinationIdentity {
				return nil, errors.New("destination cipher changed or is locked")
			}
			if destID != identity {
				return unsupported()
			}
		}
		kind, _ = store.GetValue(backing, "type")
		header, err = exactRange(ctx, reader, 0, 32)
		if err != nil {
			return nil, err
		}
		if !bytes.HasPrefix(header, []byte("RCLONE\x00\x00")) {
			return nil, errors.New("invalid encrypted source header")
		}
		fingerprint = hex.EncodeToString(header)
	} else {
		if encoded {
			return unsupported()
		}
		for _, t := range []hash.Type{hash.SHA256, hash.SHA1, hash.MD5} {
			if reader.object.Fs().Hashes().Contains(t) && !reader.object.Fs().Features().SlowHash {
				value, err := reader.object.Hash(ctx, t)
				if errors.Is(err, hash.ErrUnsupported) {
					continue
				}
				if err != nil {
					return nil, err
				}
				if value != "" {
					algorithm, checksum = map[hash.Type]string{hash.SHA256: "sha256", hash.SHA1: "sha1", hash.MD5: "md5"}[t], value
					fingerprint = algorithm + ":" + checksum
					break
				}
			}
		}
	}
	switch kind {
	case "memory", "s3", "drive", "onedrive", "dropbox", "smb", "webdav":
	default:
		return unsupported()
	}
	if fingerprint == "" {
		return unsupported()
	}
	version := fmt.Sprintf("%x", sha256.Sum256([]byte(stamp+":"+fingerprint)))
	if !read {
		return map[string]any{"supported": true, "size": size, "version": version, "encoded": encoded,
			"algorithm": algorithm, "checksum": checksum}, nil
	}
	offset := request.Offset
	if request.Expected != version || offset < 0 || offset%65536 != 0 || offset >= size {
		return nil, errors.New("source changed or download range is invalid")
	}
	if streaming {
		return streamDownload(ctx, reader, header, offset, size-offset, encoded, request.FD)
	}
	count := int64(request.Count)
	if count <= 0 || count > downloadChunk || count > size-offset || (offset+count < size && count%65536 != 0) {
		return nil, errors.New("source changed or download range is invalid")
	}
	var data []byte
	if reader.cipher == nil {
		data, err = exactRange(ctx, reader, offset, count)
	} else {
		data, err = authenticatedDownloadRange(ctx, reader, header, offset, count, encoded)
	}
	if err != nil {
		return nil, err
	}
	return base64.StdEncoding.EncodeToString(data), nil
}

// Fetch whole authenticated blocks, including the final short block. Reuse
// the verified source ciphertext for a matching LocalCrypt destination.
func authenticatedDownloadRange(ctx context.Context, reader remoteReaderAt, header []byte, offset, count int64, encoded bool) ([]byte, error) {
	start := reader.cipher.EncryptedSize(offset)
	end := reader.cipher.EncryptedSize(offset + count)
	raw, err := exactRange(ctx, reader, start, end-start)
	if err != nil {
		return nil, err
	}
	return authenticateDownloadBlocks(ctx, reader, header, raw, offset, count, encoded)
}

// A single response supplies every checkpoint. Each chunk is authenticated
// before it crosses the pipe, and Python retains all checkpoint ownership.
func streamDownload(ctx context.Context, reader remoteReaderAt, header []byte, offset, count int64, encoded bool, fd int) (int64, error) {
	if fd < 3 {
		return 0, errors.New("a private download pipe is required")
	}
	duplicate, err := unix.FcntlInt(uintptr(fd), unix.F_DUPFD_CLOEXEC, 0)
	if err != nil {
		return 0, errors.New("the download pipe is unavailable")
	}
	var info unix.Stat_t
	if err := unix.Fstat(duplicate, &info); err != nil || info.Mode&unix.S_IFMT != unix.S_IFIFO {
		unix.Close(duplicate)
		return 0, errors.New("a private download pipe is required")
	}
	// Register the pipe with Go's poller so cancellation can interrupt a
	// write even when the host is no longer draining the pipe.
	if err := unix.SetNonblock(duplicate, true); err != nil {
		unix.Close(duplicate)
		return 0, errors.New("the download pipe is unavailable")
	}
	output := os.NewFile(uintptr(duplicate), "download pipe")
	defer output.Close()
	stop := context.AfterFunc(ctx, func() { output.Close() })
	defer stop()
	start, length := offset, count
	if reader.cipher != nil {
		start = reader.cipher.EncryptedSize(offset)
		length = reader.cipher.EncryptedSize(offset+count) - start
	}
	input, err := reader.open(ctx, start, length)
	if err != nil {
		return 0, errors.New("the download stream could not be opened")
	}
	defer input.Close()
	if reader.cipher == nil {
		written, err := io.CopyN(output, input, count)
		if err != nil {
			return 0, errors.New("the download stream was interrupted")
		}
		return written, nil
	}
	raw := make([]byte, reader.cipher.EncryptedSize(downloadChunk)-reader.cipher.EncryptedSize(0))
	for position := offset; position < offset+count; {
		if err := ctx.Err(); err != nil {
			return 0, err
		}
		size := min(downloadChunk, offset+count-position)
		length := reader.cipher.EncryptedSize(position+size) - reader.cipher.EncryptedSize(position)
		if _, err := io.ReadFull(input, raw[:length]); err != nil {
			return 0, errors.New("the download stream was interrupted")
		}
		verified, err := authenticateDownloadBlocks(ctx, reader, header, raw[:length], position, size, encoded)
		if err != nil {
			return 0, err
		}
		if _, err := output.Write(verified); err != nil {
			return 0, errors.New("the download stream was interrupted")
		}
		position += size
	}
	return count, nil
}

func authenticateDownloadBlocks(ctx context.Context, reader remoteReaderAt, header, raw []byte, offset, count int64, encoded bool) ([]byte, error) {
	start := reader.cipher.EncryptedSize(offset)
	open := func(_ context.Context, pos, _ int64) (io.ReadCloser, error) {
		switch {
		case pos == 0 && offset == 0:
			return io.NopCloser(io.MultiReader(bytes.NewReader(header), bytes.NewReader(raw))), nil
		case pos == 0:
			return io.NopCloser(bytes.NewReader(header)), nil
		case pos == start:
			return io.NopCloser(bytes.NewReader(raw)), nil
		default:
			return nil, errors.New("invalid encrypted block boundary")
		}
	}
	plain, err := reader.cipher.DecryptDataSeek(ctx, open, offset, count)
	if err != nil {
		return nil, err
	}
	defer plain.Close()
	if encoded {
		n, err := io.Copy(io.Discard, plain)
		if err != nil || n != count {
			return nil, errors.New("encrypted block authentication failed")
		}
		if offset == 0 {
			return append(header, raw...), nil
		}
		return raw, nil
	}
	data, err := io.ReadAll(plain)
	if err != nil || int64(len(data)) != count {
		return nil, errors.New("encrypted range authentication failed")
	}
	return data, nil
}

func exactRange(ctx context.Context, reader remoteReaderAt, offset, length int64) ([]byte, error) {
	source, err := reader.open(ctx, offset, length)
	if err != nil {
		return nil, err
	}
	defer source.Close()
	data, err := io.ReadAll(io.LimitReader(source, length+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) != length {
		return nil, downloadRangeUnavailable
	}
	return data, nil
}
