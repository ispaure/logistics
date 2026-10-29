// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"bytes"
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
)

func TestFolderListingsHaveNoEntryCap(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:uncapped-crypt-list"), ""); err != nil {
		t.Fatal(err)
	}
	cloud, err := remote(ctx, "Cloud")
	if err != nil {
		t.Fatal(err)
	}
	cipher, _, root, _, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 1005; i++ {
		name := fmt.Sprintf("match-%04d.txt", i)
		// Empty crypt objects still need a valid encrypted size for listing.
		encrypted, err := cipher.EncryptData(bytes.NewReader(nil))
		if err != nil {
			t.Fatal(err)
		}
		var data bytes.Buffer
		if _, err := data.ReadFrom(encrypted); err != nil {
			t.Fatal(err)
		}
		for _, target := range []string{"uncapped-plain-list/" + name, root + "/" + cipher.EncryptFileName(name)} {
			if _, err := cloud.Put(ctx, bytes.NewReader(data.Bytes()), object.NewStaticObjectInfo(target, time.Now(), int64(data.Len()), true, nil, cloud)); err != nil {
				t.Fatal(err)
			}
		}
	}
	for _, scope := range []struct{ name, dir string }{{"Cloud", "uncapped-plain-list"}, {"Secret", ""}} {
		rows, err := list(ctx, scope.name, scope.dir)
		if err != nil || len(rows) != 1005 {
			t.Fatalf("%s listing: %d rows, %v", scope.name, len(rows), err)
		}
		if !bytes.HasSuffix([]byte(rows[len(rows)-1].Path), []byte("match-1004.txt")) {
			t.Fatal("last entry missing")
		}
	}
}
