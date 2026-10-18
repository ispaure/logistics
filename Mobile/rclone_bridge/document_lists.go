package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"errors"
	"io"

	"github.com/yeka/zip"
)

const documentListLimit = 128 * 1024

type documentListKey struct {
	id       string
	password []byte
}

// Access is protected by credentialScope. Passwords never enter a snapshot/vault.
var documentListKeys = map[string]documentListKey{}

func clearDocumentListKeys() {
	for key, value := range documentListKeys {
		clear(value.password)
		delete(documentListKeys, key)
	}
}

func installDocumentListKey(label string, data []byte, password string, sessionOnly bool) {
	key := packageID(label)
	if previous, ok := documentListKeys[key]; ok {
		clear(previous.password)
		delete(documentListKeys, key)
	}
	if !sessionOnly || password == "" {
		return
	}
	archive, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return
	}
	for _, member := range archive.File {
		if !member.FileInfo().IsDir() && !member.IsEncrypted() {
			return
		}
	}
	hash := sha256.New()
	hash.Write([]byte(label + "\x00"))
	hash.Write(data)
	documentListKeys[key] = documentListKey{hex.EncodeToString(hash.Sum(nil)), []byte(password)}
}

func documentListID(packageKey string) string {
	return documentListKeys[packageKey].id
}

func aes256Member(member *zip.File) bool {
	extra := member.Extra
	for len(extra) >= 4 {
		tag, size := binary.LittleEndian.Uint16(extra), int(binary.LittleEndian.Uint16(extra[2:]))
		if size > len(extra)-4 {
			return false
		}
		if tag == 0x9901 {
			value := extra[4 : 4+size]
			return size == 7 && string(value[2:4]) == "AE" && value[4] == 3
		}
		extra = extra[4+size:]
	}
	return false
}

func documentLists(id string, data []byte, decode bool) ([]byte, error) {
	var password []byte
	for _, value := range documentListKeys {
		if value.id == id {
			password = value.password
			break
		}
	}
	if len(password) == 0 || len(data) > documentListLimit+1024 {
		return nil, errors.New("document list credential is locked or cache exceeds limits")
	}
	if decode {
		archive, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
		if err != nil || len(archive.File) != 1 {
			return nil, errors.New("invalid encrypted document list")
		}
		member := archive.File[0]
		if member.Name != "entries.json" || !member.IsEncrypted() || !aes256Member(member) || member.UncompressedSize64 > documentListLimit {
			return nil, errors.New("invalid encrypted document list")
		}
		member.SetPassword(string(password))
		source, err := member.Open()
		if err != nil {
			return nil, errors.New("document list authentication failed")
		}
		plain, readErr := io.ReadAll(io.LimitReader(source, documentListLimit+1))
		closeErr := source.Close()
		if readErr != nil || closeErr != nil || len(plain) > documentListLimit || uint64(len(plain)) != member.UncompressedSize64 {
			clear(plain)
			return nil, errors.New("document list authentication failed")
		}
		return plain, nil
	}
	if len(data) > documentListLimit {
		return nil, errors.New("document list exceeds limits")
	}
	output := &bytes.Buffer{}
	writer := zip.NewWriter(output)
	member, err := writer.Encrypt("entries.json", string(password), zip.AES256Encryption)
	if err != nil {
		return nil, err
	}
	if _, err = member.Write(data); err != nil {
		return nil, err
	}
	if err = writer.Close(); err != nil {
		return nil, err
	}
	return output.Bytes(), nil
}
