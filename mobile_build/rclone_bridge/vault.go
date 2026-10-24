package main

import (
	"bytes"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/json"
	"errors"
	"golang.org/x/sys/unix"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
)

const vaultLimit = 2 * packageLimit

var store = newStore()
var vaultError = errors.New("Saved credentials could not be accessed safely; unlock or forget them before importing again.")

type snapshot struct {
	Label    string                       `json:"package_name"`
	Remotes  map[string]map[string]string `json:"remotes"`
	Pins     map[string]connectionPin     `json:"connection_pins,omitempty"`
	Aliases  map[string]string            `json:"aliases,omitempty"`
	Packages map[string]snapshot          `json:"packages,omitempty"`
}
type vaultStorage struct {
	mu               sync.Mutex
	values           snapshot
	path, id         string
	key, expected    []byte
	failed           bool
	generation       uint64
	parent           *vaultStorage
	packageID        string
	origins          map[string]credentialOrigin
	validatedCiphers cryptCipherCache // Transient; never part of the saved snapshot.
}

func newStore() *vaultStorage {
	return &vaultStorage{values: snapshot{Remotes: map[string]map[string]string{}}, generation: 1}
}
func (s *vaultStorage) GetSectionList() []string {
	s.mu.Lock()
	defer s.mu.Unlock()
	names := []string{}
	for n := range s.values.Remotes {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}
func (s *vaultStorage) HasSection(n string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.values.Remotes[n]
	return ok
}
func (s *vaultStorage) DeleteSection(n string) {
	if origin, ok := s.origins[n]; ok {
		origin.storage.DeleteSection(origin.name)
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.values.Remotes, n)
}
func (s *vaultStorage) GetKeyList(n string) []string {
	if origin, ok := s.origins[n]; ok {
		return origin.storage.GetKeyList(origin.name)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	keys := []string{}
	for k := range s.values.Remotes[n] {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
func (s *vaultStorage) GetValue(n, k string) (string, bool) {
	if origin, ok := s.origins[n]; ok {
		return origin.storage.GetValue(origin.name, k)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	v, ok := s.values.Remotes[n][k]
	return v, ok
}
func (s *vaultStorage) SetValue(n, k, v string) {
	if origin, ok := s.origins[n]; ok {
		origin.storage.SetValue(origin.name, k, v)
		return
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.values.Remotes[n] == nil {
		return // A retired backend must not resurrect a forgotten remote.
	}
	s.values.Remotes[n][k] = v
}
func (s *vaultStorage) DeleteKey(n, k string) bool {
	if origin, ok := s.origins[n]; ok {
		return origin.storage.DeleteKey(origin.name, k)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.values.Remotes[n][k]
	delete(s.values.Remotes[n], k)
	return ok
}
func (s *vaultStorage) Load() error { return nil } // Explicit authenticated loading occurs before installation.
func (s *vaultStorage) Serialize() (string, error) {
	return "", errors.New("plaintext credential serialization is disabled")
}
func (s *vaultStorage) Save() error {
	if s.origins != nil {
		for _, set := range credentialSets {
			if err := set.storage.Save(); err != nil {
				return err
			}
		}
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	err := s.save(s.values)
	s.failed = err != nil
	return err
}
func (s *vaultStorage) failure() bool {
	if s.origins != nil {
		for _, set := range credentialSets {
			if set.storage.failure() {
				return true
			}
		}
		return false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.failed
}
func (s *vaultStorage) detach() {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.detachLocked()
}
func (s *vaultStorage) detachLocked() {
	clear(s.key)
	s.key = nil
	s.path = ""
	s.parent = nil
	s.origins = nil
	s.validatedCiphers = nil
	s.generation++
	s.values = snapshot{Remotes: map[string]map[string]string{}}
}
func (s *vaultStorage) replace(values snapshot) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.save(values); err != nil {
		return err
	}
	s.values = values
	s.generation++
	s.failed = false
	return nil
}
func validLabel(v string) bool {
	return len(v) > 0 && len(v) <= 800 && !strings.ContainsAny(v, "/\\\x00\r\n")
}
func (s *vaultStorage) aead() (cipher.AEAD, error) {
	b, err := aes.NewCipher(s.key)
	if err != nil {
		return nil, err
	}
	return cipher.NewGCM(b)
}
func (s *vaultStorage) aad() []byte { return []byte("Logistics mobile credentials v1:" + s.id) }
func readVault(p string) ([]byte, error) {
	fd, err := unix.Open(p, unix.O_RDONLY|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, vaultError
	}
	file := os.NewFile(uintptr(fd), "encrypted-credentials")
	defer file.Close()
	var info unix.Stat_t
	if unix.Fstat(fd, &info) != nil || info.Mode&unix.S_IFMT != unix.S_IFREG || info.Nlink != 1 || info.Size > vaultLimit {
		return nil, vaultError
	}
	data, err := io.ReadAll(io.LimitReader(file, vaultLimit+1))
	if err != nil || len(data) > vaultLimit {
		return nil, vaultError
	}
	return data, nil
}
func (s *vaultStorage) save(values snapshot) error {
	if s.parent != nil {
		parent := s.parent
		parent.mu.Lock()
		defer parent.mu.Unlock()
		next := copySnapshot(parent.values)
		next.Packages = map[string]snapshot{}
		if len(parent.values.Packages) == 0 && len(parent.values.Remotes) > 0 {
			next.Packages[packageID(parent.values.Label)] = copySnapshot(parent.values)
		}
		for id, value := range parent.values.Packages {
			next.Packages[id] = copySnapshot(value)
		}
		next.Packages[s.packageID] = copySnapshot(values)
		if len(next.Packages) > 32 {
			return errors.New("up to 32 saved credential packages are supported")
		}
		next.Label = values.Label
		next.Remotes = copySnapshot(values).Remotes
		next.Pins = copySnapshot(values).Pins
		next.Aliases = values.Aliases
		if err := parent.save(next); err != nil {
			return err
		}
		parent.values = next
		return nil
	}
	if s.path == "" {
		return nil
	}
	data, err := json.Marshal(values)
	if err != nil || len(data) > vaultLimit-128 {
		return vaultError
	}
	current, err := readVault(s.path)
	if err != nil || !bytes.Equal(current, s.expected) {
		return vaultError
	}
	gcm, err := s.aead()
	if err != nil {
		return vaultError
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return vaultError
	}
	prefix := "LGCV1"
	if len(values.Packages) > 0 {
		prefix = "LGCV2"
	}
	encrypted := append([]byte(prefix), nonce...)
	encrypted = gcm.Seal(encrypted, nonce, data, s.aad())
	f, err := os.CreateTemp(filepath.Dir(s.path), ".vault-")
	if err != nil {
		return vaultError
	}
	defer os.Remove(f.Name())
	if _, err = f.Write(encrypted); err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil || closeErr != nil {
		return vaultError
	}
	current, err = readVault(s.path)
	if err != nil || !bytes.Equal(current, s.expected) {
		return vaultError
	}
	if os.Rename(f.Name(), s.path) != nil {
		return vaultError
	}
	s.expected = encrypted
	if dir, err := os.Open(filepath.Dir(s.path)); err == nil {
		_ = dir.Sync()
		_ = dir.Close()
	}
	return nil
}
func openVault(p, id string, key []byte) (*vaultStorage, error) {
	if !filepath.IsAbs(p) || filepath.Base(p) != "credentials.bin" || len(id) != 32 || strings.Trim(id, "0123456789abcdef") != "" || len(key) != 32 {
		return nil, vaultError
	}
	parent, err := os.Lstat(filepath.Dir(p))
	if err != nil || !parent.IsDir() || parent.Mode()&os.ModeSymlink != 0 {
		return nil, vaultError
	}
	s := newStore()
	s.path = p
	s.id = id
	s.key = append([]byte(nil), key...)
	encrypted, err := readVault(p)
	if err != nil {
		return nil, err
	}
	s.expected = encrypted
	if encrypted == nil {
		return s, nil
	}
	gcm, err := s.aead()
	if err != nil || len(encrypted) < 5+gcm.NonceSize()+gcm.Overhead() || (string(encrypted[:5]) != "LGCV1" && string(encrypted[:5]) != "LGCV2") {
		return nil, vaultError
	}
	nonce := encrypted[5 : 5+gcm.NonceSize()]
	plain, err := gcm.Open(nil, nonce, encrypted[5+gcm.NonceSize():], s.aad())
	if err != nil {
		return nil, vaultError
	}
	s.validatedCiphers = snapshotCryptCiphers(nil)
	if json.Unmarshal(plain, &s.values) != nil || validateCredentialEnvelope(s.values, s.validatedCiphers) != nil {
		return nil, vaultError
	}

	return s, nil
}
func vaultInfo() map[string]any {
	packages := credentialPackageInfo()
	saved := false
	for _, item := range packages {
		if item["saved"].(bool) {
			saved = true
		}
	}
	return map[string]any{"package_name": latestCredential, "remotes": store.GetSectionList(), "saved": saved, "save_failed": store.failure(), "packages": packages}
}

// Each native backend captures its storage and generation. A late OAuth refresh
// from a retired backend can neither modify a replacement package nor recreate
// forgotten persistence, even if it uses the same human remote name.
type connectionConfig struct {
	storage    *vaultStorage
	generation uint64
	name       string
}

func (s *vaultStorage) connection(name string) connectionConfig {
	if origin, ok := s.origins[name]; ok {
		return origin.storage.connection(origin.name)
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return connectionConfig{s, s.generation, name}
}
func (c connectionConfig) Get(key string) (string, bool) {
	c.storage.mu.Lock()
	defer c.storage.mu.Unlock()
	if c.generation != c.storage.generation {
		return "", false
	}
	value, ok := c.storage.values.Remotes[c.name][key]
	return value, ok
}
func (c connectionConfig) Set(key, value string) {
	s := c.storage
	s.mu.Lock()
	defer s.mu.Unlock()
	if c.generation != s.generation || s.values.Remotes[c.name] == nil {
		return
	}
	kind := s.values.Remotes[c.name]["type"]
	if !strings.Contains(" "+allowed[kind]+" ", " "+key+" ") {
		return
	}
	s.values.Remotes[c.name][key] = value
	s.failed = s.save(s.values) != nil
}
