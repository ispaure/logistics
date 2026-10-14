package main

import (
	"bytes"
	"path/filepath"
	"testing"
)

func TestOAuthIdentitySurvivesRefreshAndEncryptedVaultRestoration(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	file := filepath.Join(t.TempDir(), "credentials.bin")
	key := bytes.Repeat([]byte{71}, 32)
	id := "0123456789abcdef0123456789abcdef"
	next, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	remotes := map[string]map[string]string{"Account": {"type": "drive", "token": "original-account-token"}}
	if err = next.replace(snapshot{Label: "Accounts.zip", Remotes: remotes, Pins: initialConnectionPins(remotes)}); err != nil {
		t.Fatal(err)
	}
	store = next
	admitted["Account"] = true
	original, err := connectionIdentity("Account")
	if err != nil {
		t.Fatal(err)
	}
	store.connection("Account").Set("token", "refreshed-account-token")
	refreshed, err := connectionIdentity("Account")
	if err != nil || refreshed != original {
		t.Fatal("refresh changed the copy identity", err)
	}
	restored, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	store = restored
	reopened, err := connectionIdentity("Account")
	if err != nil || reopened != original {
		t.Fatal("vault restoration changed the copy identity", err)
	}
	replacement := map[string]map[string]string{"Account": {"type": "drive", "token": "different-account-token"}}
	if err = store.replace(snapshot{Label: "Accounts.zip", Remotes: replacement, Pins: initialConnectionPins(replacement)}); err != nil {
		t.Fatal(err)
	}
	changed, err := connectionIdentity("Account")
	if err != nil || changed == original {
		t.Fatal("account replacement reused its identity", err)
	}
}

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
