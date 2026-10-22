package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
	"github.com/yeka/zip"
)

func TestRemoteComicSnapshotIsOfflineAESBoundedAndRevoked(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:comic-cache"), ""); err != nil {
		t.Fatal(err)
	}
	backend, err := remote(ctx, "Cloud")
	if err != nil {
		t.Fatal(err)
	}
	for _, method := range []zip.EncryptionMethod{zip.StandardEncryption, zip.AES256Encryption} {
		var content bytes.Buffer
		writer := zip.NewWriter(&content)
		member, err := writer.Encrypt("page.png", "inner-password", method)
		if err != nil {
			t.Fatal(err)
		}
		member.Write([]byte("cached page sentinel"))
		writer.Close()
		for _, name := range []string{"Cloud", "Secret"} {
			p := "cached.cbz"
			data, objectPath := content.Bytes(), p
			if name == "Secret" {
				cipher, _, root, _, err := cryptConnection(name)
				if err != nil {
					t.Fatal(err)
				}
				encrypted, err := cipher.EncryptData(bytes.NewReader(data))
				if err != nil {
					t.Fatal(err)
				}
				var encoded bytes.Buffer
				encoded.ReadFrom(encrypted)
				data, objectPath = encoded.Bytes(), root+"/"+cipher.EncryptFileName(p)
			}
			obj, err := backend.Put(ctx, bytes.NewReader(data), object.NewStaticObjectInfo(objectPath, time.Now(), int64(len(data)), true, nil, backend))
			if err != nil {
				t.Fatal(err)
			}
			identity, _ := connectionIdentity(name)
			_, _, revision, err := remoteDocument(ctx, name, p, identity)
			if err != nil {
				t.Fatal(err)
			}
			run := strings.Repeat("a", 32)
			if _, err := cacheRemoteComic(ctx, run, name, p, identity, "stale"); err == nil {
				t.Fatal("stale revision cached")
			}
			if _, err := cacheRemoteComic(ctx, run, name, p, identity, revision); err != nil {
				t.Fatal(err)
			}
			remoteComics.Lock()
			done, total := remoteComics.entries[run].done, remoteComics.bytes
			remoteComics.Unlock()
			if done != int64(content.Len()) || total != done {
				t.Fatal("incorrect cache accounting")
			}
			// Removing the online object proves page access needs no network/source.
			if err := obj.Remove(ctx); err != nil {
				t.Fatal(err)
			}
			if _, err := cachedRemoteArchive(ctx, run, name, p, identity, revision, "wrong", "page.png"); err == nil {
				t.Fatal("wrong archive password accepted")
			}
			network, finish := scopedOperation("mirror_sync")
			result := make(chan error, 1)
			go func() {
				value, err := cachedRemoteArchive(ctx, run, name, p, identity, revision, "inner-password", "page.png")
				if err == nil {
					decoded, _ := base64.StdEncoding.DecodeString(value.(map[string]string)["data"])
					if string(decoded) != "cached page sentinel" {
						err = context.Canceled
					}
				}
				result <- err
			}()
			select {
			case err := <-result:
				if err != nil {
					finish()
					t.Fatal(err)
				}
			case <-time.After(time.Second):
				finish()
				t.Fatal("cached page waited for network operation")
			}
			if network.Err() != nil {
				finish()
				t.Fatal("cached read cancelled network operation")
			}
			finish()
			releaseRemoteComic(run)
			if remoteComics.bytes != 0 {
				t.Fatal("closing cache retained its budget")
			}
			if _, err := cachedRemoteArchive(ctx, run, name, p, identity, revision, "inner-password", "page.png"); err == nil {
				t.Fatal("closed cache remained readable")
			}
		}
	}
}

func TestRemoteComicControlReportsSharedBudgetWithoutContent(t *testing.T) {
	clearRemoteComics()
	defer clearRemoteComics()
	run := strings.Repeat("b", 32)
	remoteComics.entries[run] = &remoteComic{total: 123, done: 123, ready: true, data: []byte("private sentinel")}
	remoteComics.bytes = 123
	var response struct {
		Result map[string]any `json:"result"`
	}
	raw := remoteComicControl("remote_cache_status", `{"run":"`+run+`"}`)
	if strings.Contains(raw, "private sentinel") {
		t.Fatal("content leaked in accounting")
	}
	if err := json.Unmarshal([]byte(raw), &response); err != nil {
		t.Fatal(err)
	}
	if response.Result["pool_bytes"] != float64(123) || response.Result["pool_limit"] != float64(remoteComicPoolLimit) {
		t.Fatal("missing aggregate admission accounting")
	}
	remoteComicControl("remote_cache_close", `{"run":"`+run+`"}`)
	if remoteComics.bytes != 0 {
		t.Fatal("close did not release reservation")
	}
}
