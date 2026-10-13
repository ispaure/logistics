package main

import (
	stdzip "archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"io"
	"path"
	"strings"

	"github.com/yeka/zip"
)

// Preserve original compressed/encrypted members verbatim. Only the metadata
// member is rebuilt; protected metadata is encrypted with the same password.
func patchArchive(ctx context.Context, data []byte, password, member string, replacement []byte) ([]byte, error) {
	if !validPath(member) || member == "" || len(replacement) > packageLimit {
		return nil, errors.New("invalid metadata replacement")
	}
	// Authenticate all encrypted members before a rewrite. The returned view also
	// validates paths, counts and expansion limits; it is never written to disk.
	if _, err := unlockArchive(ctx, data, password); err != nil {
		return nil, err
	}
	original, err := stdzip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, err
	}
	protected := false
	found := false
	for _, file := range original.File {
		protected = protected || file.Flags&1 != 0
		found = found || file.Name == member
	}
	if !found && path.Base(member) != "ComicInfo.xml" {
		return nil, errors.New("EPUB metadata member is missing")
	}
	var update bytes.Buffer
	if protected {
		writer := zip.NewWriter(&update)
		target, err := writer.Encrypt(member, password, zip.AES256Encryption)
		if err != nil {
			return nil, err
		}
		if _, err = target.Write(replacement); err != nil {
			return nil, err
		}
		if err = writer.Close(); err != nil {
			return nil, err
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
		target, err := writer.CreateHeader(header)
		if err != nil {
			return nil, err
		}
		if _, err = target.Write(replacement); err != nil {
			return nil, err
		}
		if err = writer.Close(); err != nil {
			return nil, err
		}
	}
	patch, err := stdzip.NewReader(bytes.NewReader(update.Bytes()), int64(update.Len()))
	if err != nil {
		return nil, err
	}
	// Preserve entry annotations and timestamps independently of its new
	// compression/encryption headers and checksums.
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
	output := &boundedZIPBuffer{}
	writer := stdzip.NewWriter(output)
	if err = writer.SetComment(original.Comment); err != nil {
		return nil, err
	}
	for _, file := range original.File {
		if err = ctx.Err(); err != nil {
			return nil, err
		}
		if file.Name == member {
			err = writer.Copy(patch.File[0])
		} else {
			err = writer.Copy(file)
		}
		if err != nil {
			return nil, err
		}
	}
	if !found {
		if err = writer.Copy(patch.File[0]); err != nil {
			return nil, err
		}
	}
	if err = writer.Close(); err != nil {
		return nil, err
	}
	// Verify inner authentication, including the newly encrypted metadata.
	if _, err = unlockArchive(ctx, output.Bytes(), password); err != nil {
		return nil, err
	}
	return output.Bytes(), ctx.Err()
}

func cryptMetadata(ctx context.Context, name, encrypted, identity, password, member, encoded string, fd, outputFD int) (bool, error) {
	plain, data, err := decryptCopy(ctx, name, encrypted, identity, fd)
	if err != nil {
		return false, err
	}
	suffix := strings.ToLower(path.Ext(plain))
	if suffix != ".epub" && suffix != ".cbz" && suffix != ".zip" {
		return false, errors.New("metadata requires EPUB or comic ZIP")
	}
	if suffix != ".epub" && !strings.EqualFold(path.Base(member), "ComicInfo.xml") {
		return false, errors.New("invalid comic metadata member")
	}
	replacement, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return false, err
	}
	updated, err := patchArchive(ctx, data, password, member, replacement)
	if err != nil {
		return false, err
	}
	_, cipher, err := cryptDescribe(name, encrypted, identity)
	if err != nil {
		return false, err
	}
	target, err := privateOutput(outputFD)
	if err != nil {
		return false, err
	}
	defer target.Close()
	source, err := cipher.EncryptData(bytes.NewReader(updated))
	if err != nil {
		return false, err
	}
	ciphertext, err := readBounded(ctx, source, downloadLimit)
	if err != nil {
		return false, err
	}
	if _, err = io.Copy(target, bytes.NewReader(ciphertext)); err != nil {
		return false, err
	}
	if err = target.Sync(); err != nil {
		return false, err
	}
	return true, ctx.Err()
}

// Size and encryption extras describe the replaced payload, not its metadata.
func metadataExtra(extra []byte) []byte {
	result := []byte{}
	for len(extra) >= 4 {
		id, size := binary.LittleEndian.Uint16(extra), int(binary.LittleEndian.Uint16(extra[2:]))
		if size+4 > len(extra) {
			break
		}
		if id != 0x0001 && id != 0x9901 {
			result = append(result, extra[:size+4]...)
		}
		extra = extra[size+4:]
	}
	return result
}
