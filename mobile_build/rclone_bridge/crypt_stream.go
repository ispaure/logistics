package main

import (
	"context"
	"encoding/base64"
	"errors"
	"io"
	"os"
	"path"
	"strings"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/yeka/zip"
	"golang.org/x/sys/unix"
)

// A caller-owned ciphertext file is exposed as authenticated plaintext ranges.
// No plaintext file and no whole-file byte slice is created.
type cryptReaderAt struct {
	ctx    context.Context
	file   *os.File
	cipher *crypt.Cipher
	size   int64
}

func openCryptReader(ctx context.Context, name, encrypted, identity string, fd int) (string, *cryptReaderAt, error) {
	plain, cipher, err := cryptDescribe(name, encrypted, identity)
	if err != nil {
		return "", nil, err
	}
	if fd < 3 {
		return "", nil, errors.New("invalid encrypted descriptor")
	}
	duplicate, err := unix.Dup(fd)
	if err != nil {
		return "", nil, err
	}
	file := os.NewFile(uintptr(duplicate), "encrypted-range")
	info, err := file.Stat()
	var stat unix.Stat_t
	if err != nil || !info.Mode().IsRegular() || unix.Fstat(duplicate, &stat) != nil || stat.Nlink != 1 {
		file.Close()
		return "", nil, errors.New("encrypted file must be independent and regular")
	}
	size, err := cipher.DecryptedSize(info.Size())
	if err != nil {
		file.Close()
		return "", nil, err
	}
	return path.Base(plain), &cryptReaderAt{ctx, file, cipher, size}, nil
}

func (reader *cryptReaderAt) stream(offset, limit int64) (crypt.ReadSeekCloser, error) {
	return reader.cipher.DecryptDataSeek(reader.ctx, func(ctx context.Context, start, length int64) (io.ReadCloser, error) {
		return io.NopCloser(io.NewSectionReader(reader.file, start, reader.fileSize()-start)), nil
	}, offset, limit)
}

func (reader *cryptReaderAt) fileSize() int64 { info, _ := reader.file.Stat(); return info.Size() }
func (reader *cryptReaderAt) ReadAt(buffer []byte, offset int64) (int, error) {
	if reader.ctx.Err() != nil {
		return 0, reader.ctx.Err()
	}
	if offset < 0 {
		return 0, errors.New("invalid range")
	}
	stream, err := reader.stream(offset, int64(len(buffer)))
	if err != nil {
		return 0, err
	}
	defer stream.Close()
	return io.ReadFull(stream, buffer)
}

func cryptStat(ctx context.Context, name, encrypted, identity string, fd int) (map[string]any, error) {
	plain, reader, err := openCryptReader(ctx, name, encrypted, identity, fd)
	if err != nil {
		return nil, err
	}
	defer reader.file.Close()
	return map[string]any{"name": plain, "size": reader.size}, nil
}

func cryptRange(ctx context.Context, name, encrypted, identity string, fd int, offset int64, count int) (map[string]string, error) {
	if count < 0 || count > 4*1024*1024 || offset < 0 {
		return nil, errors.New("range exceeds buffer limit")
	}
	plain, reader, err := openCryptReader(ctx, name, encrypted, identity, fd)
	if err != nil {
		return nil, err
	}
	defer reader.file.Close()
	if offset > reader.size || int64(count) > reader.size-offset {
		return nil, errors.New("range outside file")
	}
	data := make([]byte, count)
	if count > 0 {
		if _, err = reader.ReadAt(data, offset); err != nil {
			return nil, err
		}
	}
	return map[string]string{"name": plain, "data": base64.StdEncoding.EncodeToString(data)}, nil
}

type zipEntry struct {
	Name      string `json:"name"`
	Size      uint64 `json:"size"`
	CRC       uint32 `json:"crc"`
	Flags     uint16 `json:"flags"`
	Directory bool   `json:"directory"`
}

func cryptArchive(ctx context.Context, name, encrypted, identity, password, member string, fd int) (any, error) {
	_, reader, err := openCryptReader(ctx, name, encrypted, identity, fd)
	if err != nil {
		return nil, err
	}
	defer reader.file.Close()
	return archiveContents(ctx, reader, reader.size, password, member, 10000, 16*1024*1024)
}

func archiveContents(ctx context.Context, reader io.ReaderAt, size int64, password, member string, maxMembers, maxRead int) (any, error) {
	archive, err := zip.NewReader(reader, size)
	if err != nil {
		return nil, errors.New("invalid inner archive")
	}
	if len(archive.File) > maxMembers || len(password) > 4096 {
		return nil, errors.New("archive header exceeds limits")
	}
	seen := map[string]bool{}
	entries := []zipEntry{}
	var selected *zip.File
	for _, file := range archive.File {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		if !validPath(file.Name) || file.Name == "" || seen[strings.ToLower(file.Name)] || (!file.Mode().IsRegular() && !file.FileInfo().IsDir()) {
			return nil, errors.New("unsafe archive member")
		}
		seen[strings.ToLower(file.Name)] = true
		entries = append(entries, zipEntry{file.Name, file.UncompressedSize64, file.CRC32, file.Flags, file.FileInfo().IsDir()})
		if file.Name == member {
			selected = file
		}
	}
	if selected != nil {
		file := selected
		if file.UncompressedSize64 > uint64(maxRead) {
			return nil, errors.New("archive member exceeds the read buffer limit")
		}
		if file.IsEncrypted() {
			if password == "" {
				return nil, archivePasswordError
			}
			file.SetPassword(password)
		}
		stream, err := file.Open()
		if err != nil {
			return nil, archivePasswordError
		}
		data, readErr := readBounded(ctx, stream, maxRead)
		closeErr := stream.Close()
		if readErr != nil || closeErr != nil || uint64(len(data)) != file.UncompressedSize64 {
			return nil, archivePasswordError
		}
		return map[string]string{"data": base64.StdEncoding.EncodeToString(data)}, nil
	}
	if member != "" {
		return nil, errors.New("archive member not found")
	}
	return entries, nil
}

type contextReader struct {
	ctx    context.Context
	reader io.Reader
}

func (reader contextReader) Read(buffer []byte) (int, error) {
	if reader.ctx.Err() != nil {
		return 0, reader.ctx.Err()
	}
	return reader.reader.Read(buffer)
}
