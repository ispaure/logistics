package main

import (
	"bytes"
	"context"
	"errors"
	"io"
	"strings"

	"github.com/yeka/zip"
)

var archivePasswordError = errors.New("Enter the inner ZIP password; the password may be wrong or the archive damaged.")

// An authenticated RAM-only ZIP view. Original inner encryption stays on disk.
func unlockArchive(ctx context.Context, data []byte, password string) ([]byte, error) {
	archive, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, errors.New("invalid inner ZIP archive")
	}
	if len(archive.File) > 5000 || len(password) > 4096 {
		return nil, errors.New("inner ZIP exceeds mobile limits")
	}
	protected := false
	seen := map[string]bool{}
	total := uint64(0)
	for _, member := range archive.File {
		total += member.UncompressedSize64
		if !validPath(member.Name) || member.Name == "" || seen[strings.ToLower(member.Name)] ||
			(!member.Mode().IsRegular() && !member.FileInfo().IsDir()) || member.UncompressedSize64 > 8*1024*1024 || total > 256*1024*1024 {
			return nil, errors.New("unsafe or oversized inner ZIP archive")
		}
		seen[strings.ToLower(member.Name)] = true
		protected = protected || member.IsEncrypted()
	}
	if !protected {
		return data, nil
	}
	if password == "" {
		return nil, archivePasswordError
	}
	output := &boundedZIPBuffer{}
	writer := zip.NewWriter(output)
	for _, member := range archive.File {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		if member.IsEncrypted() {
			member.SetPassword(password)
		}
		source, err := member.Open()
		if err != nil {
			return nil, archivePasswordError
		}
		content, readErr := readBounded(ctx, source, 8*1024*1024)
		closeErr := source.Close()
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		if readErr != nil || closeErr != nil || uint64(len(content)) != member.UncompressedSize64 {
			return nil, archivePasswordError
		}
		destination, err := writer.Create(member.Name)
		if err != nil {
			return nil, errors.New("inner ZIP view could not be created")
		}
		if _, err = destination.Write(content); err != nil {
			return nil, err
		}
	}
	if err = writer.Close(); err != nil {
		return nil, err
	}
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	return output.Bytes(), nil
}

type boundedZIPBuffer struct{ bytes.Buffer }

func (buffer *boundedZIPBuffer) Write(data []byte) (int, error) {
	if buffer.Len()+len(data) > downloadLimit {
		return 0, errors.New("decrypted archive view exceeds 32 MiB")
	}
	return buffer.Buffer.Write(data)
}

var _ io.Writer = (*boundedZIPBuffer)(nil)
