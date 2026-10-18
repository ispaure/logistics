package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path"
	"sort"
	"strings"
	"sync"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/config/configmap"
	"golang.org/x/sys/unix"
)

func cryptCipher(values map[string]string) (*crypt.Cipher, error) {
	info, err := fs.Find("crypt")
	if err != nil {
		return nil, err
	}
	options := fs.ConfigMap(info.Prefix, info.Options, "", nil)
	options.ClearGetters(configmap.PriorityNormal)
	options.AddGetter(configmap.Simple(values), configmap.PriorityNormal)
	cipher, err := crypt.NewCipher(options)
	if err != nil {
		return nil, errors.New("invalid crypt settings")
	}
	return cipher, nil
}

// Only one crypt layer over an admitted backend. No arbitrary fs.NewFs paths.
func cryptBacking(values map[string]string, remotes map[string]map[string]string) (string, string, error) {
	name, root, ok := strings.Cut(values["remote"], ":")
	backing, exists := remotes[name]
	root = strings.Trim(root, "/")
	if !ok || !exists || backing["type"] == "crypt" || !validPath(root) {
		return "", "", errors.New("crypt must reference a supported backing remote in the same package")
	}
	if _, ok := allowed[backing["type"]]; !ok {
		return "", "", errors.New("unsupported crypt backing remote")
	}
	return name, root, nil
}

func validateCryptRemotes(remotes map[string]map[string]string) error {
	for _, values := range remotes {
		if values["type"] != "crypt" {
			continue
		}
		if _, _, err := cryptBacking(values, remotes); err != nil {
			return err
		}
		if _, err := cryptCipher(values); err != nil {
			return err
		}
	}
	return nil
}

var cryptCiphers = map[string]*crypt.Cipher{}
var cryptCipherMu sync.Mutex

func cryptConnection(name string) (*crypt.Cipher, string, string, string, error) {
	if !admitted[name] {
		return nil, "", "", "", errors.New("unlock the matching credential package first")
	}
	source, original := credentialSource(name)
	source.mu.Lock()
	values := make(map[string]string)
	for k, v := range source.values.Remotes[original] {
		values[k] = v
	}
	backing, root, err := cryptBacking(values, source.values.Remotes)
	source.mu.Unlock()
	backing = sourceAlias(source, backing)
	if values["type"] != "crypt" || err != nil {
		return nil, "", "", "", errors.New("choose a valid crypt remote")
	}
	encoded, _ := json.Marshal(values)
	digest := sha256.Sum256(encoded)
	identity := hex.EncodeToString(digest[:])
	cryptCipherMu.Lock()
	defer cryptCipherMu.Unlock()
	cipher := cryptCiphers[identity]
	if cipher == nil {
		cipher, err = cryptCipher(values)
		if err != nil {
			return nil, "", "", "", err
		}
		cryptCiphers[identity] = cipher
	}
	return cipher, backing, root, identity, nil
}

func cryptList(ctx context.Context, name, dir string) ([]entry, error) {
	cipher, backing, root, _, err := cryptConnection(name)
	if err != nil {
		return nil, err
	}
	f, err := remote(ctx, backing)
	if err != nil {
		return nil, err
	}
	folder := path.Join(root, cipher.EncryptDirName(dir))
	if folder == "." {
		folder = ""
	}
	rows, err := f.List(ctx, folder)
	if err != nil {
		return nil, errors.New("encrypted folder could not be listed")
	}
	result := []entry{}
	for _, row := range rows {
		encrypted := row.Remote()
		if root != "" {
			encrypted = strings.TrimPrefix(encrypted, root+"/")
		}
		_, object := row.(fs.Object)
		var plain string
		size := row.Size()
		if object {
			plain, err = cipher.DecryptFileName(encrypted)
			if err == nil {
				size, err = cipher.DecryptedSize(size)
			}
		} else {
			plain, err = cipher.DecryptDirName(encrypted)
		}
		if err != nil || !validPath(plain) {
			return nil, errors.New("invalid encrypted folder entry")
		}
		result = append(result, entry{plain, size, !object})
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Path < result[j].Path })
	return result, nil
}

func cryptDescribe(name, encrypted, identity string) (string, *crypt.Cipher, error) {
	cipher, _, _, expected, err := cryptConnection(name)
	if err != nil {
		return "", nil, err
	}
	if identity != expected || !validPath(encrypted) || encrypted == "" {
		return "", nil, errors.New("unlock the matching crypt settings for this copy")
	}
	plain, err := cipher.DecryptFileName(encrypted)
	if err != nil || !validPath(plain) || plain == "" {
		return "", nil, errors.New("invalid encrypted filename")
	}
	return plain, cipher, nil
}

func decryptCopy(ctx context.Context, name, encrypted, identity string, fd int) (string, []byte, error) {
	plain, cipher, err := cryptDescribe(name, encrypted, identity)
	if err != nil {
		return "", nil, err
	}
	if fd < 3 {
		return "", nil, errors.New("invalid encrypted copy descriptor")
	}
	copied, err := unix.Dup(fd)
	if err != nil {
		return "", nil, errors.New("encrypted copy unavailable")
	}
	file := os.NewFile(uintptr(copied), "encrypted-copy")
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > downloadLimit {
		return "", nil, errors.New("invalid encrypted copy")
	}
	if _, err = file.Seek(0, io.SeekStart); err != nil {
		return "", nil, errors.New("encrypted copy unavailable")
	}
	reader, err := cipher.DecryptData(file)
	if err != nil {
		return "", nil, errors.New("encrypted copy authentication failed")
	}
	defer reader.Close()
	data, err := readBounded(ctx, reader, downloadLimit)
	if err != nil {
		return "", nil, errors.New("encrypted copy authentication failed or operation cancelled")
	}
	return path.Base(plain), data, nil
}

// Decrypted bytes cross the bridge in RAM; no plaintext destination descriptor.
func cryptDecode(ctx context.Context, name, encrypted, identity string, fd int, passwords ...string) (map[string]string, error) {
	plain, data, err := decryptCopy(ctx, name, encrypted, identity, fd)
	if err != nil {
		return nil, err
	}
	suffix := strings.ToLower(path.Ext(plain))
	if suffix == ".cbz" || suffix == ".zip" || suffix == ".epub" {
		password := ""
		if len(passwords) > 0 {
			password = passwords[0]
		}
		data, err = unlockArchive(ctx, data, password)
		if err != nil {
			return nil, err
		}
	}
	return map[string]string{"name": plain, "data": base64.StdEncoding.EncodeToString(data)}, nil
}

// Only the host's exclusive ciphertext staging descriptor is writable.
func cryptEncode(ctx context.Context, name, encrypted, identity, encoded string, fd int) (bool, error) {
	plain, cipher, err := cryptDescribe(name, encrypted, identity)
	if err != nil {
		return false, err
	}
	switch strings.ToLower(path.Ext(plain)) {
	case ".txt", ".md", ".markdown", ".ini":
	default:
		return false, errors.New("only text, Markdown and INI copies can be edited")
	}
	if len(encoded) > 2*packageLimit {
		return false, errors.New("text exceeds 1 MiB")
	}
	data, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil || len(data) > packageLimit {
		return false, errors.New("invalid text or text exceeds 1 MiB")
	}
	target, err := privateOutput(fd)
	if err != nil {
		return false, err
	}
	defer target.Close()
	encryptedReader, err := cipher.EncryptData(bytes.NewReader(data))
	if err != nil {
		return false, errors.New("could not encrypt document")
	}
	ciphertext, err := readBounded(ctx, encryptedReader, downloadLimit)
	if err != nil || ctx.Err() != nil {
		return false, errors.New("encryption cancelled or failed")
	}
	if _, err = target.Write(ciphertext); err != nil {
		return false, errors.New("encrypted staging write failed")
	}
	if target.Sync() != nil || ctx.Err() != nil {
		return false, errors.New("encrypted staging flush failed or cancelled")
	}
	return true, nil
}

// Local file management uses raw document bytes: inner ZIP encryption is opaque.
func cryptPath(name, value, identity string, directory, decode bool) (map[string]string, error) {
	cipher, _, _, expected, err := cryptConnection(name)
	if err != nil {
		return nil, err
	}
	if identity != "" && identity != expected {
		return nil, errors.New("crypt settings changed")
	}
	result, err := cryptMappedPath(cipher, value, directory, decode)
	return map[string]string{"path": result, "identity": expected}, err
}

type cryptPathEntry struct {
	Path      string `json:"path"`
	Directory bool   `json:"directory"`
}

// A folder page shares one credential lookup and native boundary crossing.
func cryptPaths(ctx context.Context, name, identity string, entries []cryptPathEntry) ([]string, error) {
	if len(entries) > 256 {
		return nil, errors.New("too many encrypted names")
	}
	cipher, _, _, expected, err := cryptConnection(name)
	if err != nil {
		return nil, err
	}
	if identity == "" || identity != expected {
		return nil, errors.New("crypt settings changed")
	}
	result := make([]string, 0, len(entries))
	for _, entry := range entries {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		plain, err := cryptMappedPath(cipher, entry.Path, entry.Directory, true)
		if err != nil {
			return nil, err
		}
		result = append(result, plain)
	}
	return result, nil
}

func cryptMappedPath(cipher *crypt.Cipher, value string, directory, decode bool) (string, error) {
	var err error
	if !validPath(value) {
		return "", errors.New("invalid resource path")
	}
	var result string
	if decode {
		if directory {
			result, err = cipher.DecryptDirName(value)
		} else {
			result, err = cipher.DecryptFileName(value)
		}
	} else if directory {
		result = cipher.EncryptDirName(value)
	} else {
		result = cipher.EncryptFileName(value)
	}
	if err != nil || !validPath(result) {
		return "", errors.New("invalid resource name")
	}
	return result, nil
}

func cryptRawRead(ctx context.Context, name, encrypted, identity string, fd int) (map[string]string, error) {
	plain, data, err := decryptCopy(ctx, name, encrypted, identity, fd)
	if err != nil {
		return nil, err
	}
	return map[string]string{"name": plain, "data": base64.StdEncoding.EncodeToString(data)}, nil
}

func cryptRawWrite(ctx context.Context, name, encrypted, identity string, inputFD, outputFD int, sourceRemote, sourcePath, sourceIdentity string) (bool, error) {
	_, cipher, err := cryptDescribe(name, encrypted, identity)
	if err != nil {
		return false, err
	}
	// The descriptor is opened by the host; no paths supplied to the bridge.
	if inputFD < 3 {
		return false, errors.New("invalid input descriptor")
	}
	duplicate, err := unix.Dup(inputFD)
	if err != nil {
		return false, err
	}
	source := os.NewFile(uintptr(duplicate), "transfer-input")
	defer source.Close()
	info, err := source.Stat()
	if err != nil || !info.Mode().IsRegular() {
		return false, errors.New("file is not regular")
	}
	if _, err = source.Seek(0, io.SeekStart); err != nil {
		return false, err
	}
	target, err := privateOutput(outputFD)
	if err != nil {
		return false, err
	}
	defer target.Close()
	var plaintext io.Reader = source
	var decrypted crypt.ReadSeekCloser
	if sourceRemote != "" {
		_, original, readErr := openCryptReader(ctx, sourceRemote, sourcePath, sourceIdentity, inputFD)
		if readErr != nil {
			return false, readErr
		}
		defer original.file.Close()
		decrypted, readErr = original.stream(0, -1)
		if readErr != nil {
			return false, readErr
		}
		defer decrypted.Close()
		plaintext = decrypted
	}
	input, err := cipher.EncryptData(plaintext)
	if err != nil {
		return false, err
	}
	if _, err = io.Copy(target, contextReader{ctx, input}); err != nil {
		return false, err
	}
	if closer, ok := input.(io.Closer); ok {
		defer closer.Close()
	}
	return true, target.Sync()
}
