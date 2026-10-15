package main

import (
	stdzip "archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/object"
)

func canonicalTestDir(t *testing.T) string {
	t.Helper()
	folder, err := filepath.EvalSymlinks(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	return folder
}

func TestMirrorAuthenticatedSyncAndRemoteConflict(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:mirror-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"Cloud", "Secret"} {
		info, err := mirrorInfo(ctx, name, "authenticated-"+name)
		if err != nil {
			t.Fatal(err)
		}
		identity, prefix := info["identity"].(string), info["prefix"].(string)
		f, root, cipher, _, err := mirrorConnection(ctx, name, identity)
		if err != nil {
			t.Fatal(err)
		}
		filename, empty := "note.txt", "empty-folder"
		encode := func(data []byte) []byte {
			if cipher == nil {
				return data
			}
			reader, err := cipher.EncryptData(bytes.NewReader(data))
			if err != nil {
				t.Fatal(err)
			}
			data, err = io.ReadAll(reader)
			if err != nil {
				t.Fatal(err)
			}
			return data
		}
		if cipher != nil {
			filename, empty = cipher.EncryptFileName(filename), cipher.EncryptDirName(empty)
		}
		physical := path.Join(root, prefix, filename)
		seed := func(data []byte) {
			_, err := f.Put(ctx, bytes.NewReader(data), object.NewStaticObjectInfo(physical, time.Now(), int64(len(data)), true, nil, f))
			if err != nil {
				t.Fatal(err)
			}
		}
		readRemote := func() []byte {
			obj, err := f.NewObject(ctx, physical)
			if err != nil {
				t.Fatal(err)
			}
			reader, err := obj.Open(ctx)
			if err != nil {
				t.Fatal(err)
			}
			defer reader.Close()
			data, err := io.ReadAll(reader)
			if err != nil {
				t.Fatal(err)
			}
			return data
		}
		initial := encode([]byte("old remote bytes"))
		seed(initial)
		local := canonicalTestDir(t)
		if _, err := mirrorSync(ctx, name, prefix, identity, local, strings.Repeat("a", 32), false); err != nil {
			t.Fatal(err)
		}
		actual, err := os.ReadFile(filepath.Join(local, filename))
		if err != nil || !bytes.Equal(actual, initial) {
			t.Fatal("pull did not retain source bytes", err)
		}
		updated := encode([]byte("updated local bytes"))
		if err := os.WriteFile(filepath.Join(local, filename), updated, 0600); err != nil {
			t.Fatal(err)
		}
		source, err := os.Open(filepath.Join(local, filename))
		if err != nil {
			t.Fatal(err)
		}
		checked, err := mirrorValidate(ctx, name, path.Join(prefix, filename), identity, int(source.Fd()))
		source.Close()
		if err != nil || checked != fmt.Sprintf("%x", sha256.Sum256(updated)) {
			t.Fatal("preflight failed", err)
		}
		if cipher != nil {
			corrupt, err := os.CreateTemp(t.TempDir(), "corrupt")
			if err != nil {
				t.Fatal(err)
			}
			corrupt.Write(updated[:len(updated)-1])
			corrupt.Seek(0, 0)
			_, err = mirrorValidate(ctx, name, path.Join(prefix, filename), identity, int(corrupt.Fd()))
			corrupt.Close()
			if err == nil {
				t.Fatal("corrupt ciphertext passed preflight")
			}
			if !bytes.Equal(readRemote(), initial) {
				t.Fatal("validation changed remote")
			}
		}
		os.Mkdir(filepath.Join(local, empty), 0700)
		before, err := mirrorReview(ctx, name, prefix, identity, local, strings.Repeat("b", 32), true)
		if err != nil {
			t.Fatal(err)
		}
		seed(encode([]byte("external mutation with different length")))
		after, err := mirrorReview(ctx, name, prefix, identity, local, strings.Repeat("c", 32), true)
		if err != nil || before.(map[string]any)["fingerprint"] == after.(map[string]any)["fingerprint"] {
			t.Fatal("external mutation did not invalidate review", err)
		}
		if _, err := mirrorSync(ctx, name, prefix, identity, local, strings.Repeat("d", 32), true); err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(readRemote(), updated) {
			t.Fatal("push contents differ")
		}
		verify := canonicalTestDir(t)
		if _, err := mirrorSync(ctx, name, prefix, identity, verify, strings.Repeat("e", 32), false); err != nil {
			t.Fatal(err)
		}
		if st, err := os.Stat(filepath.Join(verify, empty)); f.Features().CanHaveEmptyDirectories && (err != nil || !st.IsDir()) {
			t.Fatal("empty folder not preserved", err)
		}
		if _, err := mirrorSync(ctx, name, prefix, strings.Repeat("f", 64), local, strings.Repeat("f", 32), true); err == nil {
			t.Fatal("different connection accepted")
		}
	}
}

func TestLocalImageDispatchDoesNotWaitForRemoteTransfer(t *testing.T) {
	archive, err := os.CreateTemp(t.TempDir(), "ordinary-comic")
	if err != nil {
		t.Fatal(err)
	}
	writer := stdzip.NewWriter(archive)
	member, err := writer.Create("page.png")
	if err != nil {
		t.Fatal(err)
	}
	member.Write([]byte("synthetic comic page bytes"))
	writer.Close()
	input, _ := json.Marshal(map[string]any{"fd": int(archive.Fd()), "member": "page.png"})
	defer archive.Close()
	serial.Lock()
	ctx, finish := operation("mirror_sync")
	defer finish()
	done := make(chan string, 1)
	go func() { done <- dispatch("file_archive", string(input)) }()
	select {
	case reply := <-done:
		var value map[string]any
		if json.Unmarshal([]byte(reply), &value) != nil || value["ok"] != true {
			serial.Unlock()
			t.Fatal("ordinary comic member failed", reply)
		}
	case <-time.After(time.Second):
		serial.Unlock()
		t.Fatal("local image work blocked behind remote transfer")
	}
	if ctx.Err() != nil {
		serial.Unlock()
		t.Fatal("local reading cancelled the transfer")
	}
	cancel()
	if ctx.Err() == nil {
		serial.Unlock()
		t.Fatal("local reading lost the transfer cancellation handle")
	}
	serial.Unlock()
}

func TestMirrorLogicalCryptPullAndPush(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.WithValue(context.Background(), mirrorLogicalKey{}, true)
	if _, err := importPackage(cryptPackage(t, "Cloud:logical-mirror-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	info, err := mirrorInfo(ctx, "Secret", "")
	if err != nil || info["crypt"] != false {
		t.Fatal(info, err)
	}
	identity := info["identity"].(string)
	local := canonicalTestDir(t)
	data := []byte("plaintext local edit")
	os.WriteFile(filepath.Join(local, "note.txt"), data, 0600)
	source, err := os.Open(filepath.Join(local, "note.txt"))
	if err != nil {
		t.Fatal(err)
	}
	checked, err := mirrorValidate(ctx, "Secret", "note.txt", identity, int(source.Fd()))
	source.Close()
	if err != nil || checked == "" {
		t.Fatal(err)
	}
	if _, err := mirrorSync(ctx, "Secret", "", identity, local, strings.Repeat("c", 32), true); err != nil {
		t.Fatal(err)
	}
	plain := canonicalTestDir(t)
	if _, err := mirrorSync(ctx, "Secret", "", identity, plain, strings.Repeat("d", 32), false); err != nil {
		t.Fatal(err)
	}
	result, err := os.ReadFile(filepath.Join(plain, "note.txt"))
	if err != nil || !bytes.Equal(data, result) {
		t.Fatal("logical pull did not return plaintext", err)
	}
	raw := canonicalTestDir(t)
	if _, err := mirrorSync(context.Background(), "Secret", "", identity, raw, strings.Repeat("e", 32), false); err != nil {
		t.Fatal(err)
	}
	entries, err := os.ReadDir(raw)
	if err != nil || len(entries) != 1 || entries[0].Name() == "note.txt" {
		t.Fatal("backing names not encrypted", err)
	}
	encrypted, err := os.ReadFile(filepath.Join(raw, entries[0].Name()))
	if err != nil || bytes.Equal(data, encrypted) {
		t.Fatal("backing bytes not encrypted", err)
	}
}

func TestNativeRcloneSyncDeletesDestinationOnlyFilesWithoutBackups(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:sync-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	for _, mode := range []struct {
		name    string
		logical bool
	}{{"Cloud", false}, {"Secret", false}, {"Secret", true}} {
		ctx := context.Background()
		if mode.logical {
			ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
		}
		title := mode.name
		if mode.logical {
			title += "-logical"
		} else {
			title += "-raw"
		}
		info, err := mirrorInfo(ctx, mode.name, title)
		if err != nil {
			t.Fatal(err)
		}
		prefix := info["prefix"].(string)
		identity := info["identity"].(string)
		local := t.TempDir()
		canonical, err := filepath.EvalSymlinks(local)
		if err != nil {
			t.Fatal(err)
		}
		filename := "note.txt"
		if mode.name == "Secret" && !mode.logical {
			cipher, _, _, _, _ := cryptConnection("Secret")
			filename = cipher.EncryptFileName(filename)
			stream, e := cipher.EncryptData(strings.NewReader("initial"))
			if e != nil {
				t.Fatal(e)
			}
			bytes, e := io.ReadAll(stream)
			if e != nil {
				t.Fatal(e)
			}
			if e = os.WriteFile(filepath.Join(canonical, filename), bytes, 0600); e != nil {
				t.Fatal(e)
			}
		} else if err = os.WriteFile(filepath.Join(canonical, filename), []byte("initial"), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err = mirrorSync(ctx, mode.name, prefix, identity, canonical, strings.Repeat("a", 32), true); err != nil {
			t.Fatal(title, err)
		}
		// A second identical push transfers nothing: use the normal incremental rclone path.
		if count, e := mirrorSync(ctx, mode.name, prefix, identity, canonical, strings.Repeat("b", 32), true); e != nil || count != 0 {
			t.Fatalf("incremental %s: %d %v", title, count, e)
		}
		if err = os.Remove(filepath.Join(canonical, filename)); err != nil {
			t.Fatal(err)
		}
		if _, err = mirrorSync(ctx, mode.name, prefix, identity, canonical, strings.Repeat("c", 32), true); err != nil {
			t.Fatal(err)
		}
		backend, root, _, _, err := mirrorConnection(ctx, mode.name, identity)
		if err != nil {
			t.Fatal(err)
		}
		rows, err := backend.List(ctx, path.Join(root, prefix))
		if err != nil || len(rows) != 0 {
			t.Fatalf("push must remove destination-only files: %v %v", rows, err)
		}
		// Pull from that empty remote deletes a local-only file and creates no snapshots.
		if err = os.WriteFile(filepath.Join(canonical, "local-only"), []byte("delete"), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err = mirrorSync(ctx, mode.name, prefix, identity, canonical, strings.Repeat("d", 32), false); err != nil {
			t.Fatal(err)
		}
		children, _ := os.ReadDir(canonical)
		if len(children) != 0 {
			t.Fatal("pull did not remove destination-only local files")
		}
	}
}

// Exercise both a decrypted Local pull and a ciphertext LocalCrypt pull through
// the embedded sync engine, observing its real accounting while it is running.
func TestNativeCryptPullReportsLiveProgress(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:progress-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	for _, logical := range []bool{false, true} {
		ctx := context.Background()
		if logical {
			ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
		}
		info, err := mirrorInfo(ctx, "Secret", "")
		if err != nil {
			t.Fatal(err)
		}
		local, err := filepath.EvalSymlinks(t.TempDir())
		if err != nil {
			t.Fatal(err)
		}
		data := bytes.Repeat([]byte("fixture"), 128*1024)
		name := "large.bin"
		if !logical {
			cipher, _, _, _, _ := cryptConnection("Secret")
			name = cipher.EncryptFileName(name)
			encrypted, err := cipher.EncryptData(bytes.NewReader(data))
			if err != nil {
				t.Fatal(err)
			}
			data, err = io.ReadAll(encrypted)
			if err != nil {
				t.Fatal(err)
			}
		}
		file := filepath.Join(local, name)
		if err := os.WriteFile(file, data, 0600); err != nil {
			t.Fatal(err)
		}
		prefix, identity := info["prefix"].(string), info["identity"].(string)
		if _, err := mirrorSync(ctx, "Secret", prefix, identity, local, strings.Repeat("e", 32), true); err != nil {
			t.Fatal(err)
		}
		if err := os.Remove(file); err != nil {
			t.Fatal(err)
		}
		ctx, config := fs.AddConfig(ctx)
		if err := config.BwLimit.Set("256K"); err != nil {
			t.Fatal(err)
		}
		accounting.TokenBucket.StartTokenBucket(ctx)
		t.Cleanup(func() { accounting.TokenBucket.SetBwLimit(fs.BwPair{}) })
		cipher, _, _, cipherIdentity, err := cryptConnection("Secret")
		if err != nil {
			t.Fatal(err)
		}
		probe, err := os.CreateTemp(t.TempDir(), "existing-ciphertext")
		if err != nil {
			t.Fatal(err)
		}
		defer probe.Close()
		encrypted, err := cipher.EncryptData(bytes.NewReader([]byte("read during download")))
		if err != nil {
			t.Fatal(err)
		}
		if _, err = io.Copy(probe, encrypted); err != nil {
			t.Fatal(err)
		}
		readInput, _ := json.Marshal(map[string]any{"remote": "Secret", "identity": cipherIdentity,
			"path": cipher.EncryptFileName("existing.md"), "fd": int(probe.Fd()), "count": 4})
		finished := make(chan error, 1)
		var transferFinished atomic.Bool
		run := strings.Repeat("f", 32)
		go func() {
			_, finish := scopedOperation("mirror_sync")
			_, err := mirrorSync(ctx, "Secret", prefix, identity, local, run, false)
			transferFinished.Store(true)
			finish()
			finished <- err
		}()
		deadline := time.After(12 * time.Second)
		ticker := time.NewTicker(30 * time.Millisecond)
		sawLive := false
		readWhileDownloading := false
		waiting := true
		for waiting {
			select {
			case err := <-finished:
				if err != nil {
					t.Fatal(err)
				}
				waiting = false
			case <-deadline:
				t.Fatal("crypt pull did not finish")
			case <-ticker.C:
				mirrorProgressState.Lock()
				if mirrorProgressState.Run == run && mirrorProgressState.Done > 0 && mirrorProgressState.Done < mirrorProgressState.Total && mirrorProgressState.Active > 0 && mirrorProgressState.TotalFiles > 0 {
					sawLive = true
				}
				mirrorProgressState.Unlock()
				if sawLive && !readWhileDownloading {
					var reply struct {
						OK bool `json:"ok"`
					}
					json.Unmarshal([]byte(dispatch("crypt_range", string(readInput))), &reply)
					if !reply.OK || transferFinished.Load() {
						t.Fatal("existing LocalCrypt file could not be read until download finished")
					}
					readWhileDownloading = true
				}
			}
		}
		ticker.Stop()
		if !sawLive || !readWhileDownloading {
			t.Fatal("no live bytes, totals or active transfers observed")
		}
		mirrorProgressState.Lock()
		files, done, total := mirrorProgressState.Files, mirrorProgressState.Done, mirrorProgressState.Total
		mirrorProgressState.Unlock()
		if files != 1 || done != int64(len(data)) || total != done {
			t.Fatalf("final stats: files=%d bytes=%d total=%d", files, done, total)
		}
		pulled, err := os.ReadFile(file)
		if err != nil || !bytes.Equal(pulled, data) {
			t.Fatal("pull contents differ", err)
		}
	}
}

func TestRetiredMirrorOperationsAreRejected(t *testing.T) {
	for _, action := range []string{"mirror_list", "mirror_read", "mirror_stat", "mirror_mkdir", "mirror_write"} {
		var reply map[string]any
		if err := json.Unmarshal([]byte(dispatch(action, `{}`)), &reply); err != nil || reply["ok"] != false || reply["error"] != "unsupported mobile operation" {
			t.Fatal(action, reply, err)
		}
	}
}

func TestMirrorValidationDescriptorSafeguards(t *testing.T) {
	if _, err := mirrorInput(0); err == nil {
		t.Fatal("accepted standard descriptor")
	}
	file, err := os.CreateTemp(t.TempDir(), "source")
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	file.Write([]byte("fixture"))
	if _, err := mirrorInput(int(file.Fd())); err == nil {
		t.Fatal("accepted nonzero offset")
	}
	file.Seek(0, 0)
	if err := os.Link(file.Name(), file.Name()+"-link"); err != nil {
		t.Fatal(err)
	}
	if _, err := mirrorInput(int(file.Fd())); err == nil {
		t.Fatal("accepted hard linked source")
	}
	read, write, err := os.Pipe()
	if err != nil {
		t.Fatal(err)
	}
	defer read.Close()
	defer write.Close()
	if _, err := mirrorInput(int(read.Fd())); err == nil {
		t.Fatal("accepted pipe")
	}
	dir, err := os.Open(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	defer dir.Close()
	if _, err := mirrorInput(int(dir.Fd())); err == nil {
		t.Fatal("accepted directory")
	}
}
