package main

import (
	stdzip "archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"errors"
	"io"
	"path"
	"strings"

	"github.com/yeka/zip"
)

func cryptStreamMetadata(ctx context.Context, name, encrypted, identity, password, member, encoded string, fd, outputFD int) (bool, error) {
	plain, source, err := openCryptReader(ctx, name, encrypted, identity, fd)
	if err != nil {
		return false, err
	}
	defer source.file.Close()
	suffix := strings.ToLower(path.Ext(plain))
	if (suffix != ".epub" && suffix != ".cbz" && suffix != ".zip") || !validPath(member) || member == "" || (suffix != ".epub" && !strings.EqualFold(path.Base(member), "ComicInfo.xml")) {
		return false, errors.New("invalid metadata member")
	}
	data, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(data) > packageLimit {
		return false, errors.New("metadata exceeds its buffer limit")
	}
	original, err := stdzip.NewReader(source, source.size)
	if err != nil || len(original.File) > 10000 {
		return false, errors.New("invalid archive")
	}
	// Authenticate each member as a stream before rewriting. RAM stays bounded.
	authenticated, err := zip.NewReader(source, source.size)
	if err != nil {
		return false, err
	}
	protected, found := false, false
	seen := map[string]bool{}
	for _, file := range authenticated.File {
		if !validPath(file.Name) || file.Name == "" || seen[strings.ToLower(file.Name)] || (!file.Mode().IsRegular() && !file.FileInfo().IsDir()) {
			return false, errors.New("unsafe archive entry")
		}
		seen[strings.ToLower(file.Name)] = true
		found = found || file.Name == member
		protected = protected || file.IsEncrypted()
		if file.IsEncrypted() {
			if password == "" {
				return false, archivePasswordError
			}
			file.SetPassword(password)
		}
		stream, err := file.Open()
		if err != nil {
			return false, archivePasswordError
		}
		_, readErr := io.Copy(io.Discard, contextReader{ctx, stream})
		closeErr := stream.Close()
		if readErr != nil || closeErr != nil {
			return false, archivePasswordError
		}
	}
	if !found && path.Base(member) != "ComicInfo.xml" {
		return false, errors.New("metadata member is missing")
	}
	var update bytes.Buffer
	if protected {
		writer := zip.NewWriter(&update)
		entry, err := writer.Encrypt(member, password, zip.AES256Encryption)
		if err != nil {
			return false, err
		}
		if _, err = entry.Write(data); err != nil {
			return false, err
		}
		if err = writer.Close(); err != nil {
			return false, err
		}
	} else {
		writer := stdzip.NewWriter(&update)
		header := &stdzip.FileHeader{Name: member, Method: stdzip.Deflate}
		for _, file := range original.File {
			if file.Name == member {
				*header = file.FileHeader
				header.Extra = metadataExtra(file.Extra)
				break
			}
		}
		entry, err := writer.CreateHeader(header)
		if err != nil {
			return false, err
		}
		if _, err = entry.Write(data); err != nil {
			return false, err
		}
		if err = writer.Close(); err != nil {
			return false, err
		}
	}
	patch, err := stdzip.NewReader(bytes.NewReader(update.Bytes()), int64(update.Len()))
	if err != nil {
		return false, err
	}
	for _, file := range original.File {
		if file.Name == member {
			header := &patch.File[0].FileHeader
			header.Comment, header.NonUTF8 = file.Comment, file.NonUTF8
			header.Modified, header.ModifiedTime, header.ModifiedDate = file.Modified, file.ModifiedTime, file.ModifiedDate
			header.CreatorVersion, header.ExternalAttrs = file.CreatorVersion, file.ExternalAttrs
			if protected {
				header.Extra = append(metadataExtra(file.Extra), header.Extra...)
			}
			break
		}
	}
	target, err := privateOutput(outputFD)
	if err != nil {
		return false, err
	}
	defer target.Close()
	pipeReader, pipeWriter := io.Pipe()
	finished := make(chan error, 1)
	go func() {
		encryptedStream, err := source.cipher.EncryptData(pipeReader)
		if err == nil {
			_, err = io.Copy(target, contextReader{ctx, encryptedStream})
		}
		pipeReader.CloseWithError(err)
		finished <- err
	}()
	writer := stdzip.NewWriter(pipeWriter)
	err = writer.SetComment(original.Comment)
	for _, file := range original.File {
		if err != nil {
			break
		}
		if ctx.Err() != nil {
			err = ctx.Err()
			break
		}
		if file.Name == member {
			err = writer.Copy(patch.File[0])
		} else {
			err = writer.Copy(file)
		}
	}
	if err == nil && !found {
		err = writer.Copy(patch.File[0])
	}
	if err == nil {
		err = writer.Close()
	}
	pipeWriter.CloseWithError(err)
	copyErr := <-finished
	if err != nil {
		return false, err
	}
	if copyErr != nil {
		return false, copyErr
	}
	return true, target.Sync()
}
