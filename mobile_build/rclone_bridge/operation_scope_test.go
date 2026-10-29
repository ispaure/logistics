// TEST_STAGE = TestStage.SMOKE
package main

import (
	stdzip "archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/cache"
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

// Import/restore must report contention immediately, preserve credentials and
// leave the running transfer's cancellation handle intact.
func TestCredentialLoadingNeverQueuesBehindTransfer(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(multiPackage(t, "Existing", "memory", ""), ""); err != nil {
		t.Fatal(err)
	}
	ctx, finish := scopedOperation("mirror_sync")
	defer finish()
	epoch := credentialEpoch
	for _, action := range []string{"import", "vault_open", "add_smb"} {
		done := make(chan string, 1)
		go func() { done <- dispatch(action, "{}") }()
		select {
		case raw := <-done:
			var reply map[string]any
			if json.Unmarshal([]byte(raw), &reply) != nil || reply["ok"] != false || reply["error_code"] != "credentials_busy" {
				t.Fatal("expected immediate credential contention", raw)
			}
		case <-time.After(time.Second):
			t.Fatal("credential loading queued behind a transfer")
		}
	}
	if credentialEpoch != epoch || !admitted["Existing"] || ctx.Err() != nil {
		t.Fatal("rejected load changed credentials or interrupted the transfer")
	}
	cancel()
	if ctx.Err() == nil {
		t.Fatal("loading replaced the transfer cancellation handle")
	}
}

func TestCredentialMetadataDoesNotQueueBehindNetwork(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	_, finish := scopedOperation("list")
	defer finish()
	for _, action := range []string{"crypt_remotes", "vault_info", "protect_package", "unprotect_package"} {
		done := make(chan string, 1)
		go func() { done <- dispatch(action, "{}") }()
		select {
		case <-done:
		case <-time.After(time.Second):
			t.Fatal("local credential metadata queued behind a network operation", action)
		}
	}
}

func TestCredentialImportDoesNotWaitForBackendDisconnect(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	started, release := make(chan struct{}), make(chan struct{})
	defer close(release)
	backend, err := fs.NewFs(context.Background(), ":memory:credential-retirement")
	if err != nil {
		t.Fatal(err)
	}
	clients["Retiring"] = &slowDisconnect{Fs: backend, started: started, release: release}
	input, _ := json.Marshal(map[string]any{"package": base64.StdEncoding.EncodeToString(multiPackage(t, "Fresh", "memory", "")), "package_name": "Fresh.zip", "session_only": true})
	done := make(chan string, 1)
	go func() { done <- dispatch("import", string(input)) }()
	select {
	case raw := <-done:
		var reply map[string]any
		if json.Unmarshal([]byte(raw), &reply) != nil || reply["ok"] != true || !admitted["Fresh"] {
			t.Fatal("offline import failed", raw)
		}
	case <-time.After(time.Second):
		t.Fatal("credential import waited for backend disconnect")
	}
	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("old backend was not retired")
	}
}

type slowDisconnect struct {
	fs.Fs
	started chan struct{}
	release chan struct{}
}

func (f *slowDisconnect) Features() *fs.Features {
	features := *f.Fs.Features()
	features.Shutdown = func(context.Context) error {
		close(f.started)
		<-f.release
		return nil
	}
	return &features
}

func TestOfflineImportDefersNetworkCacheEviction(t *testing.T) {
	clearSession()
	backend, err := fs.NewFs(context.Background(), ":memory:cached-credential-retirement")
	if err != nil {
		t.Fatal(err)
	}
	retired := &cachedDisconnect{Fs: backend, stopped: make(chan struct{}, 1)}
	cache.Put("Cached:", retired)
	t.Cleanup(func() { cache.Clear(); clearSession() })
	if _, err := importPackage(multiPackage(t, "Offline", "memory", ""), ""); err != nil {
		t.Fatal(err)
	}
	select {
	case <-retired.stopped:
		t.Fatal("offline import invoked a cached network backend's Shutdown")
	default:
	}
	if _, err := remote(context.Background(), "Offline"); err != nil {
		t.Fatal(err)
	}
	select {
	case <-retired.stopped:
	default:
		t.Fatal("next explicit online operation did not evict the retired cache")
	}
}

type cachedDisconnect struct {
	fs.Fs
	stopped chan struct{}
}

func (f *cachedDisconnect) Shutdown(context.Context) error {
	f.stopped <- struct{}{}
	return nil
}
