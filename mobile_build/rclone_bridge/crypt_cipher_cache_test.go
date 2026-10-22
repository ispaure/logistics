package main

import (
	"archive/zip"
	"bytes"
	"fmt"
	"sync"
	"testing"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs/config/obscure"
)

func sharedCipherPackage(t *testing.T, password string) []byte {
	t.Helper()
	var data bytes.Buffer
	archive := zip.NewWriter(&data)
	member, _ := archive.Create("Cloud.txt")
	fmt.Fprint(member, "[Cloud]\ntype=memory\n")
	for index := range 16 {
		name := fmt.Sprintf("Secret%02d", index)
		member, _ := archive.Create(name + ".txt")
		// Rclone obscure uses a random IV. Equal passwords can have different
		// config spellings, and the backing roots must remain distinct.
		fmt.Fprintf(member, "[%s]\ntype=crypt\nremote=Cloud:folder-%d\npassword=%s\n",
			name, index, obscure.MustObscure(password))
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	return data.Bytes()
}

func assertSharedCipher(t *testing.T, expected *crypt.Cipher) *crypt.Cipher {
	t.Helper()
	identities := map[string]bool{}
	for index := range 16 {
		cipher, _, root, identity, err := cryptConnection(fmt.Sprintf("Secret%02d", index))
		if err != nil {
			t.Fatal(err)
		}
		if expected == nil {
			expected = cipher
		}
		if cipher != expected || root != fmt.Sprintf("folder-%d", index) || identities[identity] {
			t.Fatal("cipher reuse changed connection identities or repeated derivation")
		}
		identities[identity] = true
	}
	if len(cryptCiphers) != 1 {
		t.Fatal("expected one cipher for 16 equivalent crypto configurations")
	}
	return expected
}

func TestCipherReuseAcrossValidationFolderDiscoveryAndCredentialReplacement(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackageMode(sharedCipherPackage(t, "synthetic-first"), "", "Shared.zip", true); err != nil {
		t.Fatal(err)
	}
	if len(cryptCiphers) != 1 {
		t.Fatal("validated cipher was discarded before folder discovery")
	}
	var validated *crypt.Cipher
	for _, cipher := range cryptCiphers {
		validated = cipher
	}
	first := assertSharedCipher(t, validated)
	// Re-obscured passwords and repeated loading reuse the still-admitted key.
	if _, err := importPackageMode(sharedCipherPackage(t, "synthetic-first"), "", "Shared.zip", true); err != nil {
		t.Fatal(err)
	}
	assertSharedCipher(t, first)
	// A rejected candidate cannot evict or publish keys into the active cache.
	aliases := map[string]string{"Secret00": "invalid:name"}
	if _, err := importPackageWithAliases(sharedCipherPackage(t, "synthetic-rejected"), "", "Shared.zip", true, aliases); err == nil {
		t.Fatal("expected candidate alias rejection")
	}
	assertSharedCipher(t, first)
	if _, err := importPackageMode(sharedCipherPackage(t, "synthetic-second"), "", "Shared.zip", true); err != nil {
		t.Fatal(err)
	}
	second := assertSharedCipher(t, nil)
	if second == first {
		t.Fatal("changed credentials reused a retired cipher")
	}
	clearSession()
	if len(cryptCiphers) != 0 {
		t.Fatal("locking retained cached keys")
	}
	if _, _, _, _, err := cryptConnection("Secret00"); err == nil {
		t.Fatal("locked connection remained admitted")
	}
}

func TestSavedVaultValidationPublishesPreparedCiphersWithoutAnotherDerivation(t *testing.T) {
	file, key, id := savedFixture(t)
	if _, err := importPackageMode(sharedCipherPackage(t, "synthetic-saved"), "", "Saved.zip", false); err != nil {
		t.Fatal(err)
	}
	clearSession()
	restored, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	if len(restored.validatedCiphers) != 1 || len(cryptCiphers) != 0 {
		t.Fatal("vault validation repeated derivation or published before admission")
	}
	var validated *crypt.Cipher
	for _, cipher := range restored.validatedCiphers {
		validated = cipher
	}
	if err := installSavedCredentials(restored); err != nil {
		t.Fatal(err)
	}
	assertSharedCipher(t, validated)
	if restored.validatedCiphers != nil {
		t.Fatal("published vault retained a second cache owner")
	}
	clearSession()
	if len(cryptCiphers) != 0 {
		t.Fatal("vault lock retained cached keys")
	}
}

func TestCipherSettingsDoNotAliasDifferentEncryptionOptions(t *testing.T) {
	base := map[string]string{"type": "crypt", "password": obscure.MustObscure("synthetic"), "remote": "Cloud:first"}
	cache := make(cryptCipherCache)
	first, err := cache.get(base)
	if err != nil {
		t.Fatal(err)
	}
	for _, change := range []map[string]string{
		{"password": obscure.MustObscure("different")},
		{"password2": obscure.MustObscure("different-salt")},
		{"filename_encryption": "off"},
		{"directory_name_encryption": "false"},
		{"filename_encoding": "base64"},
		{"suffix": ".different"},
		{"pass_bad_blocks": "true"},
	} {
		values := map[string]string{}
		for k, v := range base {
			values[k] = v
		}
		for k, v := range change {
			values[k] = v
		}
		cipher, err := cache.get(values)
		if err != nil || cipher == first {
			t.Fatal("different crypto settings shared a cipher", err)
		}
	}
	count := len(cache)
	if _, err := cache.get(map[string]string{"password": "invalid"}); err == nil || len(cache) != count {
		t.Fatal("invalid settings entered the cache")
	}
}

func TestSharedCipherSupportsConcurrentFolderNameReads(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackageMode(sharedCipherPackage(t, "synthetic-concurrent"), "", "Shared.zip", true); err != nil {
		t.Fatal(err)
	}
	var workers sync.WaitGroup
	errors := make(chan error, 8)
	for worker := range 8 {
		workers.Go(func() {
			for index := range 50 {
				cipher, _, _, _, err := cryptConnection(fmt.Sprintf("Secret%02d", worker))
				if err != nil {
					errors <- err
					return
				}
				name := fmt.Sprintf("synthetic-%d-%d.txt", worker, index)
				decoded, err := cipher.DecryptFileName(cipher.EncryptFileName(name))
				if err != nil || decoded != name {
					errors <- fmt.Errorf("concurrent filename round trip failed")
					return
				}
			}
		})
	}
	workers.Wait()
	close(errors)
	for err := range errors {
		t.Fatal(err)
	}
	assertSharedCipher(t, nil)
}

func TestPrepareDistinctCiphersMatchesSequentialAndReusesExisting(t *testing.T) {
	remotes := map[string]map[string]string{}
	for index := range 16 {
		remotes[fmt.Sprintf("Secret%d", index)] = map[string]string{
			"type": "crypt", "remote": fmt.Sprintf("Cloud:folder%d", index),
			"password": obscure.MustObscure(fmt.Sprintf("synthetic-%d", index%8)),
		}
	}
	cache := cryptCipherCache{}
	if err := cache.prepare(remotes); err != nil {
		t.Fatal(err)
	}
	if len(cache) != 8 {
		t.Fatalf("got %d ciphers for eight distinct configurations", len(cache))
	}
	before := cryptCipherCache{}
	for key, cipher := range cache {
		before[key] = cipher
	}
	for _, values := range remotes {
		got, err := cache.get(values)
		if err != nil {
			t.Fatal(err)
		}
		want, err := cryptCipher(values)
		if err != nil {
			t.Fatal(err)
		}
		if got.EncryptFileName("folder/check.txt") != want.EncryptFileName("folder/check.txt") {
			t.Fatal("parallel preparation changed encryption")
		}
	}
	if err := cache.prepare(remotes); err != nil {
		t.Fatal(err)
	}
	for key, cipher := range before {
		if cache[key] != cipher {
			t.Fatal("prepared cipher was replaced")
		}
	}
}

func TestPrepareFailedBatchDoesNotPublishPartialCiphers(t *testing.T) {
	cache := cryptCipherCache{}
	remotes := map[string]map[string]string{
		"Valid":   {"type": "crypt", "password": obscure.MustObscure("synthetic-valid")},
		"Invalid": {"type": "crypt", "password": obscure.MustObscure("synthetic-invalid"), "filename_encryption": "invalid"},
	}
	if err := cache.prepare(remotes); err == nil {
		t.Fatal("invalid cipher configuration accepted")
	}
	if len(cache) != 0 {
		t.Fatal("failed batch published partial cipher results")
	}
}
