package main

import (
	"context"
	"encoding/base64"
	"errors"
	"github.com/yeka/zip"
	"os"
	"path/filepath"
	"testing"
)

func TestStandaloneEncryptedArchiveWithoutCredentials(t *testing.T) {
	for _, method := range []zip.EncryptionMethod{zip.StandardEncryption, zip.AES256Encryption} {
		file, err := os.Create(filepath.Join(t.TempDir(), "comic.cbz"))
		if err != nil {
			t.Fatal(err)
		}
		writer := zip.NewWriter(file)
		page, err := writer.Encrypt("page.png", "fixture-password", method)
		if err != nil {
			t.Fatal(err)
		}
		if _, err = page.Write([]byte("fixture page")); err != nil {
			t.Fatal(err)
		}
		if err = writer.Close(); err != nil {
			t.Fatal(err)
		}
		if _, err = fileArchive(context.Background(), int(file.Fd()), "", ""); err != nil {
			t.Fatal(err)
		}
		for _, password := range []string{"", "wrong"} {
			if _, err = fileArchive(context.Background(), int(file.Fd()), password, "page.png"); !errors.Is(err, archivePasswordError) {
				t.Fatalf("wrong password was not rejected: %v", err)
			}
		}
		result, err := fileArchive(context.Background(), int(file.Fd()), "fixture-password", "page.png")
		if err != nil {
			t.Fatal(err)
		}
		data, err := base64.StdEncoding.DecodeString(result.(map[string]string)["data"])
		if err != nil || string(data) != "fixture page" {
			t.Fatal("bad decoded page")
		}
		file.Close()
	}
}

func TestStandaloneArchiveValidatesAllHeadersBeforeReading(t *testing.T) {
	file, err := os.Create(filepath.Join(t.TempDir(), "unsafe.cbz"))
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer := zip.NewWriter(file)
	first, _ := writer.Create("page.png")
	first.Write([]byte("page"))
	unsafe, _ := writer.Create("../escape.png")
	unsafe.Write([]byte("outside"))
	if err = writer.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err = fileArchive(context.Background(), int(file.Fd()), "", "page.png"); err == nil {
		t.Fatal("unsafe later header accepted")
	}
}
