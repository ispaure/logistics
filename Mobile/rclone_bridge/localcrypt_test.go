package main

import (
	stdzip "archive/zip"
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"io"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/rclone/rclone/fs/config/obscure"
	"github.com/rclone/rclone/fs/object"
	"github.com/yeka/zip"
)

func cryptPackage(t *testing.T, target string) []byte {
	t.Helper()
	var buffer bytes.Buffer
	archive := zip.NewWriter(&buffer)
	for name, text := range map[string]string{
		"Cloud":  "type=memory\n",
		"Secret": "type=crypt\nremote=" + target + "\npassword=" + obscure.MustObscure("synthetic-crypt-password") + "\n",
	} {
		member, err := archive.Create(name + ".txt")
		if err != nil {
			t.Fatal(err)
		}
		_, _ = io.WriteString(member, "["+name+"]\n"+text)
	}
	if err := archive.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func TestLocalCryptCiphertextCopyOfflineDecodeAndLock(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	pkg := cryptPackage(t, "Cloud:localcrypt-fixture")
	if _, err := importPackage(pkg, ""); err != nil {
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
	plain := []byte("# Private mobile sentinel\n")
	encrypted, err := cipher.EncryptData(bytes.NewReader(plain))
	if err != nil {
		t.Fatal(err)
	}
	ciphertext, _ := io.ReadAll(encrypted)
	encryptedName := root + "/" + cipher.EncryptFileName("note.md")
	_, err = f.Put(ctx, bytes.NewReader(ciphertext), object.NewStaticObjectInfo(encryptedName, time.Now(), int64(len(ciphertext)), true, nil, f))
	if err != nil {
		t.Fatal(err)
	}
	rows, err := list(ctx, "Secret", "")
	if err != nil || len(rows) != 1 || rows[0].Path != "note.md" || rows[0].Size != int64(len(plain)) {
		t.Fatalf("listing: %+v %v", rows, err)
	}
	target, err := os.CreateTemp(t.TempDir(), "ciphertext")
	if err != nil {
		t.Fatal(err)
	}
	defer target.Close()
	if _, err = readInto(ctx, "Secret", "note.md", int(target.Fd())); err == nil {
		t.Fatal("plaintext disk download accepted")
	}
	record, err := cryptFetch(ctx, "Secret", "note.md", int(target.Fd()))
	if err != nil {
		t.Fatal(err)
	}
	stored, _ := os.ReadFile(target.Name())
	if !bytes.Equal(stored, ciphertext) || bytes.Contains(stored, plain) {
		t.Fatal("copy was not original ciphertext")
	}
	encodedRecord, _ := json.Marshal(record)
	if bytes.Contains(encodedRecord, []byte("note.md")) || bytes.Contains(encodedRecord, []byte("password")) {
		t.Fatal("metadata leaked plaintext name/key")
	}
	// Remove the remote object: reading the local copy must be genuinely offline.
	obj, _ := f.NewObject(ctx, encryptedName)
	if err := obj.Remove(ctx); err != nil {
		t.Fatal(err)
	}
	reply, err := cryptDecode(ctx, "Secret", record["encrypted_path"], record["identity"], int(target.Fd()))
	if err != nil {
		t.Fatal(err)
	}
	decoded, _ := base64.StdEncoding.DecodeString(reply["data"])
	if !bytes.Equal(decoded, plain) || reply["name"] != "note.md" {
		t.Fatal("decryption differed")
	}
	if _, err = cryptDecode(ctx, "Secret", record["encrypted_path"], strings.Repeat("0", 64), int(target.Fd())); err == nil {
		t.Fatal("wrong settings accepted")
	}
	cancelled, stop := context.WithCancel(ctx)
	stop()
	if _, err = cryptDecode(cancelled, "Secret", record["encrypted_path"], record["identity"], int(target.Fd())); err == nil {
		t.Fatal("cancel ignored")
	}
	clearSession()
	if _, err = cryptDecode(ctx, "Secret", record["encrypted_path"], record["identity"], int(target.Fd())); err == nil {
		t.Fatal("forgotten credentials usable")
	}
	if _, err = importPackage(pkg, ""); err != nil {
		t.Fatal(err)
	}
	if _, err = cryptDecode(ctx, "Secret", record["encrypted_path"], record["identity"], int(target.Fd())); err != nil {
		t.Fatal("reimport did not unlock offline copy", err)
	}
	stored[len(stored)-1] ^= 1
	if _, err = target.WriteAt(stored, 0); err != nil {
		t.Fatal(err)
	}
	if _, err = cryptDecode(ctx, "Secret", record["encrypted_path"], record["identity"], int(target.Fd())); err == nil {
		t.Fatal("corrupt ciphertext accepted")
	}
}

func TestLocalCryptRejectsUnsafeBackingAndPreservesSession(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:safe"), ""); err != nil {
		t.Fatal(err)
	}
	for _, target := range []string{"/private/local", ":local:/tmp", "Secret:loop", "Missing:root", "Cloud:../escape"} {
		if _, err := importPackage(cryptPackage(t, target), ""); err == nil {
			t.Fatal("unsafe target accepted", target)
		}
		if !admitted["Secret"] {
			t.Fatal("failed import replaced session")
		}
	}
}

func TestPrivateArchivePasswordsAndLimits(t *testing.T) {
	for _, method := range []zip.EncryptionMethod{zip.AES256Encryption, zip.StandardEncryption} {
		var input bytes.Buffer
		writer := zip.NewWriter(&input)
		member, err := writer.Encrypt("page.png", "inner-password", method)
		if err != nil {
			t.Fatal(err)
		}
		_, _ = member.Write([]byte("page fixture"))
		if err := writer.Close(); err != nil {
			t.Fatal(err)
		}
		for _, password := range []string{"", "wrong"} {
			if _, err := unlockArchive(context.Background(), input.Bytes(), password); err != archivePasswordError {
				t.Fatalf("password accepted: %v", err)
			}
		}
		view, err := unlockArchive(context.Background(), input.Bytes(), "inner-password")
		if err != nil {
			t.Fatal(err)
		}
		archive, err := zip.NewReader(bytes.NewReader(view), int64(len(view)))
		if err != nil {
			t.Fatal(err)
		}
		if archive.File[0].IsEncrypted() {
			t.Fatal("RAM view still encrypted")
		}
		source, _ := archive.File[0].Open()
		data, err := io.ReadAll(source)
		source.Close()
		if err != nil || string(data) != "page fixture" {
			t.Fatalf("bad content %q %v", data, err)
		}
		if method == zip.AES256Encryption {
			damaged := append([]byte(nil), input.Bytes()...)
			original, _ := zip.NewReader(bytes.NewReader(damaged), int64(len(damaged)))
			offset, err := original.File[0].DataOffset()
			if err != nil {
				t.Fatal(err)
			}
			damaged[offset+int64(original.File[0].CompressedSize64)-1] ^= 1
			if _, err := unlockArchive(context.Background(), damaged, "inner-password"); err == nil {
				t.Fatal("corrupt authentication accepted")
			}
		}
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		if _, err := unlockArchive(ctx, input.Bytes(), "inner-password"); err == nil {
			t.Fatal("ignored cancellation")
		}
	}
	var input bytes.Buffer
	writer := zip.NewWriter(&input)
	member, _ := writer.Create("../escape.png")
	_, _ = member.Write([]byte("x"))
	_ = writer.Close()
	if _, err := unlockArchive(context.Background(), input.Bytes(), ""); err == nil {
		t.Fatal("unsafe archive accepted")
	}
}

func TestCryptEncodeRoundTripAndRefusesOverwrite(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:save-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, _, _, identity, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	encrypted := cipher.EncryptFileName("note.md")
	target, err := os.CreateTemp(t.TempDir(), "ciphertext")
	if err != nil {
		t.Fatal(err)
	}
	defer target.Close()
	plain := []byte("# edited private document\r\n")
	if _, err := cryptEncode(context.Background(), "Secret", encrypted, identity, base64.StdEncoding.EncodeToString(plain), int(target.Fd())); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(target.Name())
	if bytes.Contains(data, plain) {
		t.Fatal("plaintext on disk")
	}
	decoded, err := cryptDecode(context.Background(), "Secret", encrypted, identity, int(target.Fd()))
	if err != nil {
		t.Fatal(err)
	}
	actual, _ := base64.StdEncoding.DecodeString(decoded["data"])
	if !bytes.Equal(actual, plain) {
		t.Fatal("round trip changed bytes")
	}
	if _, err := cryptEncode(context.Background(), "Secret", encrypted, identity, "", int(target.Fd())); err == nil {
		t.Fatal("overwrote existing file")
	}
}

func TestMetadataPatchPreservesInnerPasswordsAndResources(t *testing.T) {
	for _, method := range []zip.EncryptionMethod{zip.AES256Encryption, zip.StandardEncryption} {
		var input bytes.Buffer
		writer := zip.NewWriter(&input)
		page, _ := writer.Encrypt("page.png", "inner", method)
		_, _ = page.Write([]byte("unchanged page bytes"))
		metadata, _ := writer.Encrypt("ComicInfo.xml", "inner", method)
		_, _ = metadata.Write([]byte("<ComicInfo><Title>Before</Title></ComicInfo>"))
		_ = writer.Close()
		replacement := []byte("<ComicInfo><Title>After</Title></ComicInfo>")
		patched, err := patchArchive(context.Background(), input.Bytes(), "inner", "ComicInfo.xml", replacement)
		if err != nil {
			t.Fatal(err)
		}
		before, _ := stdzip.NewReader(bytes.NewReader(input.Bytes()), int64(input.Len()))
		after, _ := stdzip.NewReader(bytes.NewReader(patched), int64(len(patched)))
		oldRaw, _ := before.File[0].OpenRaw()
		oldBytes, _ := io.ReadAll(oldRaw)
		newRaw, _ := after.File[0].OpenRaw()
		newBytes, _ := io.ReadAll(newRaw)
		if !bytes.Equal(oldBytes, newBytes) {
			t.Fatal("unchanged page ciphertext was rewritten")
		}
		archive, _ := zip.NewReader(bytes.NewReader(patched), int64(len(patched)))
		for _, member := range archive.File {
			if !member.IsEncrypted() {
				t.Fatal("inner protection removed")
			}
			member.SetPassword("inner")
			stream, err := member.Open()
			if err != nil {
				t.Fatal(err)
			}
			content, err := io.ReadAll(stream)
			stream.Close()
			if err != nil {
				t.Fatal(err)
			}
			expected := []byte("unchanged page bytes")
			if member.Name == "ComicInfo.xml" {
				expected = replacement
			}
			if !bytes.Equal(content, expected) {
				t.Fatal("resource changed")
			}
		}
		for _, password := range []string{"", "wrong"} {
			if _, err := unlockArchive(context.Background(), patched, password); err == nil {
				t.Fatal("password bypass")
			}
			if _, err := patchArchive(context.Background(), input.Bytes(), password, "ComicInfo.xml", replacement); err == nil {
				t.Fatal("patched without password")
			}
		}
		ctx, cancel := context.WithCancel(context.Background())
		cancel()
		if _, err := patchArchive(ctx, input.Bytes(), "inner", "ComicInfo.xml", replacement); err == nil {
			t.Fatal("cancellation ignored")
		}
	}
}

func TestFileOperationsRawRewrapRejectsPlaintextAndPreservesInnerBytes(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	ctx := context.Background()
	if _, err := importPackage(cryptPackage(t, "Cloud:file-operations"), ""); err != nil {
		t.Fatal(err)
	}
	_, _, _, identity, _ := cryptConnection("Secret")
	first, err := cryptPath("Secret", "folder/archive.cbz", identity, false, false)
	if err != nil {
		t.Fatal(err)
	}
	plain := []byte("opaque inner archive bytes: keep exactly, including inner encryption")
	input, _ := os.CreateTemp(t.TempDir(), "source")
	defer input.Close()
	input.Write(plain)
	encrypted, _ := os.CreateTemp(t.TempDir(), "encrypted")
	defer encrypted.Close()
	if _, err := cryptRawWrite(ctx, "Secret", first["path"], identity, int(input.Fd()), int(encrypted.Fd()), "", "", ""); err != nil {
		t.Fatal(err)
	}
	decoded, err := cryptRawRead(ctx, "Secret", first["path"], identity, int(encrypted.Fd()))
	if err != nil || decoded["data"] != base64.StdEncoding.EncodeToString(plain) {
		t.Fatalf("raw decode: %v", err)
	}
	if _, err := cryptRawRead(ctx, "Secret", first["path"], identity, int(input.Fd())); err == nil {
		t.Fatal("plaintext accepted with encrypted filename")
	}
	if _, err := cryptPath("Secret", "../escape", identity, false, false); err == nil {
		t.Fatal("path traversal accepted")
	}
	// Add a different key to the same admitted package, then rewrap without
	// decrypting/unlocking any archive members.
	store.mu.Lock()
	store.values.Remotes["Other"] = map[string]string{"type": "crypt", "remote": "Cloud:other", "password": obscure.MustObscure("different-synthetic-key")}
	store.mu.Unlock()
	admitted["Other"] = true
	second, err := cryptPath("Other", "new.cbz", "", false, false)
	if err != nil {
		t.Fatal(err)
	}
	output, _ := os.CreateTemp(t.TempDir(), "rewrapped")
	defer output.Close()
	if _, err := cryptRawWrite(ctx, "Other", second["path"], second["identity"], int(encrypted.Fd()), int(output.Fd()), "Secret", first["path"], identity); err != nil {
		t.Fatal(err)
	}
	decoded, err = cryptRawRead(ctx, "Other", second["path"], second["identity"], int(output.Fd()))
	if err != nil || decoded["data"] != base64.StdEncoding.EncodeToString(plain) {
		t.Fatalf("rewrap: %v", err)
	}
	if _, err := cryptRawRead(ctx, "Secret", first["path"], identity, int(output.Fd())); err == nil {
		t.Fatal("different key accepted")
	}
}

func TestINIEncryptedSaveRoundTrip(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:ini-fixture"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, _, _, identity, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	encrypted := cipher.EncryptFileName("Settings.INI")
	file, err := os.CreateTemp(t.TempDir(), "ciphertext")
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	plain := []byte("[Settings]\r\nvalue=private-sentinel\r\n")
	if _, err := cryptEncode(context.Background(), "Secret", encrypted, identity, base64.StdEncoding.EncodeToString(plain), int(file.Fd())); err != nil {
		t.Fatal(err)
	}
	ciphertext, _ := os.ReadFile(file.Name())
	if bytes.Contains(ciphertext, plain) {
		t.Fatal("plaintext persisted")
	}
	decoded, err := cryptDecode(context.Background(), "Secret", encrypted, identity, int(file.Fd()))
	if err != nil {
		t.Fatal(err)
	}
	actual, err := base64.StdEncoding.DecodeString(decoded["data"])
	if err != nil || !bytes.Equal(actual, plain) {
		t.Fatal("INI bytes changed")
	}
}
