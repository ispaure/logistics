package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
)

type connectionPin struct {
	Signature string `json:"signature"`
	Identity  string `json:"identity"`
}

func validDigest(value string) bool {
	return len(value) == 64 && strings.Trim(value, "0123456789abcdef") == ""
}

func selectedConnection(remotes map[string]map[string]string, name string, omitToken bool) (map[string]map[string]string, bool, error) {
	values, ok := remotes[name]
	if !ok {
		return nil, false, errors.New("remote is unavailable")
	}
	names := []string{name}
	if values["type"] == "crypt" {
		backing, _, err := cryptBacking(values, remotes)
		if err != nil {
			return nil, false, err
		}
		names = append(names, backing)
	}
	selected := map[string]map[string]string{}
	oauth := false
	for _, key := range names {
		value := remotes[key]
		kind := value["type"]
		refreshable := (kind == "drive" || kind == "dropbox" || kind == "onedrive") && value["token"] != ""
		oauth = oauth || refreshable
		copied := map[string]string{}
		for k, v := range value {
			if !(omitToken && refreshable && k == "token") {
				copied[k] = v
			}
		}
		selected[key] = copied
	}
	return selected, oauth, nil
}

func connectionHash(value map[string]map[string]string) string {
	data, _ := json.Marshal(value)
	digest := sha256.Sum256(data)
	return hex.EncodeToString(digest[:])
}

func initialConnectionPins(remotes map[string]map[string]string) map[string]connectionPin {
	pins := map[string]connectionPin{}
	for name := range remotes {
		selected, oauth, err := selectedConnection(remotes, name, false)
		if err != nil || !oauth {
			continue
		}
		signature, _, err := selectedConnection(remotes, name, true)
		if err != nil {
			continue
		}
		pins[name] = connectionPin{connectionHash(signature), connectionHash(selected)}
	}
	return pins
}

// Stable identities start with the original full configuration hash. OAuth
// refresh updates its encrypted vault without retargeting an existing copy.
func connectionIdentity(name string) (string, error) {
	if !admitted[name] {
		return "", errors.New("unlock the matching credential package first")
	}
	source, original := credentialSource(name)
	source.mu.Lock()
	defer source.mu.Unlock()
	name = original
	selected, oauth, err := selectedConnection(source.values.Remotes, name, false)
	if err != nil {
		return "", err
	}
	identity := connectionHash(selected)
	if !oauth {
		return identity, nil
	}
	scope, _, err := selectedConnection(source.values.Remotes, name, true)
	if err != nil {
		return "", err
	}
	signature := connectionHash(scope)
	if pin, ok := source.values.Pins[name]; ok && pin.Signature == signature {
		return pin.Identity, nil
	}
	// Import replaces pins, including a change of account. First use also
	// migrates an older vault while keeping its current full-hash identity.
	if source.values.Pins == nil {
		source.values.Pins = map[string]connectionPin{}
	}
	source.values.Pins[name] = connectionPin{signature, identity}
	if err := source.save(source.values); err != nil {
		source.failed = true
		return "", err
	}
	return identity, nil
}
