package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/hex"
	"errors"
)

// Encrypt retained ZIP bytes independently of the live rclone credential store.
func protectPackage(data, key []byte, id string, decode bool) ([]byte, error) {
	identity, err := hex.DecodeString(id)
	if err != nil || len(identity) != 32 || len(key) != 32 || len(data) > packageLimit+64 {
		return nil, errors.New("invalid retained credential package")
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	aad := []byte("Logistics retained ZIP v1:" + id)
	if decode {
		if len(data) < gcm.NonceSize()+gcm.Overhead() {
			return nil, errors.New("invalid retained credential package")
		}
		return gcm.Open(nil, data[:gcm.NonceSize()], data[gcm.NonceSize():], aad)
	}
	if len(data) > packageLimit {
		return nil, errors.New("credential package exceeds limits")
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err = rand.Read(nonce); err != nil {
		return nil, err
	}
	return gcm.Seal(nonce, nonce, data, aad), nil
}
