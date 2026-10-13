package main

import (
	"bytes"
	"encoding/json"
	"github.com/rclone/rclone/fs/config"
	"os"
	"path/filepath"
	"testing"
)

func TestEncryptedVaultRefreshRestoreTamperAndForget(t *testing.T) {
	clearSession()
	defer clearSession()
	p := filepath.Join(t.TempDir(), "credentials.bin")
	id := "0123456789abcdef0123456789abcdef"
	key := bytes.Repeat([]byte{73}, 32)
	next, err := openVault(p, id, key)
	if err != nil {
		t.Fatal(err)
	}
	store = next
	config.SetData(store)
	data, _ := os.ReadFile("testdata/credentials-aes256.zip")
	if _, err := importPackage(data, "synthetic-fixture-password", "Accounts.zip"); err != nil {
		t.Fatal(err)
	}
	if err := config.SetValueAndSave("Fixture", "token", "synthetic-refreshed-token"); err != nil {
		t.Fatal(err)
	}
	// Fixture memory backend would not accept token at restore. Use drive settings
	// to exercise the actual rclone token-save callback without contacting a cloud.
	store.SetValue("Fixture", "type", "drive")
	if err := store.Save(); err != nil {
		t.Fatal(err)
	}
	cipher, _ := os.ReadFile(p)
	for _, secret := range [][]byte{[]byte("Accounts.zip"), []byte("synthetic-refreshed-token"), key} {
		if bytes.Contains(cipher, secret) {
			t.Fatal("plaintext leaked into ciphertext")
		}
	}
	clearSession()
	reopened, err := openVault(p, id, key)
	if err != nil {
		t.Fatal(err)
	}
	if v, _ := reopened.GetValue("Fixture", "token"); v != "synthetic-refreshed-token" {
		t.Fatal("refresh not retained")
	}
	if reopened.values.Label != "Accounts.zip" {
		t.Fatal("source label lost")
	}
	if _, err := openVault(p, id, bytes.Repeat([]byte{74}, 32)); err == nil {
		t.Fatal("wrong key accepted")
	}
	corrupt := append([]byte(nil), cipher...)
	corrupt[len(corrupt)-1] ^= 1
	_ = os.WriteFile(p, corrupt, 0600)
	if _, err := openVault(p, id, key); err == nil {
		t.Fatal("tampered vault accepted")
	}
	reopened.SetValue("Fixture", "token", "new-token")
	if reopened.Save() == nil || !reopened.failure() {
		t.Fatal("concurrent edit overwritten")
	}
	after, _ := os.ReadFile(p)
	if !bytes.Equal(after, corrupt) {
		t.Fatal("prior ciphertext replaced")
	}
	reopened.detach()
	_ = os.Remove(p)
	if err := reopened.Save(); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(p); !os.IsNotExist(err) {
		t.Fatal("detached token refresh recreated vault")
	}
}

func TestFailedPersistentImportRetainsPriorSession(t *testing.T) {
	clearSession()
	defer clearSession()
	p := filepath.Join(t.TempDir(), "credentials.bin")
	next, err := openVault(p, "0123456789abcdef0123456789abcdef", bytes.Repeat([]byte{42}, 32))
	if err != nil {
		t.Fatal(err)
	}
	store = next
	config.SetData(store)
	data, _ := os.ReadFile("testdata/credentials-aes256.zip")
	if _, err = importPackage(data, "synthetic-fixture-password", "First.zip"); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(p, []byte("external change"), 0600)
	if _, err = importPackage(data, "synthetic-fixture-password", "Second.zip"); err == nil {
		t.Fatal("conflict ignored")
	}
	if !admitted["Fixture"] || store.values.Label != "First.zip" {
		t.Fatal("failed import destroyed prior session")
	}
	var info map[string]any
	_ = json.Unmarshal([]byte(dispatch("vault_info", "{}")), &info)
	if info["ok"] != true {
		t.Fatal("metadata unavailable")
	}
}

func TestSessionOnlyImportPreservesSavedCiphertextAndRejectsLinkedVault(t *testing.T) {
	clearSession()
	defer clearSession()
	root := t.TempDir()
	p := filepath.Join(root, "credentials.bin")
	key := bytes.Repeat([]byte{42}, 32)
	id := "0123456789abcdef0123456789abcdef"
	next, err := openVault(p, id, key)
	if err != nil {
		t.Fatal(err)
	}
	store = next
	config.SetData(store)
	data, _ := os.ReadFile("testdata/credentials-aes256.zip")
	if _, err = importPackageMode(data, "synthetic-fixture-password", "Saved.zip", false); err != nil {
		t.Fatal(err)
	}
	saved, _ := os.ReadFile(p)
	if _, err = importPackageMode(data, "wrong", "Session.zip", true); err == nil {
		t.Fatal("wrong password accepted")
	}
	if store.values.Label != "Saved.zip" || store.path != p {
		t.Fatal("failed session import replaced saved session")
	}
	if _, err = importPackageMode(data, "synthetic-fixture-password", "Session.zip", true); err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(p)
	if !bytes.Equal(saved, after) || store.path != "" {
		t.Fatal("session import modified saved ciphertext")
	}
	if recovered, err := openVault(p, id, key); err != nil || recovered.values.Label != "Saved.zip" {
		t.Fatal("saved package did not restore")
	}
	original := filepath.Join(root, "original")
	if os.Rename(p, original) != nil {
		t.Fatal("rename fixture")
	}
	if os.Symlink(original, p) != nil {
		t.Fatal("symlink fixture")
	}
	if _, err := openVault(p, id, key); err == nil {
		t.Fatal("linked ciphertext accepted")
	}
}

func TestRetiredConnectionCannotWriteTokensToReplacementOrForgottenVault(t *testing.T) {
	s := newStore()
	p := filepath.Join(t.TempDir(), "credentials.bin")
	s.path = p
	s.id = "0123456789abcdef0123456789abcdef"
	s.key = bytes.Repeat([]byte{42}, 32)
	first := snapshot{Label: "First.zip", Remotes: map[string]map[string]string{"Account": {"type": "drive", "token": "first-token"}}}
	if err := s.replace(first); err != nil {
		t.Fatal(err)
	}
	retired := s.connection("Account")
	retired.Set("token", "refreshed-first-token")
	restored, err := openVault(p, s.id, s.key)
	if err != nil {
		t.Fatal(err)
	}
	if token, _ := restored.GetValue("Account", "token"); token != "refreshed-first-token" {
		t.Fatal("bound refresh not persisted")
	}
	next := snapshot{Label: "Second.zip", Remotes: map[string]map[string]string{"Account": {"type": "drive", "token": "second-token"}}}
	if err := s.replace(next); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(p)
	retired.Set("token", "late-first-token")
	if token, _ := s.GetValue("Account", "token"); token != "second-token" {
		t.Fatal("retired callback replaced active token")
	}
	after, _ := os.ReadFile(p)
	if !bytes.Equal(before, after) {
		t.Fatal("retired callback modified vault")
	}
	active := s.connection("Account")
	s.detach()
	_ = os.Remove(p)
	active.Set("token", "forgotten-token")
	if _, err := os.Stat(p); !os.IsNotExist(err) {
		t.Fatal("retired callback recreated forgotten vault")
	}
}
