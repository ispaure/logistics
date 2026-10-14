package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
)

// Return an opaque configuration identity, never credentials or capability handles.
// This performs no network access and changes when the remote or its backing
// configuration changes, preventing a saved local pull from silently retargeting.
func connectionIdentity(name string) (string, error) {
	if !admitted[name] {
		return "", errors.New("unlock the matching credential package first")
	}
	store.mu.Lock()
	defer store.mu.Unlock()
	values, ok := store.values.Remotes[name]
	if !ok {
		return "", errors.New("remote is unavailable")
	}
	selected := map[string]map[string]string{name: values}
	if values["type"] == "crypt" {
		backing, _, err := cryptBacking(values, store.values.Remotes)
		if err != nil {
			return "", err
		}
		selected[backing] = store.values.Remotes[backing]
	}
	data, err := json.Marshal(selected)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(data)
	return hex.EncodeToString(digest[:]), nil
}
