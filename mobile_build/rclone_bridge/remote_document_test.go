// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
)

func TestRemoteDocumentsRangesArchivesIdentityAndRevision(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:remote-reader"), ""); err != nil {
		t.Fatal(err)
	}
	cloud, err := remote(ctx, "Cloud")
	if err != nil {
		t.Fatal(err)
	}
	var content bytes.Buffer
	archive := zip.NewWriter(&content)
	member, _ := archive.Create("page.txt")
	member.Write([]byte("remote sentinel"))
	archive.Close()
	cipher, _, root, _, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	encrypted, err := cipher.EncryptData(bytes.NewReader(content.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	var encoded bytes.Buffer
	if _, err = encoded.ReadFrom(encrypted); err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	for p, data := range map[string][]byte{"plain.zip": content.Bytes(), root + "/" + cipher.EncryptFileName("secret.zip"): encoded.Bytes()} {
		if _, err := cloud.Put(ctx, bytes.NewReader(data), object.NewStaticObjectInfo(p, now, int64(len(data)), true, nil, cloud)); err != nil {
			t.Fatal(err)
		}
	}
	for name, p := range map[string]string{"Cloud": "plain.zip", "Secret": "secret.zip"} {
		identity, _ := connectionIdentity(name)
		result, err := remoteDocumentRequest(ctx, "remote_stat", name, p, identity, "", "", "", 0, 0)
		if err != nil {
			t.Fatal(err)
		}
		stat := result.(map[string]any)
		revision := stat["revision"].(string)
		if stat["size"].(int64) != int64(content.Len()) {
			t.Fatal("incorrect logical size", stat)
		}
		result, err = remoteDocumentRequest(ctx, "remote_range", name, p, identity, revision, "", "", 2, 6)
		if err != nil {
			t.Fatal(err)
		}
		data, _ := base64.StdEncoding.DecodeString(result.(map[string]string)["data"])
		if !bytes.Equal(data, content.Bytes()[2:8]) {
			t.Fatal("range mismatch")
		}
		result, err = remoteDocumentRequest(ctx, "remote_archive", name, p, identity, revision, "", "page.txt", 0, 0)
		if err != nil {
			t.Fatal(err)
		}
		data, _ = base64.StdEncoding.DecodeString(result.(map[string]string)["data"])
		if string(data) != "remote sentinel" {
			t.Fatal("archive member mismatch")
		}
		for _, invalid := range []struct {
			identity, revision string
			count              int
		}{{"wrong", revision, 1}, {identity, "stale", 1}, {identity, revision, 4*1024*1024 + 1}} {
			if _, err := remoteDocumentRequest(ctx, "remote_range", name, p, invalid.identity, invalid.revision, "", "", 0, invalid.count); err == nil {
				t.Fatal("invalid read accepted")
			}
		}
	}
	stopped, cancel := context.WithCancel(ctx)
	cancel()
	identity, _ := connectionIdentity("Cloud")
	if _, err := remoteDocumentRequest(stopped, "remote_archive", "Cloud", "plain.zip", identity, "", "", "", 0, 0); err == nil {
		t.Fatal("cancelled archive read succeeded")
	}
}

// Video uses larger rolling ranges than document readers. Exercise the real
// native boundary for plain and encrypted files, including the exact limit.
func TestRemoteVideoFourMiBRanges(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:video-ranges"), ""); err != nil {
		t.Fatal(err)
	}
	cloud, err := remote(ctx, "Cloud")
	if err != nil {
		t.Fatal(err)
	}
	raw := bytes.Repeat([]byte("video-range-sentinel"), 250000)
	cipher, _, root, _, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	encrypted, err := cipher.EncryptData(bytes.NewReader(raw))
	if err != nil {
		t.Fatal(err)
	}
	var encoded bytes.Buffer
	if _, err = encoded.ReadFrom(encrypted); err != nil {
		t.Fatal(err)
	}
	for p, data := range map[string][]byte{"movie.avi": raw, root + "/" + cipher.EncryptFileName("movie.avi"): encoded.Bytes()} {
		if _, err = cloud.Put(ctx, bytes.NewReader(data), object.NewStaticObjectInfo(p, time.Now(), int64(len(data)), true, nil, cloud)); err != nil {
			t.Fatal(err)
		}
	}
	for _, name := range []string{"Cloud", "Secret"} {
		t.Run(name, func(t *testing.T) {
			identity, _ := connectionIdentity(name)
			stat, err := remoteDocumentRequest(ctx, "remote_stat", name, "movie.avi", identity, "", "", "", 0, 0)
			if err != nil {
				t.Fatal(err)
			}
			revision := stat.(map[string]any)["revision"].(string)
			result, err := remoteDocumentRequest(ctx, "remote_range", name, "movie.avi", identity, revision, "", "", 0, 4*1024*1024)
			if err != nil {
				t.Fatal(err)
			}
			data, err := base64.StdEncoding.DecodeString(result.(map[string]string)["data"])
			if err != nil || !bytes.Equal(data, raw[:4*1024*1024]) {
				t.Fatal("video range mismatch", err)
			}
			if _, err = remoteDocumentRequest(ctx, "remote_range", name, "movie.avi", identity, revision, "", "", 0, 4*1024*1024+1); err == nil {
				t.Fatal("oversized video range accepted")
			}
		})
	}
}
