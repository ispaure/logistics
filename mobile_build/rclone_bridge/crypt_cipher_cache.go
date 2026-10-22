package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"runtime"
	"sync"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs/config/obscure"
)

// Candidate validation owns a private cache. Only successful credential
// publication can transfer its ciphers into the active in-memory cache.
type cryptCipherCache map[string]*crypt.Cipher

func cryptCipherKey(values map[string]string) (string, error) {
	settings := make(map[string]string, len(values))
	for key, value := range values {
		// The backing path is part of connection identity, but NewCipher does
		// not use it. Preserve every other setting, including filename modes.
		if key != "remote" {
			settings[key] = value
		}
	}
	for _, key := range []string{"password", "password2"} {
		if settings[key] != "" {
			plain, err := obscure.Reveal(settings[key])
			if err != nil {
				return "", err
			}
			settings[key] = plain
		}
	}
	data, _ := json.Marshal(settings)
	defer clear(data)
	digest := sha256.Sum256(data)
	return hex.EncodeToString(digest[:]), nil
}

func (cache cryptCipherCache) get(values map[string]string) (*crypt.Cipher, error) {
	key, err := cryptCipherKey(values)
	if err != nil {
		return nil, err
	}
	if cipher := cache[key]; cipher != nil {
		return cipher, nil
	}
	cipher, err := cryptCipher(values)
	if err == nil {
		cache[key] = cipher
	}
	return cipher, err
}

func snapshotCryptCiphers(validated cryptCipherCache) cryptCipherCache {
	cryptCipherMu.Lock()
	defer cryptCipherMu.Unlock()
	result := make(cryptCipherCache, len(cryptCiphers)+len(validated))
	for key, cipher := range cryptCiphers {
		result[key] = cipher
	}
	for key, cipher := range validated {
		result[key] = cipher
	}
	return result
}

func publishCryptCiphers(candidates cryptCipherCache) {
	cryptCipherMu.Lock()
	defer cryptCipherMu.Unlock()
	// Retain only settings referenced by the newly admitted credential view.
	// Removed, replaced, rejected and shadowed packages cannot leave keys here.
	clear(cryptCiphers)
	for _, values := range store.values.Remotes {
		if values["type"] != "crypt" {
			continue
		}
		key, err := cryptCipherKey(values)
		if err == nil && candidates[key] != nil {
			cryptCiphers[key] = candidates[key]
		}
	}
}

// Prepare distinct missing ciphers in a bounded batch. Workers never access the
// candidate map; a failed batch publishes nothing. Four scrypt derivations use
// at most 64 MiB of scrypt working memory, independent of the remote count.
func (cache cryptCipherCache) prepare(remotes map[string]map[string]string) error {
	type pendingCipher struct {
		key    string
		values map[string]string
		cipher *crypt.Cipher
		err    error
	}
	pending := []*pendingCipher{}
	seen := map[string]bool{}
	for _, values := range remotes {
		if values["type"] != "crypt" {
			continue
		}
		key, err := cryptCipherKey(values)
		if err != nil {
			return err
		}
		if cache[key] == nil && !seen[key] {
			seen[key] = true
			pending = append(pending, &pendingCipher{key: key, values: values})
		}
	}
	workers := min(4, runtime.GOMAXPROCS(0), len(pending))
	jobs := make(chan *pendingCipher)
	var group sync.WaitGroup
	for range workers {
		group.Go(func() {
			for job := range jobs {
				job.cipher, job.err = cryptCipher(job.values)
			}
		})
	}
	for _, job := range pending {
		jobs <- job
	}
	close(jobs)
	group.Wait()
	for _, job := range pending {
		if job.err != nil {
			return job.err
		}
	}
	for _, job := range pending {
		cache[job.key] = job.cipher
	}
	return nil
}
