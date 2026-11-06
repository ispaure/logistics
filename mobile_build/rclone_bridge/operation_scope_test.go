// TEST_STAGE = TestStage.SMOKE
package main

import (
	stdzip "archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/cache"
	"github.com/rclone/rclone/fs/config/configmap"
	"github.com/rclone/rclone/fs/config/obscure"
	"github.com/rclone/rclone/lib/oauthutil"
	"golang.org/x/oauth2"
	"io"
	"net/http"
	"os"
	"strings"
	"sync/atomic"
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
	actions := []string{"crypt_describe", "crypt_stat", "crypt_sizes", "crypt_range", "crypt_archive", "crypt_manifest", "connection_identity"}
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

const syntheticOAuthToken = `{"access_token":"synthetic-initial","refresh_token":"synthetic-refresh","token_type":"Bearer","expiry":"2099-01-01T00:00:00Z"}`

type fixtureRoundTripper func(*http.Request) (*http.Response, error)

func (f fixtureRoundTripper) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

type fixtureOAuthFS struct {
	fs.Fs
	tokens *oauthutil.TokenSource
}

func (f *fixtureOAuthFS) List(ctx context.Context, dir string) (fs.DirEntries, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	_, err := f.tokens.Token()
	return nil, err
}
func requireFixtureReply(t *testing.T, action, input string) {
	t.Helper()
	raw := dispatch(action, input)
	var reply struct {
		OK bool `json:"ok"`
	}
	if err := json.Unmarshal([]byte(raw), &reply); err != nil || !reply.OK {
		t.Fatalf("%s: %s", action, raw)
	}
}
func importFixtureInput(t *testing.T, name, kind, token string) string {
	t.Helper()
	input, err := json.Marshal(map[string]any{"package": base64.StdEncoding.EncodeToString(multiPackage(t, name, kind, token)), "package_name": name + ".zip", "session_only": true})
	if err != nil {
		t.Fatal(err)
	}
	return string(input)
}
func TestCachedOAuthRemoteRefreshAfterRequest(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	info, err := fs.Find("drive")
	if err != nil {
		t.Fatal(err)
	}
	original := info.NewFs
	t.Cleanup(func() { info.NewFs = original })
	var tokens *oauthutil.TokenSource
	var constructor context.Context
	var calls atomic.Int32
	constructors := 0
	info.NewFs = func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
		constructors++
		constructor = ctx
		memory, err := fs.NewFs(ctx, ":memory:oauth-fixture")
		if err != nil {
			return nil, err
		}
		transport := fixtureRoundTripper(func(r *http.Request) (*http.Response, error) {
			if err := r.Context().Err(); err != nil {
				t.Logf("synthetic refresh context: %v", err)
				return nil, err
			}
			if r.URL.String() != "https://oauth-fixture.invalid/token" {
				return nil, fmt.Errorf("unexpected synthetic URL: %s", r.URL)
			}
			calls.Add(1)
			return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"access_token":"synthetic-refreshed","token_type":"Bearer","expires_in":3600,"refresh_token":"synthetic-refresh"}`))}, nil
		})
		_, tokens, err = oauthutil.NewClientWithBaseClient(ctx, name, m, &oauthutil.Config{ClientID: "synthetic-client", ClientSecret: "synthetic-secret", TokenURL: "https://oauth-fixture.invalid/token", AuthStyle: oauth2.AuthStyleInParams}, &http.Client{Transport: transport})
		return &fixtureOAuthFS{Fs: memory, tokens: tokens}, err
	}
	requireFixtureReply(t, "import", importFixtureInput(t, "OAuthFixture", "drive", syntheticOAuthToken))
	input := `{"remote":"OAuthFixture","path":""}`
	requireFixtureReply(t, "list", input)
	if constructors != 1 || calls.Load() != 0 {
		t.Fatal("unexpected construction/refresh count", constructors, calls.Load())
	}
	before, err := connectionIdentity("OAuthFixture")
	if err != nil {
		t.Fatal(err)
	}
	t.Logf("constructor context after first dispatch: %v", constructor.Err())
	if err = tokens.Expire(); err != nil {
		t.Fatal(err)
	}
	requireFixtureReply(t, "list", input)
	after, err := connectionIdentity("OAuthFixture")
	if err != nil || before != after {
		t.Fatal("refresh changed identity", err)
	}
	value, _ := store.GetValue("OAuthFixture", "token")
	if constructors != 1 || calls.Load() != 1 || !strings.Contains(value, "synthetic-refreshed") {
		t.Fatal("cached refresh did not publish token", constructors, calls.Load())
	}
}

// Registry replacements are deliberately nonparallel and restored before cleanup.
func replaceFixtureDrive(t *testing.T, factory func(context.Context, string, string, configmap.Mapper) (fs.Fs, error)) {
	t.Helper()
	clearSession()
	t.Cleanup(clearSession)
	info, err := fs.Find("drive")
	if err != nil {
		t.Fatal(err)
	}
	original := info.NewFs
	info.NewFs = factory
	t.Cleanup(func() { info.NewFs = original })
	requireFixtureReply(t, "import", importFixtureInput(t, "OAuthFixture", "drive", syntheticOAuthToken))
}

func awaitFixture(t *testing.T, ch <-chan struct{}) {
	t.Helper()
	select {
	case <-ch:
	case <-time.After(2 * time.Second):
		t.Fatal("fixture did not reach barrier")
	}
}

type fixtureListFS struct {
	fs.Fs
	list func(context.Context) (fs.DirEntries, error)
}

func (f *fixtureListFS) List(ctx context.Context, _ string) (fs.DirEntries, error) {
	return f.list(ctx)
}

func (f *fixtureListFS) Features() *fs.Features {
	features := *f.Fs.Features()
	features.ListP = nil // Exercise the fixture List, including through crypt.
	return &features
}

func TestCachedBackendRequestCancelAndCredentialRetirement(t *testing.T) {
	var contexts []context.Context
	var block atomic.Bool
	started := make(chan struct{}, 1)
	replaceFixtureDrive(t, func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
		contexts = append(contexts, ctx)
		memory, err := fs.NewFs(ctx, ":memory:request-cancellation")
		return &fixtureListFS{Fs: memory, list: func(request context.Context) (fs.DirEntries, error) {
			if block.Load() {
				started <- struct{}{}
				<-request.Done()
				return nil, request.Err()
			}
			return nil, nil
		}}, err
	})
	input := `{"remote":"OAuthFixture","path":""}`
	requireFixtureReply(t, "list", input)
	if contexts[0].Err() != nil {
		t.Fatal("normal completion retired backend")
	}
	block.Store(true)
	done := make(chan string, 1)
	go func() { done <- dispatch("list", input) }()
	awaitFixture(t, started)
	requireFixtureReply(t, "cancel", "{}")
	select {
	case raw := <-done:
		if !strings.Contains(raw, `"ok":false`) {
			t.Fatal(raw)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("cancel did not release List")
	}
	if contexts[0].Err() == nil {
		t.Fatal("request cancellation did not retire backend")
	}
	block.Store(false)
	requireFixtureReply(t, "list", input)
	if len(contexts) != 2 || contexts[1].Err() != nil {
		t.Fatal("cancelled backend was reused")
	}
	requireFixtureReply(t, "import", importFixtureInput(t, "OAuthFixture", "drive", syntheticOAuthToken))
	if contexts[1].Err() == nil {
		t.Fatal("replacement retained backend context")
	}
	requireFixtureReply(t, "list", input)
	requireFixtureReply(t, "clear", "{}")
	if len(contexts) != 3 || contexts[2].Err() == nil {
		t.Fatal("clear retained backend context")
	}
}

func TestBackendInitializationCancellationAndFailure(t *testing.T) {
	for _, mode := range []string{"cancel", "deadline", "failure"} {
		t.Run(mode, func(t *testing.T) {
			started := make(chan struct{})
			var captured context.Context
			replaceFixtureDrive(t, func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
				captured = ctx
				close(started)
				if mode == "failure" {
					return nil, errors.New("synthetic construction failure")
				}
				<-ctx.Done()
				return nil, ctx.Err()
			})
			ctx, finish := scopedOperation("list")
			defer finish()
			if mode == "deadline" {
				var stop context.CancelFunc
				ctx, stop = context.WithTimeout(ctx, 50*time.Millisecond)
				defer stop()
			}
			done := make(chan error, 1)
			go func() { _, err := remote(ctx, "OAuthFixture"); done <- err }()
			awaitFixture(t, started)
			if mode == "cancel" {
				requireFixtureReply(t, "cancel", "{}")
			}
			select {
			case err := <-done:
				if err == nil {
					t.Fatal("construction unexpectedly succeeded")
				}
			case <-time.After(2 * time.Second):
				t.Fatal("initialization ignored cancellation")
			}
			if captured.Err() == nil || len(clients) != 0 {
				t.Fatal("unpublished lifecycle survived failure")
			}
		})
	}
}

func TestBackendCancellationAtOperationFinish(t *testing.T) {
	for _, mode := range []string{"normal", "cancel-before", "cancel-during-detach", "cancel-after-detach", "callback-started"} {
		t.Run(mode, func(t *testing.T) {
			parent, cancelRequest := context.WithCancel(context.Background())
			defer cancelRequest()
			owner := &operationBackends{}
			ctx := context.WithValue(parent, operationBackendsKey{}, owner)
			lifetime, stop := context.WithCancel(context.Background())
			defer stop()
			callbackStarted, callbackRelease, callbackDone := make(chan struct{}), make(chan struct{}), make(chan struct{})
			cancelBackend := context.CancelFunc(stop)
			if mode == "callback-started" {
				cancelBackend = func() { close(callbackStarted); <-callbackRelease; stop(); close(callbackDone) }
			}
			followBackendCancellation(ctx, cancelBackend)
			// The production finish fallback must use an idempotent cancel. Delay only
			// the already-running AfterFunc to expose detach returning false.
			if mode == "callback-started" {
				owner.hooks[0].stop = stop
				cancelRequest()
				awaitFixture(t, callbackStarted)
			}
			if mode == "cancel-before" {
				cancelRequest()
			}
			if mode == "cancel-during-detach" {
				detach := owner.hooks[0].detach
				owner.hooks[0].detach = func() bool { cancelRequest(); return detach() }
			}
			if mode == "cancel-after-detach" {
				detach := owner.hooks[0].detach
				owner.hooks[0].detach = func() bool { detached := detach(); cancelRequest(); return detached }
			}
			owner.finish()
			if mode == "normal" {
				cancelRequest()
				if lifetime.Err() != nil {
					t.Fatal("normal finish cancelled backend")
				}
			} else if lifetime.Err() == nil {
				t.Fatal("finish lost cancellation")
			}
			if mode == "callback-started" {
				close(callbackRelease)
				awaitFixture(t, callbackDone)
			}
		})
	}
}

func TestCachedOAuthRefreshCancellation(t *testing.T) {
	for _, mode := range []string{"cancel", "deadline"} {
		t.Run(mode, func(t *testing.T) {
			testCachedOAuthRefreshCancellation(t, mode)
		})
	}
}

func testCachedOAuthRefreshCancellation(t *testing.T, mode string) {
	var tokens *oauthutil.TokenSource
	var lifetime context.Context
	var block atomic.Bool
	started := make(chan struct{}, 1)
	transport := fixtureRoundTripper(func(r *http.Request) (*http.Response, error) {
		if r.URL.String() != "https://oauth-fixture.invalid/token" {
			return nil, errors.New("unexpected synthetic URL")
		}
		if block.Load() {
			select {
			case started <- struct{}{}:
			default:
			}
			<-r.Context().Done()
			return nil, r.Context().Err()
		}
		return &http.Response{StatusCode: 200, Header: http.Header{"Content-Type": []string{"application/json"}}, Body: io.NopCloser(strings.NewReader(`{"access_token":"synthetic-refreshed","token_type":"Bearer","expires_in":3600,"refresh_token":"synthetic-refresh"}`))}, nil
	})
	replaceFixtureDrive(t, func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
		lifetime = ctx
		memory, err := fs.NewFs(ctx, ":memory:refresh-cancellation")
		if err != nil {
			return nil, err
		}
		_, tokens, err = oauthutil.NewClientWithBaseClient(ctx, name, m, &oauthutil.Config{ClientID: "synthetic-client", ClientSecret: "synthetic-secret", TokenURL: "https://oauth-fixture.invalid/token", AuthStyle: oauth2.AuthStyleInParams}, &http.Client{Transport: transport})
		return &fixtureOAuthFS{Fs: memory, tokens: tokens}, err
	})
	input := `{"remote":"OAuthFixture","path":""}`
	requireFixtureReply(t, "list", input)
	if err := tokens.Expire(); err != nil {
		t.Fatal(err)
	}
	block.Store(true)
	done := make(chan string, 1)
	go func() {
		if mode == "cancel" {
			done <- dispatch("list", input)
			return
		}
		ctx, finish := scopedOperation("list")
		defer finish()
		ctx, stop := context.WithTimeout(ctx, 50*time.Millisecond)
		defer stop()
		result, err := list(ctx, "OAuthFixture", "")
		done <- encodeReply("list", result, err)
	}()
	awaitFixture(t, started)
	if mode == "cancel" {
		requireFixtureReply(t, "cancel", "{}")
	}
	// OAuth's pinned retry loop sleeps one second after each of five failures.
	select {
	case raw := <-done:
		if !strings.Contains(raw, `"ok":false`) {
			t.Fatal(raw)
		}
	case <-time.After(8 * time.Second):
		t.Fatal("refresh ignored cancellation")
	}
	if lifetime.Err() == nil {
		t.Fatal("refresh retained cancelled lifetime")
	}
	block.Store(false)
	requireFixtureReply(t, "list", input)
	if lifetime.Err() != nil {
		t.Fatal("retry reused cancelled OAuth backend")
	}
}

func TestCancelledCryptBackendEvictsSharedBackingCache(t *testing.T) {
	var backing []context.Context
	var block atomic.Bool
	started := make(chan struct{}, 1)
	memoryInfo, err := fs.Find("memory")
	if err != nil {
		t.Fatal(err)
	}
	replaceFixtureDrive(t, func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
		backing = append(backing, ctx)
		memory, err := memoryInfo.NewFs(ctx, name, root, configmap.Simple{})
		return &fixtureListFS{Fs: memory, list: func(request context.Context) (fs.DirEntries, error) {
			if block.Load() {
				started <- struct{}{}
				<-ctx.Done() // Model a backing OAuth refresh using its retained context.
			}
			if err := request.Err(); err != nil {
				return nil, err
			}
			return nil, ctx.Err()
		}}, err
	})
	var data bytes.Buffer
	archive := stdzip.NewWriter(&data)
	for name, text := range map[string]string{
		"Cloud":   "type=drive\ntoken=" + syntheticOAuthToken + "\n",
		"SecretA": "type=crypt\nremote=Cloud:shared-backing\npassword=" + obscure.MustObscure("synthetic-cache-password") + "\n",
		"SecretB": "type=crypt\nremote=Cloud:shared-backing\npassword=" + obscure.MustObscure("synthetic-cache-password") + "\n",
	} {
		member, err := archive.Create(name + ".txt")
		if err != nil {
			t.Fatal(err)
		}
		if _, err = fmt.Fprintf(member, "[%s]\n%s", name, text); err != nil {
			t.Fatal(err)
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := importPackageMode(data.Bytes(), "", "SharedBacking.zip", true); err != nil {
		t.Fatal(err)
	}
	open := func(names []string) {
		t.Helper()
		ctx, finish := scopedOperation("mirror_review")
		defer finish()
		ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
		for _, name := range names {
			f, err := remote(ctx, name)
			if err != nil {
				t.Fatal(err)
			}
			if _, err = f.List(ctx, ""); err != nil {
				t.Fatal(err)
			}
		}
	}
	open([]string{"SecretA", "SecretB"})
	if len(backing) != 1 || backing[0].Err() != nil {
		t.Fatal("fixture did not share a live backing filesystem", len(backing))
	}
	block.Store(true)
	done := make(chan error, 1)
	go func() {
		ctx, finish := scopedOperation("mirror_review")
		defer finish()
		ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
		f, err := remote(ctx, "SecretB")
		if err == nil {
			_, err = f.List(ctx, "")
		}
		done <- err
	}()
	awaitFixture(t, started)
	cancel()
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("cancelled shared backing succeeded")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("cancel did not reach the other client's shared backing")
	}
	if backing[0].Err() == nil {
		t.Fatal("cancelled crypt retained its backing lifecycle")
	}
	block.Store(false)
	// Both cache layers must be replaced, including the client which originally
	// created the backing Fs but was not used directly by the cancelled request.
	open([]string{"SecretB", "SecretA"})
	if len(backing) != 2 || backing[1].Err() != nil {
		t.Fatal("cancelled backing cache was reused", len(backing))
	}
}
