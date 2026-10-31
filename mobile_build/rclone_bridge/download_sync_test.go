// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/object"
)

func TestDownloadSelectedItemAndEncryptedDestination(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:download-crypt"), ""); err != nil {
		t.Fatal(err)
	}
	ctx := context.WithValue(context.Background(), mirrorLogicalKey{}, true)
	source, err := fs.NewFs(ctx, "Cloud:download-test")
	if err != nil {
		t.Fatal(err)
	}
	put := func(f fs.Fs, name, text string) {
		t.Helper()
		if _, err := f.Put(ctx, strings.NewReader(text), object.NewStaticObjectInfo(name, time.Now(), int64(len(text)), true, nil, f)); err != nil {
			t.Fatal(err)
		}
	}
	put(source, "one.txt", "single")
	put(source, "folder/note.txt", "nested")
	put(source, "unrelated.txt", "keep remote")
	if err := source.Mkdir(ctx, "folder/empty"); err != nil {
		t.Fatal(err)
	}
	identity, _ := connectionIdentity("Cloud")
	for _, directory := range []bool{false, true} {
		for _, encrypted := range []bool{false, true} {
			local := canonicalTestDir(t)
			selected := "download-test/one.txt"
			filename, content := "one.txt", "single"
			if directory {
				selected = "download-test/folder"
				filename = "note.txt"
				content = "nested"
			}
			request := bridgeRequest{Download: true, Remote: "Cloud", Identity: identity, Path: selected,
				Directory: directory, LocalPath: local, Run: strings.Repeat("a", 32)}
			if encrypted {
				_, _, _, cryptID, e := cryptConnection("Secret")
				if e != nil {
					t.Fatal(e)
				}
				request.DestinationRemote, request.DestinationIdentity = "Secret", cryptID
			}
			payload, err := json.Marshal(request)
			if err != nil {
				t.Fatal(err)
			}
			var reply struct {
				OK    bool   `json:"ok"`
				Error string `json:"error"`
			}
			if err := json.Unmarshal([]byte(dispatch("mirror_sync", string(payload))), &reply); err != nil || !reply.OK {
				t.Fatalf("download wire request failed: %v %s", err, reply.Error)
			}
			physical := filename
			if encrypted {
				cipher, _, _, _, _ := cryptConnection("Secret")
				physical = cipher.EncryptFileName(filename)
			}
			data, err := os.ReadFile(filepath.Join(local, physical))
			if err != nil {
				t.Fatal(err)
			}
			if encrypted {
				if bytes.Contains(data, []byte(content)) {
					t.Fatal("plaintext was persisted")
				}
				cipher, _, _, _, _ := cryptConnection("Secret")
				reader, e := cipher.DecryptData(io.NopCloser(bytes.NewReader(data)))
				if e != nil {
					t.Fatal(e)
				}
				data, e = io.ReadAll(reader)
				reader.Close()
				if e != nil {
					t.Fatal(e)
				}
			}
			if string(data) != content {
				t.Fatalf("wrong selected contents: %q", data)
			}
			entries, _ := os.ReadDir(local)
			expected := 1
			if directory && source.Features().CanHaveEmptyDirectories {
				expected = 2
			}
			if len(entries) != expected {
				t.Fatalf("download escaped its selected scope: %v", entries)
			}
		}
	}
	secret, err := fs.NewFs(ctx, "Secret:private-folder")
	if err != nil {
		t.Fatal(err)
	}
	put(secret, "secret.txt", "decrypted once")
	secretID, _ := connectionIdentity("Secret")
	local := canonicalTestDir(t)
	if _, err := downloadSync(ctx, bridgeRequest{Remote: "Secret", Identity: secretID, Path: "private-folder/secret.txt", LocalPath: local, Run: strings.Repeat("b", 32)}); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(local, "secret.txt"))
	if err != nil || string(data) != "decrypted once" {
		t.Fatalf("crypt source download failed: %s %v", data, err)
	}
}

func TestDownloadRejectsNonemptyDestinationAndChangedIdentity(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:download-guard"), ""); err != nil {
		t.Fatal(err)
	}
	identity, _ := connectionIdentity("Cloud")
	local := canonicalTestDir(t)
	sentinel := filepath.Join(local, "keep.txt")
	if err := os.WriteFile(sentinel, []byte("keep"), 0600); err != nil {
		t.Fatal(err)
	}
	request := bridgeRequest{Remote: "Cloud", Identity: identity, Path: "folder", Directory: true, LocalPath: local, Run: strings.Repeat("c", 32)}
	if _, err := downloadSync(context.Background(), request); err == nil {
		t.Fatal("nonempty destination accepted")
	}
	data, _ := os.ReadFile(sentinel)
	if string(data) != "keep" {
		t.Fatal("unrelated destination changed")
	}
	request.LocalPath = canonicalTestDir(t)
	request.Identity = strings.Repeat("0", 64)
	if _, err := downloadSync(context.Background(), request); err == nil {
		t.Fatal("changed source identity accepted")
	}
}
