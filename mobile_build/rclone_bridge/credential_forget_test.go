// TEST_STAGE = TestStage.REGRESSION
package main

import (
	"bytes"
	"os"
	"runtime"
	"testing"
	"time"
)

func TestForgetPackageUsesTokenRefreshLockOrder(t *testing.T) {
	file, key, id := savedFixture(t)
	if _, err := importPackageMode(multiPackage(t, "Main", "drive", `{"access_token":"fixture"}`), "", "Personal.zip", false); err != nil {
		t.Fatal(err)
	}
	selected := credentialSets[packageID("Personal.zip")].storage
	root := savedCredentials
	writer := selected.connection("Main")
	// An in-flight token callback already owns the child mutex. Forget must
	// wait there without taking the parent which that callback needs to save.
	selected.mu.Lock()
	done := make(chan error, 1)
	started := make(chan struct{})
	go func() { close(started); done <- forgetCredentialPackage("Personal.zip", nil) }()
	<-started
	heldParent := false
	until := time.Now().Add(100 * time.Millisecond)
	for time.Now().Before(until) {
		if !root.mu.TryLock() {
			heldParent = true
			break
		}
		root.mu.Unlock()
		runtime.Gosched()
	}
	selected.mu.Unlock()
	select {
	case err := <-done:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("forget deadlocked with an in-flight token callback")
	}
	if heldParent {
		t.Fatal("forget inverted the package/vault lock order")
	}
	writer.Set("token", `{"access_token":"late-refresh"}`)
	restored, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	defer restored.detach()
	if len(restored.values.Remotes) != 0 {
		t.Fatal("late callback recreated forgotten credentials")
	}
}

func TestForgetPackagePreservesOtherSavedAndSessionPackages(t *testing.T) {
	file, key, id := savedFixture(t)
	for _, label := range []string{"Personal.zip", "Work.zip"} {
		if _, err := importPackageMode(multiPackage(t, "Shared", "memory", ""), "", label, false); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := importPackageMode(multiPackage(t, "Shared", "memory", ""), "", "Session.zip", true); err != nil {
		t.Fatal(err)
	}
	workAlias := packageAlias(t, "Work.zip", "Shared")
	sessionAlias := packageAlias(t, "Session.zip", "Shared")
	retired := credentialSets[packageID("Personal.zip")].storage
	if err := forgetCredentialPackage("Personal.zip", nil); err != nil {
		t.Fatal(err)
	}
	if admitted["Shared"] || !admitted[workAlias] || !admitted[sessionAlias] || len(credentialSets) != 2 {
		t.Fatal("incorrect package revoked")
	}
	retired.SetValue("Shared", "token", "must-not-return")
	if err := retired.Save(); err != nil {
		t.Fatal(err)
	}
	restored, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	defer restored.detach()
	if len(restored.values.Packages) != 1 || restored.values.Packages[packageID("Work.zip")].Label != "Work.zip" {
		t.Fatal("forgotten or session package persisted")
	}
}

func TestForgetShadowingSessionAlsoRemovesItsOldSavedVersion(t *testing.T) {
	file, key, id := savedFixture(t)
	for _, label := range []string{"Personal.zip", "Work.zip"} {
		if _, err := importPackageMode(multiPackage(t, label[:4], "memory", ""), "", label, false); err != nil {
			t.Fatal(err)
		}
	}
	if _, err := importPackageMode(multiPackage(t, "SessionPersonal", "memory", ""), "", "Personal.zip", true); err != nil {
		t.Fatal(err)
	}
	if err := forgetCredentialPackage("Personal.zip", nil); err != nil {
		t.Fatal(err)
	}
	clearSession()
	restored, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	if err := installSavedCredentials(restored); err != nil {
		t.Fatal(err)
	}
	if len(credentialSets) != 1 || credentialSets[packageID("Personal.zip")] != nil {
		t.Fatal("saved credentials resurrected")
	}
}

func TestForgetLockedPackageDoesNotUnlockOtherPackages(t *testing.T) {
	file, key, id := savedFixture(t)
	for _, label := range []string{"Personal.zip", "Work.zip"} {
		if _, err := importPackageMode(multiPackage(t, label[:4], "memory", ""), "", label, false); err != nil {
			t.Fatal(err)
		}
	}
	clearSession()
	unopened, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	if err := forgetCredentialPackage("Personal.zip", unopened); err != nil {
		t.Fatal(err)
	}
	unopened.detach()
	if len(credentialSets) != 0 || len(admitted) != 0 {
		t.Fatal("forget unlocked an unrelated package")
	}
	remaining, err := openVault(file, id, key)
	if err != nil {
		t.Fatal(err)
	}
	if len(remaining.values.Packages) != 1 {
		t.Fatal("remaining saved package lost")
	}
	if err := forgetCredentialPackage("Work.zip", remaining); err != nil {
		t.Fatal(err)
	}
	remaining.detach()
	if _, err := os.Stat(file); !os.IsNotExist(err) {
		t.Fatal("last package ciphertext remains", err)
	}
}

func TestForgetPackageFailedSaveKeepsOtherCredentialsAndCiphertext(t *testing.T) {
	file, _, _ := savedFixture(t)
	if _, err := importPackageMode(multiPackage(t, "Main", "memory", ""), "", "Personal.zip", false); err != nil {
		t.Fatal(err)
	}
	original, _ := os.ReadFile(file)
	if err := os.WriteFile(file, []byte("changed-outside-this-process"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := forgetCredentialPackage("Personal.zip", nil); err == nil {
		t.Fatal("unsafe saved removal succeeded")
	}
	if !admitted["Main"] {
		t.Fatal("failed transaction changed live credentials")
	}
	after, _ := os.ReadFile(file)
	if bytes.Equal(after, original) {
		t.Fatal("unexpected overwrite")
	}
}
