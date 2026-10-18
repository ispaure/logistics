package main

import (
	"bytes"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"io"
	"testing"

	"github.com/yeka/zip"
)

func documentCredentialZIP(t *testing.T, password, name string) []byte {
	t.Helper()
	buffer := &bytes.Buffer{}
	writer := zip.NewWriter(buffer)
	member, err := writer.Encrypt("Drive.txt", password, zip.AES256Encryption)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = member.Write([]byte("[" + name + "]\ntype = memory\n")); err != nil {
		t.Fatal(err)
	}
	if err = writer.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}

func TestDocumentListsAES256CredentialPasswordAndLock(t *testing.T) {
	clearSession()
	defer clearSession()
	credential := documentCredentialZIP(t, "credential-password", "Drive")
	if _, err := importPackageWithAliases(credential, "credential-password", "Session.zip", true, nil); err != nil {
		t.Fatal(err)
	}
	id := documentListID(packageID("Session.zip"))
	if len(id) != 64 {
		t.Fatal("missing credential-bound document cache")
	}
	payload := []byte(`{"version":1,"open":["Secret/path.md"],"recent":[]}`)
	encrypted, err := documentLists(id, payload, false)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(encrypted, []byte("Secret")) {
		t.Fatal("plaintext filename leaked")
	}
	input, _ := json.Marshal(map[string]string{"id": id, "data": base64.StdEncoding.EncodeToString(encrypted)})
	var reply struct {
		OK     bool   `json:"ok"`
		Result string `json:"result"`
	}
	if err := json.Unmarshal([]byte(dispatch("document_lists_open", string(input))), &reply); err != nil || !reply.OK {
		t.Fatal("document cache bridge dispatch failed", err)
	}
	viaBridge, _ := base64.StdEncoding.DecodeString(reply.Result)
	if !bytes.Equal(viaBridge, payload) {
		t.Fatal("bridge cache payload changed")
	}
	archive, err := zip.NewReader(bytes.NewReader(encrypted), int64(len(encrypted)))
	if err != nil || len(archive.File) != 1 {
		t.Fatal("not a ZIP archive", err)
	}
	member := archive.File[0]
	if !member.IsEncrypted() || !aes256Member(member) {
		t.Fatal("cache is not AES-256 ZIP")
	}
	member.SetPassword("credential-password")
	stream, err := member.Open()
	if err != nil {
		t.Fatal(err)
	}
	value, err := io.ReadAll(stream)
	stream.Close()
	if err != nil || !bytes.Equal(value, payload) {
		t.Fatal("credential password could not open ZIP", err)
	}
	clearSession()
	if _, err := documentLists(id, encrypted, true); err == nil {
		t.Fatal("locked cache opened")
	}
	if _, err := importPackageWithAliases(credential, "wrong", "Session.zip", true, nil); err == nil {
		t.Fatal("wrong credential password accepted")
	}
	if _, err := documentLists(id, encrypted, true); err == nil {
		t.Fatal("failed credential import unlocked cache")
	}
	if _, err := importPackageWithAliases(credential, "credential-password", "Session.zip", true, nil); err != nil {
		t.Fatal(err)
	}
	restored, err := documentLists(id, encrypted, true)
	if err != nil || !bytes.Equal(restored, payload) {
		t.Fatal("cache did not restore after credential unlock", err)
	}
	encrypted[len(encrypted)/3] ^= 0x40
	if _, err := documentLists(id, encrypted, true); err == nil {
		t.Fatal("tampered cache authenticated")
	}
}

func TestDocumentListsIsolationReplacementBoundsAndPlainZIP(t *testing.T) {
	clearSession()
	defer clearSession()
	first := documentCredentialZIP(t, "one", "One")
	if _, err := importPackageWithAliases(first, "one", "One.zip", true, nil); err != nil {
		t.Fatal(err)
	}
	firstID := documentListID(packageID("One.zip"))
	encrypted, err := documentLists(firstID, []byte(`{"paths":["private"]}`), false)
	if err != nil {
		t.Fatal(err)
	}
	second := documentCredentialZIP(t, "two", "Two")
	if _, err := importPackageWithAliases(second, "two", "Two.zip", true, nil); err != nil {
		t.Fatal(err)
	}
	secondID := documentListID(packageID("Two.zip"))
	if _, err := documentLists(secondID, encrypted, true); err == nil {
		t.Fatal("unrelated credential opened cache")
	}
	if _, err := documentLists(firstID, bytes.Repeat([]byte{'x'}, documentListLimit+1), false); err == nil {
		t.Fatal("oversized cache accepted")
	}
	// Replacing a credential file at the same label retires its old password.
	if _, err := importPackageWithAliases(second, "two", "One.zip", true, nil); err != nil {
		t.Fatal(err)
	}
	if _, err := documentLists(firstID, encrypted, true); err == nil {
		t.Fatal("replaced credential still available")
	}
	plain := &bytes.Buffer{}
	writer := zip.NewWriter(plain)
	file, _ := writer.Create("Plain.txt")
	file.Write([]byte("[Plain]\ntype = memory\n"))
	writer.Close()
	if _, err := importPackageWithAliases(plain.Bytes(), "unused", "Plain.zip", true, nil); err != nil {
		t.Fatal(err)
	}
	if documentListID(packageID("Plain.zip")) != "" {
		t.Fatal("unencrypted credential enabled password cache")
	}
	// AES extra-field strength is explicitly checked, including truncated extras.
	fake := &zip.File{FileHeader: zip.FileHeader{Extra: []byte{1, 0x99, 7, 0, 2, 0, 'A', 'E', 3, 8, 0}}}
	if !aes256Member(fake) {
		t.Fatal("AES-256 extra rejected")
	}
	fake.Extra[8] = 1
	if aes256Member(fake) {
		t.Fatal("AES-128 extra accepted")
	}
	binary.LittleEndian.PutUint16(fake.Extra[2:], 255)
	if aes256Member(fake) {
		t.Fatal("truncated extra accepted")
	}
	if _, err := json.Marshal(credentialPackageInfo()); err != nil {
		t.Fatal(err)
	}
}
