package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestRetainedPackageAuthenticationAndScope(t *testing.T) {
	key := bytes.Repeat([]byte{77}, 32)
	id := strings.Repeat("a", 64)
	plain := []byte("synthetic retained ZIP credential bytes")
	encrypted, err := protectPackage(plain, key, id, false)
	if err != nil || bytes.Contains(encrypted, plain) {
		t.Fatal("package not encrypted", err)
	}
	decoded, err := protectPackage(encrypted, key, id, true)
	if err != nil || !bytes.Equal(decoded, plain) {
		t.Fatal("package did not round trip", err)
	}
	if _, err := protectPackage(encrypted, key, strings.Repeat("b", 64), true); err == nil {
		t.Fatal("wrong package identity accepted")
	}
	encrypted[len(encrypted)-1] ^= 1
	if _, err := protectPackage(encrypted, key, id, true); err == nil {
		t.Fatal("tampered package accepted")
	}
	if _, err := protectPackage(make([]byte, packageLimit+1), key, id, false); err == nil {
		t.Fatal("oversized package accepted")
	}
}
