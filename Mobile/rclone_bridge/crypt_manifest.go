package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"github.com/yeka/zip"
	"io"
	"strings"
)

// Hash authenticated member streams without allocating whole members or archives.
func cryptManifest(ctx context.Context, name, encrypted, identity, password string, fd int) (map[string]any, error) {
	_, source, err := openCryptReader(ctx, name, encrypted, identity, fd)
	if err != nil {
		return nil, err
	}
	defer source.file.Close()
	archive, err := zip.NewReader(source, source.size)
	if err != nil || len(archive.File) > 10000 || len(password) > 4096 {
		return nil, errors.New("invalid archive")
	}
	result := map[string]any{}
	seen := map[string]bool{}
	for _, file := range archive.File {
		if !validPath(file.Name) || file.Name == "" || seen[strings.ToLower(file.Name)] || (!file.Mode().IsRegular() && !file.FileInfo().IsDir()) {
			return nil, errors.New("unsafe archive member")
		}
		seen[strings.ToLower(file.Name)] = true
		if file.FileInfo().IsDir() {
			result[file.Name] = nil
			continue
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
		digest := sha256.New()
		length, readErr := io.Copy(digest, contextReader{ctx, stream})
		closeErr := stream.Close()
		if readErr != nil || closeErr != nil || uint64(length) != file.UncompressedSize64 {
			return nil, archivePasswordError
		}
		result[file.Name] = []any{length, hex.EncodeToString(digest.Sum(nil))}
	}
	return result, nil
}
