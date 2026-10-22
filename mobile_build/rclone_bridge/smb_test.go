package main

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/config/obscure"
)

func TestSMBRegistrationAndCredentialValidation(t *testing.T) {
	if _, err := fs.Find("smb"); err != nil {
		t.Fatal(err)
	}
	pass, _ := obscure.Obscure("share secret")
	if _, _, err := parseCredential([]byte("[Mac]\ntype=smb\nhost=192.168.1.2\nuser=marc\npass=" + pass + "\nport=445\ndomain=WORKGROUP\n")); err != nil {
		t.Fatal(err)
	}
	for _, extra := range []string{"host=smb://mac/Share", "host=mac/Share", "port=0", "port=65536", "port=invalid", "kerberos_ccache=/private/file", "use_kerberos=true", "pass=plaintext"} {
		input := "[Mac]\ntype=smb\nuser=marc\n"
		if len(extra) < 5 || extra[:5] != "host=" {
			input += "host=mac.local\n"
		}
		if _, _, err := parseCredential([]byte(input + extra + "\n")); err == nil {
			t.Fatalf("accepted %s", extra)
		}
	}
}

func TestAddSMBPreservesConnectionsAndRejectsDuplicates(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if err := store.replace(snapshot{Label: "Existing.zip", Remotes: map[string]map[string]string{"Existing": {"type": "memory"}}}); err != nil {
		t.Fatal(err)
	}
	admitted["Existing"] = true
	before, _ := connectionIdentity("Existing")
	names, err := addSMB("Mac", "mac.local", "marc", "secret", "WORKGROUP", "445", false)
	if err != nil || len(names) != 2 {
		t.Fatalf("append: %v %v", names, err)
	}
	after, _ := connectionIdentity("Existing")
	if before != after || !admitted["Existing"] || !admitted["Mac"] {
		t.Fatal("existing connection changed")
	}
	hidden, _ := store.GetValue("Mac", "pass")
	if plain, err := obscure.Reveal(hidden); err != nil || plain != "secret" {
		t.Fatal("password was not obscured")
	}
	if _, err := addSMB("Mac", "other.local", "guest", "", "", "445", false); err == nil {
		t.Fatal("duplicate overwrote connection")
	}
	host, _ := store.GetValue("Mac", "host")
	if host != "mac.local" {
		t.Fatal("failed addition changed connection")
	}
}

func TestSMBSessionAdditionPreservesSavedVault(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	key := make([]byte, 32)
	p := t.TempDir() + "/credentials.bin"
	next, err := openVault(p, "0123456789abcdef0123456789abcdef", key)
	if err != nil {
		t.Fatal(err)
	}
	store = next
	if _, err := addSMB("Saved", "192.168.1.2", "alice", "first server password", "WORKGROUP", "445", false); err != nil {
		t.Fatal(err)
	}
	if _, err := addSMB("Second", "192.168.1.4", "bob", "second server password", "WORKGROUP", "445", false); err != nil {
		t.Fatal(err)
	}
	encrypted, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{"alice", "bob", "first server password", "second server password"} {
		if bytes.Contains(encrypted, []byte(secret)) {
			t.Fatal("credential leaked into saved vault")
		}
	}
	if _, err := addSMB("Temporary", "192.168.1.3", "guest", "", "WORKGROUP", "445", true); err != nil {
		t.Fatal(err)
	}
	if store.path != "" || !admitted["Saved"] || !admitted["Temporary"] {
		t.Fatal("session state incorrect")
	}
	saved, err := openVault(p, "0123456789abcdef0123456789abcdef", key)
	if err != nil {
		t.Fatal(err)
	}
	defer saved.detach()
	if !saved.HasSection("Saved") || !saved.HasSection("Second") || saved.HasSection("Temporary") {
		t.Fatal("session connection persisted")
	}
	for name, want := range map[string]string{"Saved": "first server password", "Second": "second server password"} {
		hidden, _ := saved.GetValue(name, "pass")
		if plain, err := obscure.Reveal(hidden); err != nil || plain != want {
			t.Fatal("server password not restored")
		}
	}
	if reply := dispatch("add_smb", `{"remote":"Bad","host":"smb://bad","user":"guest"}`); !json.Valid([]byte(reply)) {
		t.Fatal("invalid bridge response")
	}
}
