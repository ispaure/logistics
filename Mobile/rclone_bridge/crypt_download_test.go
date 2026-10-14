package main

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"os"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/object"
)

func TestExplicitDecryptedDownloadStreamsAuthenticatesAndPreservesRemote(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:explicit-decrypted-fixture"), ""); err != nil {
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
	// Larger than the bounded in-memory reader: this operation must stream.
	plain := bytes.Repeat([]byte("decrypted-download-sentinel\n"), (33*1024*1024)/27+1)
	reader, err := cipher.EncryptData(bytes.NewReader(plain))
	if err != nil {
		t.Fatal(err)
	}
	ciphertext, err := io.ReadAll(reader)
	if err != nil {
		t.Fatal(err)
	}
	p := "folder/large.txt"
	encryptedPath := root + "/" + cipher.EncryptFileName(p)
	put := func(data []byte) {
		_, err := f.Put(ctx, bytes.NewReader(data), object.NewStaticObjectInfo(encryptedPath, time.Now(), int64(len(data)), true, nil, f))
		if err != nil {
			t.Fatal(err)
		}
	}
	put(ciphertext)
	target, err := os.CreateTemp(t.TempDir(), "decrypted-")
	if err != nil {
		t.Fatal(err)
	}
	defer target.Close()
	request, _ := json.Marshal(map[string]any{"remote": "Secret", "path": p, "fd": int(target.Fd())})
	var reply struct {
		OK     bool   `json:"ok"`
		Result int64  `json:"result"`
		Error  string `json:"error"`
	}
	if err := json.Unmarshal([]byte(dispatch("crypt_read", string(request))), &reply); err != nil || !reply.OK || reply.Result != int64(len(plain)) {
		t.Fatalf("explicit streamed download: %+v %v", reply, err)
	}
	data, _ := os.ReadFile(target.Name())
	if !bytes.Equal(data, plain) {
		t.Fatal("decrypted copy differs")
	}
	if _, err := cryptReadInto(ctx, "Secret", p, int(target.Fd())); err == nil {
		t.Fatal("existing destination accepted")
	}
	obj, err := f.NewObject(ctx, encryptedPath)
	if err != nil {
		t.Fatal(err)
	}
	source, err := obj.Open(ctx)
	if err != nil {
		t.Fatal(err)
	}
	unchanged, err := io.ReadAll(source)
	_ = source.Close()
	if err != nil || !bytes.Equal(unchanged, ciphertext) {
		t.Fatal("remote ciphertext was modified")
	}
	for _, mode := range []string{"cancelled", "corrupt", "unsafe", "ordinary"} {
		out, err := os.CreateTemp(t.TempDir(), "invalid-")
		if err != nil {
			t.Fatal(err)
		}
		operationCtx, name, input := ctx, "Secret", p
		if mode == "cancelled" {
			cancelled, stop := context.WithCancel(ctx)
			stop()
			operationCtx = cancelled
		}
		if mode == "corrupt" {
			bad := append([]byte(nil), ciphertext...)
			bad[len(bad)-1] ^= 1
			put(bad)
		}
		if mode == "unsafe" {
			input = "../escape"
		}
		if mode == "ordinary" {
			name = "Cloud"
		}
		_, err = cryptReadInto(operationCtx, name, input, int(out.Fd()))
		out.Close()
		if err == nil {
			t.Fatal("invalid decrypted download accepted:", mode)
		}
	}
}
