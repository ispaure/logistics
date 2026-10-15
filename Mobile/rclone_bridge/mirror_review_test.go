package main

import (
	"bytes"
	"context"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
)

func TestMirrorReviewUsesSyncComparisonWithoutWriting(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:review-crypt"), ""); err != nil {
		t.Fatal(err)
	}
	f, err := remote(ctx, "Cloud")
	if err != nil {
		t.Fatal(err)
	}
	for name, text := range map[string]string{"replace.txt": "old", "delete.txt": "old"} {
		if _, err := f.Put(ctx, strings.NewReader(text), object.NewStaticObjectInfo("review-plain/"+name, time.Now(), int64(len(text)), true, nil, f)); err != nil {
			t.Fatal(err)
		}
	}
	local, _ := filepath.EvalSymlinks(t.TempDir())
	os.WriteFile(filepath.Join(local, "replace.txt"), []byte("new longer contents"), 0600)
	os.WriteFile(filepath.Join(local, "add.txt"), []byte("added"), 0600)
	identity, _ := connectionIdentity("Cloud")
	run := strings.Repeat("b", 32)
	result, err := mirrorReview(ctx, "Cloud", "review-plain", identity, local, run, true)
	if err != nil {
		t.Fatal(err)
	}
	review := result.(map[string]any)
	changes := map[string]string{}
	for _, row := range review["changes"].([][]string) {
		changes[row[1]] = row[0]
	}
	if changes["add.txt"] != "add" || changes["replace.txt"] != "replace" || changes["delete.txt"] != "delete" {
		t.Fatal(changes)
	}
	if _, err := f.NewObject(ctx, "review-plain/add.txt"); err == nil {
		t.Fatal("review uploaded an addition")
	}
	if _, err := f.NewObject(ctx, "review-plain/delete.txt"); err != nil {
		t.Fatal("review removed a destination file")
	}
	repeated, err := mirrorReview(ctx, "Cloud", "review-plain", identity, local, run, true)
	if err != nil || repeated.(map[string]any)["fingerprint"] != review["fingerprint"] {
		t.Fatal("unchanged review revision is unstable", err)
	}
	os.WriteFile(filepath.Join(local, "add.txt"), []byte("changed after review"), 0600)
	changed, err := mirrorReview(ctx, "Cloud", "review-plain", identity, local, run, true)
	if err != nil || changed.(map[string]any)["fingerprint"] == review["fingerprint"] {
		t.Fatal("changed source did not invalidate review", err)
	}
	missing := filepath.Join(local, "new-local-copy")
	if _, err = mirrorReview(ctx, "Cloud", "review-plain", identity, missing, run, false); err != nil {
		t.Fatal(err)
	}
	if _, err = os.Stat(missing); !os.IsNotExist(err) {
		t.Fatal("review created its proposed destination")
	}
}

func TestCryptReviewDecodesNamesAndDoesNotPersistReports(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:review-private"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, backing, root, _, _ := cryptConnection("Secret")
	f, _ := remote(ctx, backing)
	encrypted, _ := cipher.EncryptData(bytes.NewReader([]byte("private bytes")))
	name := cipher.EncryptFileName("private-note.md")
	if _, err := f.Put(ctx, encrypted, object.NewStaticObjectInfo(root+"/"+name, time.Now(), -1, true, nil, f)); err != nil {
		t.Fatal(err)
	}
	identity, _ := connectionIdentity("Secret")
	local, _ := filepath.EvalSymlinks(t.TempDir())
	result, err := mirrorReview(ctx, "Secret", "", identity, local, strings.Repeat("c", 32), false)
	if err != nil {
		t.Fatal(err)
	}
	rows := result.(map[string]any)["changes"].([][]string)
	if len(rows) != 1 || rows[0][0] != "add" || rows[0][1] != "private-note.md" {
		t.Fatal(rows)
	}
	files, _ := os.ReadDir(local)
	if len(files) != 0 {
		t.Fatal("crypt review wrote local content")
	}
	clearSession()
	comparisonState.Lock()
	cached := comparisonState.current
	comparisonState.Unlock()
	if cached != nil {
		t.Fatal("credential revocation retained plaintext review names")
	}
}

func TestTransferOptionsFollowOrdinaryFileLinksAndKeepExcludedDestination(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:policy-crypt"), ""); err != nil {
		t.Fatal(err)
	}
	f, _ := remote(ctx, "Cloud")
	identity, _ := connectionIdentity("Cloud")
	local, _ := filepath.EvalSymlinks(t.TempDir())
	outside := filepath.Join(t.TempDir(), "target.txt")
	os.WriteFile(outside, []byte("linked contents"), 0600)
	if err := os.Symlink(outside, filepath.Join(local, "linked.txt")); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(local, "new.skip"), []byte("excluded source"), 0600)
	for name, text := range map[string]string{"retained.skip": "excluded destination", "delete.txt": "delete"} {
		if _, err := f.Put(ctx, strings.NewReader(text), object.NewStaticObjectInfo("policy/"+name, time.Now(), int64(len(text)), true, nil, f)); err != nil {
			t.Fatal(err)
		}
	}
	ctx = context.WithValue(ctx, transferOptionsKey{}, transferOptions{TrackRenames: true, Excludes: []string{"*.skip"}})
	run := strings.Repeat("d", 32)
	review, err := mirrorReview(ctx, "Cloud", "policy", identity, local, run, true)
	if err != nil {
		t.Fatal(err)
	}
	rows := review.(map[string]any)["changes"].([][]string)
	for _, row := range rows {
		if strings.HasSuffix(row[1], ".skip") {
			t.Fatal("excluded review entry", row)
		}
	}
	if _, err := mirrorSync(ctx, "Cloud", "policy", identity, local, run, true); err != nil {
		t.Fatal(err)
	}
	if _, err := f.NewObject(ctx, "policy/linked.txt"); err != nil {
		t.Fatal("file link not followed", err)
	}
	if _, err := f.NewObject(ctx, "policy/retained.skip"); err != nil {
		t.Fatal("excluded destination deleted", err)
	}
	if _, err := f.NewObject(ctx, "policy/new.skip"); err == nil {
		t.Fatal("excluded file uploaded")
	}
	if _, err := f.NewObject(ctx, "policy/delete.txt"); err == nil {
		t.Fatal("destination-only file retained")
	}
	// Filters are request-local, and Pull never inherits Push exclusions.
	destination := filepath.Join(local, "pulled")
	os.Mkdir(destination, 0700)
	if _, err := mirrorSync(ctx, "Cloud", "policy", identity, destination, run, false); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(destination, "retained.skip")); err != nil {
		t.Fatal("push filter leaked into pull", err)
	}
	cryptID, _ := connectionIdentity("Secret")
	if _, err := mirrorReview(ctx, "Secret", "", cryptID, local, run, true); err == nil {
		t.Fatal("crypt accepted a link")
	}
}

func TestCryptReviewProjectsCleanupAsDeletionWithoutMutating(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:cleanup-review"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, backing, root, _, _ := cryptConnection("Secret")
	f, _ := remote(ctx, backing)
	raw := cipher.EncryptFileName(".DS_Store")
	data, _ := cipher.EncryptData(strings.NewReader("generated junk"))
	obj, err := f.Put(ctx, data, object.NewStaticObjectInfo(root+"/"+raw, time.Now(), -1, true, nil, f))
	if err != nil {
		t.Fatal(err)
	}
	stream, _ := obj.Open(ctx)
	defer stream.Close()
	local, _ := filepath.EvalSymlinks(t.TempDir())
	file, _ := os.Create(filepath.Join(local, raw))
	if _, err := io.Copy(file, stream); err != nil {
		t.Fatal(err)
	}
	file.Close()
	ctx = context.WithValue(ctx, transferOptionsKey{}, transferOptions{CleanupPaths: []string{raw}})
	identity, _ := connectionIdentity("Secret")
	review, err := mirrorReview(ctx, "Secret", "", identity, local, strings.Repeat("e", 32), true)
	if err != nil {
		t.Fatal(err)
	}
	rows := review.(map[string]any)["changes"].([][]string)
	if len(rows) != 1 || rows[0][0] != "delete" || rows[0][1] != ".DS_Store" {
		t.Fatal(rows)
	}
	if _, err := os.Stat(filepath.Join(local, raw)); err != nil {
		t.Fatal("review deleted local junk", err)
	}
	if _, err := f.NewObject(ctx, root+"/"+raw); err != nil {
		t.Fatal("review deleted remote junk", err)
	}
}

func TestReviewTracksEmptyDirectoryMembershipAndCryptNames(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:review-directories"), ""); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"Cloud", "Secret"} {
		t.Run(name, func(t *testing.T) {
			local, _ := filepath.EvalSymlinks(t.TempDir())
			identity, _ := connectionIdentity(name)
			encode := func(value string) string { return value }
			if name == "Secret" {
				cipher, _, _, _, err := cryptConnection(name)
				if err != nil {
					t.Fatal(err)
				}
				encode = cipher.EncryptDirName
			}
			review := func() map[string]any {
				value, err := mirrorReview(ctx, name, "", identity, local, strings.Repeat("e", 32), true)
				if err != nil {
					t.Fatal(err)
				}
				return value.(map[string]any)
			}
			before := review()
			if err := os.MkdirAll(filepath.Join(local, encode("New empty/Nested")), 0700); err != nil {
				t.Fatal(err)
			}
			after := review()
			if before["fingerprint"] == after["fingerprint"] {
				t.Fatal("Empty folder addition did not invalidate review")
			}
			found := false
			for _, row := range after["changes"].([][]string) {
				if row[0] == "add" && row[1] == "New empty/Nested/" {
					found = true
				}
			}
			if !found {
				t.Fatal("Missing decoded folder addition", after)
			}
			if repeated := review(); repeated["fingerprint"] != after["fingerprint"] {
				t.Fatal("Directory fingerprint is unstable", repeated, after)
			}
			if err := os.RemoveAll(filepath.Join(local, encode("New empty"))); err != nil {
				t.Fatal(err)
			}
			if removed := review(); removed["fingerprint"] != before["fingerprint"] {
				t.Fatal("Removed empty folder remains in review", removed, before)
			}
		})
	}
}
