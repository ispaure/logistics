package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"path"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
)

func TestMirrorAuthenticatedPullVerifiedPushAndRemoteConflict(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:mirror-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, backing, root, _, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	f, err := remote(ctx, backing)
	if err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"Cloud", "Secret"} {
		info, err := mirrorInfo(ctx, name, "")
		if err != nil {
			t.Fatal(err)
		}
		identity := info["identity"].(string)
		p := "mirror-note.txt"
		data := []byte("old remote bytes")
		physical := p
		if name == "Secret" {
			p = cipher.EncryptFileName(p)
			physical = path.Join(root, p)
			encrypted, e := cipher.EncryptData(bytes.NewReader(data))
			if e != nil {
				t.Fatal(e)
			}
			data, e = io.ReadAll(encrypted)
			if e != nil {
				t.Fatal(e)
			}
		}
		_, err = f.Put(ctx, bytes.NewReader(data), object.NewStaticObjectInfo(physical, time.Now(), int64(len(data)), true, nil, f))
		if err != nil {
			t.Fatal(err)
		}
		expected, err := mirrorStat(ctx, name, p, identity)
		if err != nil || expected == "" {
			t.Fatal(err)
		}
		rows, err := mirrorList(ctx, name, "", identity)
		if err != nil || len(rows) == 0 {
			t.Fatal(err)
		}
		output, err := os.CreateTemp(t.TempDir(), "pull")
		if err != nil {
			t.Fatal(err)
		}
		count, err := mirrorRead(ctx, name, p, identity, int(output.Fd()))
		if err != nil || count != int64(len(data)) {
			t.Fatal(err)
		}
		output.Seek(0, 0)
		actual, _ := io.ReadAll(output)
		output.Close()
		if !bytes.Equal(actual, data) {
			t.Fatal("ciphertext was not retained")
		}
		updated := []byte("updated local bytes")
		if name == "Secret" {
			encrypted, e := cipher.EncryptData(bytes.NewReader(updated))
			if e != nil {
				t.Fatal(e)
			}
			updated, e = io.ReadAll(encrypted)
			if e != nil {
				t.Fatal(e)
			}
		}
		source, err := os.CreateTemp(t.TempDir(), "push")
		if err != nil {
			t.Fatal(err)
		}
		source.Write(updated)
		source.Seek(0, 0)
		next, err := mirrorWrite(ctx, name, p, identity, expected, strings.Repeat("a", 32), int(source.Fd()))
		if err != nil || next == expected {
			t.Fatal(err)
		}
		source.Seek(0, 0)
		if _, err = mirrorWrite(ctx, name, p, identity, expected, strings.Repeat("b", 32), int(source.Fd())); err == nil {
			t.Fatal("stale remote revision was overwritten")
		}
		source.Close()
		// The reserved backup is excluded, but the old bytes remain recoverable.
		backup := path.Join(".logistics-backups", strings.Repeat("a", 32), "mirror-note.txt")
		if name == "Secret" {
			backup = cipher.EncryptFileName(backup)
		}
		old, err := f.NewObject(ctx, path.Join(rootFor(name, root), backup))
		if err != nil {
			t.Fatal(err)
		}
		hash, err := mirrorDigest(ctx, old)
		if err != nil || hash != expected {
			t.Fatal("remote backup differed")
		}
		if _, err = mirrorList(ctx, name, "", strings.Repeat("f", 64)); err == nil {
			t.Fatal("different connection accepted")
		}
	}
}

func rootFor(name, root string) string {
	if name == "Secret" {
		return root
	}
	return ""
}

func TestLocalImageDispatchDoesNotWaitForRemoteTransfer(t *testing.T) {
	serial.Lock()
	done := make(chan string, 1)
	go func() { done <- dispatch("image_thumbnail", `{"data":"not-base64"}`) }()
	select {
	case reply := <-done:
		var value map[string]any
		if json.Unmarshal([]byte(reply), &value) != nil || value["ok"] != false {
			t.Fatal("invalid image was accepted")
		}
	case <-time.After(time.Second):
		serial.Unlock()
		t.Fatal("local image work blocked behind remote transfer")
	}
	serial.Unlock()
}
