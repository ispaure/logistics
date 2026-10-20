package main

import (
	"context"
	"sync"
	"time"
)

// Credential replacement excludes readers and transfers. Local ciphertext reads
// share this lock with transfers, but never the serial network-operation lock or
// its cancellation handle. They do not create remote filesystem clients.
var credentialScope sync.RWMutex

func localCryptRead(action string) bool {
	switch action {
	case "crypt_remotes", "vault_info", "document_lists_seal", "document_lists_open", "remote_cache_archive", "crypt_path", "crypt_paths", "crypt_describe", "crypt_stat", "crypt_range", "crypt_raw_read", "crypt_decode", "crypt_archive", "crypt_manifest", "crypt_thumbnail", "connection_identity":
		return true
	}
	return false
}

func scopedOperation(action string) (context.Context, func()) {
	if action == "protect_package" || action == "unprotect_package" || action == "file_archive" || action == "file_thumbnail" || action == "image_thumbnail" {
		return context.WithTimeout(context.Background(), 2*time.Minute)
	}
	if localCryptRead(action) {
		credentialScope.RLock()
		ctx, stop := context.WithTimeout(context.Background(), operationTimeout(action))
		return ctx, func() { stop(); credentialScope.RUnlock() }
	}
	serial.Lock()
	switch action {
	case "import", "clear", "vault_open", "add_smb":
		credentialScope.Lock()
		ctx, stop := operation(action)
		return ctx, func() { stop(); credentialScope.Unlock(); serial.Unlock() }
	default:
		credentialScope.RLock()
		ctx, stop := operation(action)
		return ctx, func() { stop(); credentialScope.RUnlock(); serial.Unlock() }
	}
}

// Credential loading must never queue behind a network request or local reader.
// Publication changes process-wide rclone state, so reject contention rather
// than replacing credentials underneath an active operation. Do not replace
// the network cancellation handle when acquiring this independent local scope.
func tryCredentialLoad() (context.Context, func(), bool) {
	if !serial.TryLock() {
		return nil, nil, false
	}
	if !credentialScope.TryLock() {
		serial.Unlock()
		return nil, nil, false
	}
	ctx, stop := context.WithTimeout(context.Background(), 2*time.Minute)
	return ctx, func() { stop(); credentialScope.Unlock(); serial.Unlock() }, true
}
