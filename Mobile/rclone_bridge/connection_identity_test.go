package main

import (
	"testing"
)

func TestConnectionIdentityRequiresAdmissionAndDetectsReplacement(t *testing.T) {
	name := "identity-fixture"
	admitted[name] = true
	store.mu.Lock()
	store.values.Remotes[name] = map[string]string{"type": "memory"}
	store.mu.Unlock()
	first, err := connectionIdentity(name)
	if err != nil || len(first) != 64 {
		t.Fatal(first, err)
	}
	second, err := connectionIdentity(name)
	if err != nil || second != first {
		t.Fatal("identity changed without configuration changes")
	}
	store.mu.Lock()
	store.values.Remotes[name]["type"] = "drive"
	store.values.Remotes[name]["token"] = "synthetic secret"
	store.mu.Unlock()
	changed, err := connectionIdentity(name)
	if err != nil || changed == first {
		t.Fatal("replacement retained the previous identity")
	}
	delete(admitted, name)
	if _, err := connectionIdentity(name); err == nil {
		t.Fatal("locked identity was disclosed")
	}
	store.mu.Lock()
	delete(store.values.Remotes, name)
	store.mu.Unlock()
}
