package main

import (
	stdzip "archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
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
		checked, err := mirrorValidate(ctx, name, p, identity, int(source.Fd()))
		if err != nil || checked == expected {
			t.Fatal("local preflight failed", err)
		}
		if name == "Secret" {
			corrupt, e := os.CreateTemp(t.TempDir(), "corrupt")
			if e != nil {
				t.Fatal(e)
			}
			corrupt.Write(updated[:len(updated)-1])
			corrupt.Seek(0, 0)
			if _, e = mirrorValidate(ctx, name, p, identity, int(corrupt.Fd())); e == nil {
				t.Fatal("corrupt ciphertext passed preflight")
			}
			corrupt.Close()
			current, e := mirrorStat(ctx, name, p, identity)
			if e != nil || current != expected {
				t.Fatal("preflight changed remote bytes")
			}
		}
		source.Seek(0, 0)
		folder := "empty-folder"
		if name == "Secret" {
			folder = cipher.EncryptDirName(folder)
		}
		if _, err = mirrorMkdir(ctx, name, folder, identity); err != nil {
			t.Fatal(err)
		}
		next, err := mirrorWrite(ctx, name, p, identity, expected, strings.Repeat("a", 32), int(source.Fd()))
		if err != nil || next == expected {
			t.Fatal(err)
		}
		source.Seek(0, 0)
		if _, err = mirrorWrite(ctx, name, p, identity, expected, strings.Repeat("b", 32), int(source.Fd())); err == nil {
			t.Fatal("stale remote revision was overwritten")
		}
		source.Close()
		backup := path.Join(".logistics-backups", strings.Repeat("a", 32), "mirror-note.txt")
		if name == "Secret" {
			backup = cipher.EncryptFileName(backup)
		}
		if _, err = f.NewObject(ctx, path.Join(rootFor(name, root), backup)); err == nil {
			t.Fatal("plain sync must not create backups")
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
	ctx, finish := operation("mirror_read")
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
	if err != nil || info["crypt"] != false || info["prefix"] != "" {
		t.Fatalf("logical info: %v %v", info, err)
	}
	identity := info["identity"].(string)
	source, err := os.CreateTemp(t.TempDir(), "plain-source")
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()
	data := []byte("plaintext local edit")
	source.Write(data)
	source.Seek(0, 0)
	checked, err := mirrorValidate(ctx, "Secret", "note.txt", identity, int(source.Fd()))
	if err != nil {
		t.Fatal(err)
	}
	source.Seek(0, 0)
	actual, err := mirrorWrite(ctx, "Secret", "note.txt", identity, "", strings.Repeat("c", 32), int(source.Fd()))
	if err != nil || actual != checked {
		t.Fatalf("logical push: %s %v", actual, err)
	}
	rows, err := mirrorList(ctx, "Secret", "", identity)
	if err != nil || len(rows) != 1 || rows[0].Path != "note.txt" {
		t.Fatalf("logical list: %v %v", rows, err)
	}
	output, err := os.CreateTemp(t.TempDir(), "plain-pull")
	if err != nil {
		t.Fatal(err)
	}
	defer output.Close()
	if _, err = mirrorRead(ctx, "Secret", "note.txt", identity, int(output.Fd())); err != nil {
		t.Fatal(err)
	}
	output.Seek(0, 0)
	result, _ := io.ReadAll(output)
	if !bytes.Equal(data, result) {
		t.Fatal("logical pull did not return plaintext")
	}
	raw := context.Background()
	rawInfo, err := mirrorInfo(raw, "Secret", "")
	if err != nil || rawInfo["crypt"] != true {
		t.Fatal(err)
	}
	rawRows, err := mirrorList(raw, "Secret", "", identity)
	if err != nil || rawRows[0].Path == "note.txt" {
		t.Fatal("backing names were not encrypted", err)
	}
	output2, _ := os.CreateTemp(t.TempDir(), "raw-pull")
	defer output2.Close()
	if _, err = mirrorRead(raw, "Secret", rawRows[0].Path, identity, int(output2.Fd())); err != nil {
		t.Fatal(err)
	}
	output2.Seek(0, 0)
	encrypted, _ := io.ReadAll(output2)
	if bytes.Equal(data, encrypted) {
		t.Fatal("backing bytes were not encrypted")
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
		rows, err := mirrorList(ctx, mode.name, prefix, identity)
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
		finished := make(chan error, 1)
		run := strings.Repeat("f", 32)
		go func() { _, err := mirrorSync(ctx, "Secret", prefix, identity, local, run, false); finished <- err }()
		deadline := time.After(12 * time.Second)
		ticker := time.NewTicker(30 * time.Millisecond)
		sawLive := false
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
			}
		}
		ticker.Stop()
		if !sawLive {
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
