// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"github.com/rclone/rclone/fs/object"
	"io"
	"net/http"
	"path"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/cache"
	"github.com/rclone/rclone/fs/config/configmap"
	"github.com/rclone/rclone/fs/config/obscure"
	"github.com/rclone/rclone/lib/oauthutil"
	"golang.org/x/oauth2"
)

type mirrorOAuthFixtureFs struct{ *fixtureListFS }

func (f *mirrorOAuthFixtureFs) Features() *fs.Features {
	features := *f.fixtureListFS.Features()
	features.ListR = nil
	return &features
}

func TestMirrorLogicalSubfolderCancelsBackingOAuthRefresh(t *testing.T) {
	testOnlineSubfolderCancellation(t, false)
}
func TestDownloadLogicalSubfolderCancelsBackingOAuthRefresh(t *testing.T) {
	testOnlineSubfolderCancellation(t, true)
}

func testOnlineSubfolderCancellation(t *testing.T, download bool) {
	started := make(chan context.Context, 1)
	cancelled := make(chan struct{}, 1)
	release := make(chan struct{})
	memoryInfo, err := fs.Find("memory")
	if err != nil {
		t.Fatal(err)
	}
	replaceFixtureDrive(t, func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
		memory, err := memoryInfo.NewFs(ctx, name, root, configmap.Simple{})
		if err != nil {
			return nil, err
		}
		transport := fixtureRoundTripper(func(r *http.Request) (*http.Response, error) {
			if r.URL.String() != "https://oauth-fixture.invalid/token" {
				return nil, errors.New("unexpected synthetic URL")
			}
			select {
			case started <- r.Context():
			default:
			}
			select {
			case <-r.Context().Done():
				select {
				case cancelled <- struct{}{}:
				default:
				}
				return nil, r.Context().Err()
			case <-release:
				return nil, context.Canceled
			}
		})
		_, tokens, err := oauthutil.NewClientWithBaseClient(ctx, name, m, &oauthutil.Config{ClientID: "synthetic-client", ClientSecret: "synthetic-secret", TokenURL: "https://oauth-fixture.invalid/token", AuthStyle: oauth2.AuthStyleInParams}, &http.Client{Transport: transport})
		if err != nil {
			return nil, err
		}
		if root != "mirror-oauth" {
			t.Logf("subfolder factory root=%s cancellation channel present=%v", root, ctx.Done() != nil)
			if err = tokens.Expire(); err != nil {
				return nil, err
			}
		}
		return &mirrorOAuthFixtureFs{&fixtureListFS{Fs: memory, list: func(request context.Context) (fs.DirEntries, error) {
			if err := request.Err(); err != nil {
				return nil, err
			}
			// Observe refresh cancellation without feeding synthetic failures into rclone accounting.
			_, _ = tokens.Token()
			return nil, nil
		}}}, nil
	})
	var data bytes.Buffer
	archive := zip.NewWriter(&data)
	for name, text := range map[string]string{
		"Cloud":  "type=drive\ntoken=" + syntheticOAuthToken + "\n",
		"Secret": "type=crypt\nremote=Cloud:mirror-oauth\npassword=" + obscure.MustObscure("synthetic-mirror-password") + "\n",
	} {
		member, err := archive.Create(name + ".txt")
		if err != nil {
			t.Fatal(err)
		}
		if _, err = io.WriteString(member, fmt.Sprintf("[%s]\n%s", name, text)); err != nil {
			t.Fatal(err)
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := importPackageMode(data.Bytes(), "", "MirrorOAuth.zip", true); err != nil {
		t.Fatal(err)
	}
	identity, err := connectionIdentity("Secret")
	if err != nil {
		t.Fatal(err)
	}
	payload := map[string]any{"remote": "Secret", "path": "subfolder", "identity": strings.Repeat("f", 64), "local_path": canonicalTestDir(t), "run": strings.Repeat("a", 32), "decrypted": true, "download": download, "directory": true}
	invalid, _ := json.Marshal(payload)
	if raw := dispatch("mirror_sync", string(invalid)); !strings.Contains(raw, `"ok":false`) {
		t.Fatal("changed source identity was accepted", raw)
	}
	payload["identity"] = identity
	input, err := json.Marshal(payload)
	if err != nil {
		t.Fatal(err)
	}
	done := make(chan string, 1)
	go func() { done <- dispatch("mirror_sync", string(input)) }()
	var refreshContext context.Context
	select {
	case refreshContext = <-started:
	case raw := <-done:
		t.Fatalf("mirror returned before OAuth refresh: %s", raw)
	case <-time.After(2 * time.Second):
		close(release)
		t.Fatal("mirror did not reach synthetic refresh")
	}
	requireFixtureReply(t, "cancel", "{}")
	observed := false
	select {
	case <-cancelled:
		observed = true
	case <-time.After(250 * time.Millisecond):
	}
	t.Logf("refresh context after cancellation: %v", refreshContext.Err())
	// Release the baseline's detached refresh and wait for its pinned retry loop,
	// so a failing reproduction cannot leave a goroutine or operation scope alive.
	close(release)
	select {
	case raw := <-done:
		if !strings.Contains(raw, `"ok":false`) {
			t.Fatal(raw)
		}
	case <-time.After(8 * time.Second):
		t.Fatal("mirror did not retire after fixture release")
	}
	if !observed {
		t.Fatal("online subfolder OAuth refresh did not receive request cancellation")
	}
	after, err := connectionIdentity("Secret")
	if err != nil || after != identity {
		t.Fatal("refresh/cancel changed identity", err)
	}
}

func TestCryptDoesNotAdoptUnownedBackingOAuthCache(t *testing.T) {
	started := make(chan context.Context, 1)
	cancelled := make(chan struct{}, 1)
	release := make(chan struct{})
	unownedContext, stopUnowned := context.WithCancel(context.Background())
	defer stopUnowned()
	memoryInfo, err := fs.Find("memory")
	if err != nil {
		t.Fatal(err)
	}
	replaceFixtureDrive(t, func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
		memory, err := memoryInfo.NewFs(ctx, name, root, configmap.Simple{})
		return &mirrorOAuthFixtureFs{&fixtureListFS{Fs: memory, list: func(context.Context) (fs.DirEntries, error) { return nil, nil }}}, err
	})
	var data bytes.Buffer
	archive := zip.NewWriter(&data)
	for name, text := range map[string]string{
		"Cloud":  "type=drive\ntoken=" + syntheticOAuthToken + "\n",
		"Secret": "type=crypt\nremote=Cloud:preseeded\npassword=" + obscure.MustObscure("synthetic-preseed-password") + "\n",
	} {
		member, err := archive.Create(name + ".txt")
		if err != nil {
			t.Fatal(err)
		}
		if _, err = io.WriteString(member, fmt.Sprintf("[%s]\n%s", name, text)); err != nil {
			t.Fatal(err)
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := importPackageMode(data.Bytes(), "", "Preseeded.zip", true); err != nil {
		t.Fatal(err)
	}
	clearStaleFilesystemCache()
	transport := fixtureRoundTripper(func(r *http.Request) (*http.Response, error) {
		if r.URL.String() != "https://oauth-fixture.invalid/token" {
			return nil, errors.New("unexpected synthetic URL")
		}
		select {
		case started <- r.Context():
		default:
		}
		select {
		case <-r.Context().Done():
			select {
			case cancelled <- struct{}{}:
			default:
			}
			return nil, r.Context().Err()
		case <-release:
			return nil, context.Canceled
		}
	})
	_, tokens, err := oauthutil.NewClientWithBaseClient(unownedContext, "Unowned", configmap.Simple{"token": syntheticOAuthToken}, &oauthutil.Config{ClientID: "synthetic-client", ClientSecret: "synthetic-secret", TokenURL: "https://oauth-fixture.invalid/token", AuthStyle: oauth2.AuthStyleInParams}, &http.Client{Transport: transport})
	if err != nil {
		t.Fatal(err)
	}
	if err = tokens.Expire(); err != nil {
		t.Fatal(err)
	}
	memory, err := memoryInfo.NewFs(unownedContext, "Cloud", "preseeded", configmap.Simple{})
	if err != nil {
		t.Fatal(err)
	}
	unowned := &mirrorOAuthFixtureFs{&fixtureListFS{Fs: memory, list: func(context.Context) (fs.DirEntries, error) { _, err := tokens.Token(); return nil, err }}}
	cache.Put("Cloud:preseeded", unowned)
	done := make(chan error, 1)
	go func() {
		ctx, finish := scopedOperation("list")
		defer finish()
		ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
		f, err := remote(ctx, "Secret")
		if err == nil {
			_, err = f.List(ctx, "")
		}
		done <- err
	}()
	select {
	case err := <-done:
		close(release)
		if err != nil {
			t.Fatal(err)
		}
		return // The unowned cached backend was not used.
	case refreshContext := <-started:
		cancel()
		observed := false
		select {
		case <-cancelled:
			observed = true
		case <-time.After(250 * time.Millisecond):
		}
		t.Logf("preseeded refresh context after request cancellation: %v", refreshContext.Err())
		close(release)
		select {
		case <-done:
		case <-time.After(8 * time.Second):
			t.Fatal("preseeded fixture did not retire")
		}
		if !observed {
			t.Fatal("crypt adopted unowned cached backing whose OAuth refresh survives cancellation")
		}
	case <-time.After(2 * time.Second):
		close(release)
		t.Fatal("crypt did not finish or reach preseeded refresh")
	}
}

func TestOwnedCryptFactoryPreservesRootAndFileSemantics(t *testing.T) {
	for _, directoryEncryption := range []string{"true", "false"} {
		t.Run(directoryEncryption, func(t *testing.T) {
			clearSession()
			t.Cleanup(clearSession)
			var data bytes.Buffer
			archive := zip.NewWriter(&data)
			base := "owned-root-semantics-" + directoryEncryption
			for name, text := range map[string]string{
				"Cloud":  "type=memory\n",
				"Secret": "type=crypt\nremote=Cloud:" + base + "\npassword=" + obscure.MustObscure("synthetic-root-password") + "\ndirectory_name_encryption=" + directoryEncryption + "\n",
			} {
				member, err := archive.Create(name + ".txt")
				if err != nil {
					t.Fatal(err)
				}
				if _, err = io.WriteString(member, fmt.Sprintf("[%s]\n%s", name, text)); err != nil {
					t.Fatal(err)
				}
			}
			if err := archive.Close(); err != nil {
				t.Fatal(err)
			}
			if _, err := importPackageMode(data.Bytes(), "", "RootSemantics.zip", true); err != nil {
				t.Fatal(err)
			}
			ctx, finish := scopedOperation("mirror_sync")
			defer finish()
			ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
			cipher, _, _, _, err := cryptConnection("Secret")
			if err != nil {
				t.Fatal(err)
			}
			backing, err := remote(ctx, "Cloud")
			if err != nil {
				t.Fatal(err)
			}
			encrypted, err := cipher.EncryptData(strings.NewReader("synthetic file bytes"))
			if err != nil {
				t.Fatal(err)
			}
			body, err := io.ReadAll(encrypted)
			if err != nil {
				t.Fatal(err)
			}
			physical := path.Join(base, cipher.EncryptFileName("folder/note.txt"))
			if _, err = backing.Put(ctx, bytes.NewReader(body), object.NewStaticObjectInfo(physical, time.Now(), int64(len(body)), true, nil, backing)); err != nil {
				t.Fatal(err)
			}
			directory, err := remoteRootFs(ctx, "Secret", "folder")
			if err != nil {
				t.Fatal(err)
			}
			if directory.Root() != "folder" {
				t.Fatal("logical directory root changed", directory.Root())
			}
			entries, err := directory.List(ctx, "")
			if err != nil || len(entries) != 1 || entries[0].Remote() != "note.txt" {
				t.Fatal("logical directory contents changed", entries, err)
			}
			file, err := remoteRootFs(ctx, "Secret", "folder/note.txt")
			if err != fs.ErrorIsFile || file == nil || file.Root() != "folder" {
				t.Fatal("file probe did not return its logical parent", file, err)
			}
			item, err := file.NewObject(ctx, "note.txt")
			if err != nil {
				t.Fatal(err)
			}
			reader, err := item.Open(ctx)
			if err != nil {
				t.Fatal(err)
			}
			actual, err := io.ReadAll(reader)
			reader.Close()
			if err != nil || string(actual) != "synthetic file bytes" {
				t.Fatal("file-parent view changed logical content", err)
			}
		})
	}
}

func TestOwnedCryptFactoryFallsBackAfterFailedFileProbe(t *testing.T) {
	var roots []string
	var contexts []context.Context
	memoryInfo, err := fs.Find("memory")
	if err != nil {
		t.Fatal(err)
	}
	replaceFixtureDrive(t, func(ctx context.Context, name, root string, m configmap.Mapper) (fs.Fs, error) {
		roots = append(roots, root)
		contexts = append(contexts, ctx)
		if root != "fallback/folder" {
			return nil, errors.New("synthetic failed file probe")
		}
		memory, err := memoryInfo.NewFs(ctx, name, root, configmap.Simple{})
		return &mirrorOAuthFixtureFs{&fixtureListFS{Fs: memory, list: func(context.Context) (fs.DirEntries, error) { return nil, nil }}}, err
	})
	var data bytes.Buffer
	archive := zip.NewWriter(&data)
	for name, text := range map[string]string{
		"Cloud":  "type=drive\ntoken=" + syntheticOAuthToken + "\n",
		"Secret": "type=crypt\nremote=Cloud:fallback\npassword=" + obscure.MustObscure("synthetic-fallback-password") + "\ndirectory_name_encryption=false\n",
	} {
		member, err := archive.Create(name + ".txt")
		if err != nil {
			t.Fatal(err)
		}
		if _, err = io.WriteString(member, fmt.Sprintf("[%s]\n%s", name, text)); err != nil {
			t.Fatal(err)
		}
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err := importPackageMode(data.Bytes(), "", "Fallback.zip", true); err != nil {
		t.Fatal(err)
	}
	ctx, finish := scopedOperation("mirror_sync")
	defer finish()
	ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
	f, err := remoteRootFs(ctx, "Secret", "folder")
	if err != nil {
		t.Fatal(err)
	}
	if f.Root() != "folder" || len(roots) != 2 || roots[0] == roots[1] || roots[1] != "fallback/folder" {
		t.Fatal("crypt file/directory probe order changed", roots)
	}
	if contexts[0].Err() == nil || contexts[1].Done() == nil || contexts[1].Err() != nil {
		t.Fatal("probe failure or directory lifecycle was not owned")
	}
	if _, err = f.List(ctx, ""); err != nil {
		t.Fatal(err)
	}
}

func TestOwnedCryptRootsKeepPackageAliasesSeparate(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	for _, label := range []string{"First.zip", "Second.zip"} {
		if _, err := importPackageMode(cryptPackage(t, "Cloud:alias-root"), "", label, true); err != nil {
			t.Fatal(err)
		}
	}
	ctx, finish := scopedOperation("mirror_sync")
	defer finish()
	ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
	var filesystems []fs.Fs
	for index, label := range []string{"First.zip", "Second.zip"} {
		alias := packageAlias(t, label, "Secret")
		backingAlias := packageAlias(t, label, "Cloud")
		f, err := remoteRootFs(ctx, alias, "folder")
		if err != nil {
			t.Fatal(err)
		}
		if f.Features().UnWrap().Name() != backingAlias {
			t.Fatal("crypt resolved backing from another package", alias, backingAlias)
		}
		text := fmt.Sprintf("synthetic-package-%d", index)
		// Separate synthetic logical paths avoid memory backend's intentionally
		// process-global buckets; the backend name assertion checks alias routing.
		filename := fmt.Sprintf("note-%d.txt", index)
		if _, err = f.Put(ctx, strings.NewReader(text), object.NewStaticObjectInfo(filename, time.Now(), int64(len(text)), true, nil, f)); err != nil {
			t.Fatal(err)
		}
		filesystems = append(filesystems, f)
	}
	for index, f := range filesystems {
		item, err := f.NewObject(ctx, fmt.Sprintf("note-%d.txt", index))
		if err != nil {
			t.Fatal(err)
		}
		reader, err := item.Open(ctx)
		if err != nil {
			t.Fatal(err)
		}
		actual, err := io.ReadAll(reader)
		reader.Close()
		if err != nil || string(actual) != fmt.Sprintf("synthetic-package-%d", index) {
			t.Fatal("aliased crypt content changed", err)
		}
	}
}
