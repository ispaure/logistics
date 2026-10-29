// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
)

func TestPullWithoutReviewRestoresMissingLocalContent(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:missing-pull-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	for _, mode := range []struct {
		name    string
		logical bool
	}{{"Cloud", false}, {"Secret", false}, {"Secret", true}} {
		t.Run(mode.name+"-"+map[bool]string{false: "stored", true: "decrypted"}[mode.logical], func(t *testing.T) {
			ctx := context.Background()
			if mode.logical {
				ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
			}
			// Seed through the logical remote, including encryption for Secret.
			online, err := remote(context.WithValue(ctx, mirrorLogicalKey{}, true), mode.name)
			if err != nil {
				t.Fatal(err)
			}
			data := []byte("download missing content")
			if _, err := online.Put(ctx, bytes.NewReader(data), object.NewStaticObjectInfo(
				"nested/note.txt", time.Now(), int64(len(data)), true, nil, online)); err != nil {
				t.Fatal(err)
			}
			info, err := mirrorInfo(ctx, mode.name, "")
			if err != nil {
				t.Fatal(err)
			}
			local := canonicalTestDir(t)
			directory, filename := "nested", "note.txt"
			if mode.name == "Secret" && !mode.logical {
				cipher, _, _, _, err := cryptConnection(mode.name)
				if err != nil {
					t.Fatal(err)
				}
				directory, filename = cipher.EncryptDirName(directory), cipher.EncryptFileName(filename)
			}
			file := filepath.Join(local, directory, filename)
			var expected []byte
			// No review is run. Start empty, then remove just the file, then
			// its whole parent tree between pulls through the real engine.
			for _, missing := range []string{"initial", "file", "tree"} {
				if missing == "file" {
					if err := os.Remove(file); err != nil {
						t.Fatal(err)
					}
				} else if missing == "tree" {
					if err := os.RemoveAll(filepath.Join(local, directory)); err != nil {
						t.Fatal(err)
					}
				}
				if _, err := mirrorSync(ctx, mode.name, info["prefix"].(string), info["identity"].(string),
					local, strings.Repeat("a", 32), false); err != nil {
					t.Fatalf("%s: %v", missing, err)
				}
				got, err := os.ReadFile(file)
				if err != nil {
					t.Fatal(err)
				}
				if expected == nil {
					expected = got
					if mode.name != "Secret" || mode.logical {
						if !bytes.Equal(got, data) {
							t.Fatal("downloaded plaintext differs")
						}
					} else if !bytes.HasPrefix(got, []byte("RCLONE\x00\x00")) {
						t.Fatal("LocalCrypt download is not ciphertext")
					}
				} else if !bytes.Equal(got, expected) {
					t.Fatalf("%s was not restored", missing)
				}
			}
		})
	}
}
