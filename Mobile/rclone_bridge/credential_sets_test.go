package main

import (
	"archive/zip"
	"bytes"
	"context"
	"github.com/rclone/rclone/fs/object"
	"io"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func multiPackage(t *testing.T, name, kind, value string) []byte {
	t.Helper()
	var data bytes.Buffer
	archive := zip.NewWriter(&data)
	member, err := archive.Create(name + ".txt")
	if err != nil {
		t.Fatal(err)
	}
	text := "[" + name + "]\ntype=" + kind + "\n"
	if kind == "drive" {
		text += "token=" + value + "\n"
	}
	if _, err = member.Write([]byte(text)); err != nil {
		t.Fatal(err)
	}
	if err = archive.Close(); err != nil {
		t.Fatal(err)
	}
	return data.Bytes()
}
func packageAlias(t *testing.T, label, name string) string {
	t.Helper()
	set := credentialSets[packageID(label)]
	if set == nil {
		t.Fatal("missing package", label)
	}
	alias := set.aliases[name]
	if alias == "" {
		t.Fatal("missing remote", name)
	}
	return alias
}
func savedFixture(t *testing.T) (string, []byte, string) {
	t.Helper()
	clearSession()
	t.Cleanup(clearSession)
	file := filepath.Join(t.TempDir(), "credentials.bin")
	key := bytes.Repeat([]byte{17}, 32)
	id := "0123456789abcdef0123456789abcdef"
	vault, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	store = vault
	return file, key, id
}
func TestCredentialSetsMigrateOriginalSinglePackageVault(t *testing.T) {
	file, key, id := savedFixture(t)
	store.values = snapshot{Label: "Personal.zip", Remotes: map[string]map[string]string{"Original": {"type": "memory"}}}
	if err := store.Save(); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(file)
	if !bytes.HasPrefix(data, []byte("LGCV1")) {
		t.Fatal("fixture must use the original vault format")
	}
	clearSession()
	legacy, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	if err = installSavedCredentials(legacy); err != nil {
		t.Fatal(err)
	}
	if !admitted["Original"] || len(credentialSets) != 1 {
		t.Fatal("original saved package was not restored")
	}
	if _, err = importPackageMode(multiPackage(t, "Second", "memory", ""), "", "Work.zip", false); err != nil {
		t.Fatal(err)
	}
	data, _ = os.ReadFile(file)
	if !bytes.HasPrefix(data, []byte("LGCV2")) {
		t.Fatal("multi-package vault must reject older readers")
	}
	restored, err := openVault(file, id, key)
	if err != nil || len(restored.values.Packages) != 2 {
		t.Fatal("migrated packages were not saved", err)
	}
}
func TestCredentialSetsSavedAndSessionRemainLoadedAndNeverMixOnDisk(t *testing.T) {
	file, key, id := savedFixture(t)
	saved := multiPackage(t, "PersonalRemote", "drive", `{"access_token":"synthetic-personal"}`)
	legacy := multiPackage(t, "LegacyRemote", "drive", `{"access_token":"synthetic-legacy"}`)
	if _, err := importPackageMode(saved, "", "Personal.zip", false); err != nil {
		t.Fatal(err)
	}
	before, _ := os.ReadFile(file)
	if names, err := importPackageMode(legacy, "", "Legacy.zip", true); err != nil || len(names) != 2 {
		t.Fatal(names, err)
	}
	after, _ := os.ReadFile(file)
	if !bytes.Equal(before, after) {
		t.Fatal("session import changed saved ciphertext")
	}
	sessionWriter := store.connection("LegacyRemote")
	sessionWriter.Set("token", `{"access_token":"session-refresh"}`)
	after, _ = os.ReadFile(file)
	if !bytes.Equal(before, after) {
		t.Fatal("session refresh changed saved ciphertext")
	}
	savedWriter := store.connection("PersonalRemote")
	savedWriter.Set("token", `{"access_token":"saved-refresh"}`)
	if _, err := importPackageMode(multiPackage(t, "ThirdRemote", "memory", ""), "", "Third.zip", false); err != nil {
		t.Fatal(err)
	}
	if !admitted["PersonalRemote"] || !admitted["LegacyRemote"] || !admitted["ThirdRemote"] {
		t.Fatal("a package was unloaded")
	}
	restored, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	for _, item := range restored.values.Packages {
		if item.Label == "Legacy.zip" || item.Remotes["LegacyRemote"] != nil {
			t.Fatal("session credentials persisted")
		}
	}
	clearSession()
	if err := installSavedCredentials(restored); err != nil {
		t.Fatal(err)
	}
	if len(credentialSets) != 2 || admitted["LegacyRemote"] || !admitted["PersonalRemote"] || !admitted["ThirdRemote"] {
		t.Fatal("cold restore did not preserve saved-only packages")
	}
}
func TestCredentialSetsDuplicateNamesKeepSeparateIdentitiesAndAliasHints(t *testing.T) {
	savedFixture(t)
	if _, err := importPackageMode(multiPackage(t, "Books", "drive", `{"access_token":"one"}`), "", "Personal.zip", false); err != nil {
		t.Fatal(err)
	}
	personal := packageAlias(t, "Personal.zip", "Books")
	before, _ := connectionIdentity(personal)
	session := multiPackage(t, "Books", "drive", `{"access_token":"two"}`)
	if _, err := importPackageMode(session, "", "Legacy.zip", true); err != nil {
		t.Fatal(err)
	}
	legacy := packageAlias(t, "Legacy.zip", "Books")
	if personal == legacy || !admitted[personal] || !admitted[legacy] {
		t.Fatal("duplicate names overlap")
	}
	first, _ := connectionIdentity(personal)
	second, _ := connectionIdentity(legacy)
	if first != before || first == second {
		t.Fatal("connection identities retargeted")
	}
	hints := map[string]string{"Books": legacy}
	writer := store.connection(legacy)
	if _, err := importPackageWithAliases(session, "", "Legacy.zip", true, hints); err != nil {
		t.Fatal(err)
	}
	writer.Set("token", "must-not-resurrect")
	if token, _ := store.GetValue(legacy, "token"); token == "must-not-resurrect" {
		t.Fatal("retired package callback wrote into replacement")
	}
	if packageAlias(t, "Legacy.zip", "Books") != legacy {
		t.Fatal("retained alias changed")
	}
}
func TestCredentialSetsReloadSavedDoesNotDiscardSessionOrItsMode(t *testing.T) {
	file, key, id := savedFixture(t)
	if _, err := importPackageMode(multiPackage(t, "Main", "memory", ""), "", "Personal.zip", false); err != nil {
		t.Fatal(err)
	}
	if _, err := importPackageMode(multiPackage(t, "Old", "memory", ""), "", "Legacy.zip", true); err != nil {
		t.Fatal(err)
	}
	next, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	if err := installSavedCredentials(next); err != nil {
		t.Fatal(err)
	}
	if !admitted["Main"] || !admitted["Old"] || len(credentialSets) != 2 {
		t.Fatal("reload discarded a package")
	}
	if credentialSets[packageID("Legacy.zip")].storage.parent != nil {
		t.Fatal("session package promoted to saved")
	}
	if _, err := remote(context.Background(), "Main"); err != nil {
		t.Fatal(err)
	}
}

func TestCredentialSetsCryptBackingStaysWithinItsPackage(t *testing.T) {
	savedFixture(t)
	for _, item := range []struct {
		label, root string
		saved       bool
	}{{"Personal.zip", "personal", true}, {"Legacy.zip", "legacy", false}} {
		if _, err := importPackageMode(cryptPackage(t, "Cloud:"+item.root), "", item.label, !item.saved); err != nil {
			t.Fatal(err)
		}
	}
	aliases := map[string]string{}
	for _, label := range []string{"Personal.zip", "Legacy.zip"} {
		name := packageAlias(t, label, "Secret")
		aliases[label] = name
		cipher, backing, root, _, err := cryptConnection(name)
		if err != nil {
			t.Fatal(err)
		}
		if backing != packageAlias(t, label, "Cloud") {
			t.Fatal("crypt crossed package boundary")
		}
		fs, err := remote(context.Background(), backing)
		if err != nil {
			t.Fatal(err)
		}
		reader, err := cipher.EncryptData(bytes.NewReader([]byte(label)))
		if err != nil {
			t.Fatal(err)
		}
		data, err := io.ReadAll(reader)
		if err != nil {
			t.Fatal(err)
		}
		path := root + "/" + cipher.EncryptFileName("page.txt")
		if _, err := fs.Put(context.Background(), bytes.NewReader(data), object.NewStaticObjectInfo(path, time.Now(), int64(len(data)), true, nil, fs)); err != nil {
			t.Fatal(err)
		}
	}
	for label, name := range aliases {
		rows, err := cryptList(context.Background(), name, "")
		if err != nil || len(rows) != 1 || rows[0].Path != "page.txt" {
			t.Fatal(label, rows, err)
		}
	}
}
