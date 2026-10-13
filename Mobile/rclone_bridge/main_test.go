package main

import (
	"bytes"
	"context"
	"github.com/yeka/zip"
	"io"
	"os"
	"strings"
	"testing"
)

func TestNativeEngineAndAuthenticatedCredentialPackage(t *testing.T) {
	if _, err := selfCheck(context.Background()); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile("testdata/credentials-aes256.zip")
	if err != nil {
		t.Fatal(err)
	}
	names, err := importPackage(data, "synthetic-fixture-password")
	if err != nil || len(names) != 1 || names[0] != "Fixture" {
		t.Fatalf("import failed: %v", err)
	}
	if _, err := importPackage(data, "wrong password"); err == nil {
		t.Fatal("wrong password accepted")
	}
	if !admitted["Fixture"] {
		t.Fatal("failed import replaced prior session")
	}
	f, err := remote(context.Background(), "Fixture")
	if err != nil {
		t.Fatal(err)
	}
	rows, err := list(context.Background(), "Fixture", "")
	if err != nil {
		t.Fatal(err)
	}
	_ = f
	_ = rows

	file, err := os.CreateTemp(t.TempDir(), "private-copy-")
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	_, err = selfCheck(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	count, err := readInto(context.Background(), "Fixture", "logistics-native-check/fixture.txt", int(file.Fd()))
	if err != nil || count != int64(len("Native rclone fixture\n")) {
		t.Fatalf("streamed download: %d %v", count, err)
	}
	_, _ = file.Seek(0, 0)
	content, err := io.ReadAll(file)
	if err != nil || string(content) != "Native rclone fixture\n" {
		t.Fatal("private copy differed")
	}
	if _, err := readInto(context.Background(), "Fixture", "logistics-native-check/fixture.txt", int(file.Fd())); err == nil {
		t.Fatal("existing destination accepted")
	}
	if _, err := readInto(context.Background(), "Fixture", "../escape", 0); err == nil {
		t.Fatal("unsafe path accepted")
	}
	if _, err := remote(context.Background(), ":local"); err == nil {
		t.Fatal("arbitrary filesystem accepted")
	}
	if !strings.Contains(dispatch("core/command", "{}"), `"ok":false`) {
		t.Fatal("command endpoint accepted")
	}
	// Authenticate every member before any config changes, including forged
	// ciphertext with a valid-looking password verifier.
	forged := append([]byte(nil), data...)
	for i := len(forged) / 3; i < len(forged)/2; i++ {
		forged[i] ^= 0x55
	}
	if _, err := importPackage(forged, "synthetic-fixture-password"); err == nil {
		t.Fatal("corrupt archive accepted")
	}
}

func TestCredentialInputBoundsAndUnsafeSettings(t *testing.T) {
	for _, text := range []string{
		"[x]\ntype=local\n", "[x]\ntype=webdav\nurl=http://example.invalid\n",
		"[x]\ntype=drive\nservice_account_file=/private/key\n",
		"[x]\ntype=drive\nconfig_refresh_token_command=sh\n",
		"[x]\ntype=memory\ntype=memory\n", "[x]\ntype=memory\n[y]\ntype=memory\n",
	} {
		if _, _, err := parseCredential([]byte(text)); err == nil {
			t.Fatalf("accepted unsafe fixture %q", text)
		}
	}
	var b bytes.Buffer
	writer := zip.NewWriter(&b)
	member, _ := writer.Create("../fixture.txt")
	_, _ = io.WriteString(member, "[x]\ntype=memory\n")
	_ = writer.Close()
	if _, err := importPackage(b.Bytes(), ""); err == nil {
		t.Fatal("archive traversal accepted")
	}
	if _, err := importPackage(make([]byte, packageLimit+1), ""); err == nil {
		t.Fatal("oversized package accepted")
	}
}
