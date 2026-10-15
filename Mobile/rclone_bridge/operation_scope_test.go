package main

import (
	stdzip "archive/zip"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"io"
	"os"
	"testing"
	"time"
)

func TestLocalCryptReadsDuringTransferKeepCancellationAndRevocation(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:parallel-read"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, _, _, identity, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	var archive bytes.Buffer
	writer := stdzip.NewWriter(&archive)
	member, _ := writer.Create("page.txt")
	member.Write([]byte("completed local page"))
	writer.Close()
	reader, err := cipher.EncryptData(bytes.NewReader(archive.Bytes()))
	if err != nil {
		t.Fatal(err)
	}
	file, err := os.CreateTemp(t.TempDir(), "ciphertext")
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	if _, err := io.Copy(file, reader); err != nil {
		t.Fatal(err)
	}
	input, _ := json.Marshal(map[string]any{"remote": "Secret", "path": cipher.EncryptFileName("comic.zip"),
		"identity": identity, "fd": int(file.Fd()), "offset": 0, "count": 8})
	ctx, finish := scopedOperation("mirror_sync")
	released := false
	defer func() {
		if !released {
			finish()
		}
	}()
	done := make(chan string, 8)
	actions := []string{"crypt_describe", "crypt_stat", "crypt_range", "crypt_archive", "crypt_manifest", "connection_identity"}
	for _, action := range actions {
		go func() { done <- dispatch(action, string(input)) }()
	}
	for range actions {
		select {
		case reply := <-done:
			var value map[string]any
			if json.Unmarshal([]byte(reply), &value) != nil || value["ok"] != true {
				t.Fatal("local crypt read failed", reply)
			}
		case <-time.After(3 * time.Second):
			t.Fatal("local crypt read waited for transfer completion")
		}
	}
	if ctx.Err() != nil {
		t.Fatal("reading cancelled the transfer")
	}
	cancel()
	if ctx.Err() == nil {
		t.Fatal("reading replaced the transfer cancellation handle")
	}
	// Cancelling the transfer must not poison a subsequent independent range.
	var rangeReply struct {
		OK     bool              `json:"ok"`
		Result map[string]string `json:"result"`
	}
	json.Unmarshal([]byte(dispatch("crypt_range", string(input))), &rangeReply)
	data, _ := base64.StdEncoding.DecodeString(rangeReply.Result["data"])
	if !rangeReply.OK || !bytes.Equal(data, archive.Bytes()[:8]) {
		t.Fatal("transfer cancellation leaked into local reading")
	}
	finish()
	released = true
	dispatch("clear", "{}")
	var reply struct {
		OK bool `json:"ok"`
	}
	json.Unmarshal([]byte(dispatch("crypt_stat", string(input))), &reply)
	if reply.OK {
		t.Fatal("credential revocation did not block local reading")
	}
}

func TestCredentialReplacementWaitsForLocalReader(t *testing.T) {
	_, finish := scopedOperation("crypt_range")
	done := make(chan string, 1)
	go func() { done <- dispatch("clear", "{}") }()
	select {
	case <-done:
		finish()
		t.Fatal("credentials changed during a local read")
	case <-time.After(20 * time.Millisecond):
	}
	finish()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("credential replacement did not resume after local read")
	}
}
