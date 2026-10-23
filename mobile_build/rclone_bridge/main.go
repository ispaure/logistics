// Package main is a scoped mobile rclone C bridge with verified copy operations.
package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"bytes"
	"context"
	"crypto/x509"
	"errors"
	"io"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"
	"unicode/utf8"
	"unsafe"

	_ "github.com/rclone/rclone/backend/drive"
	_ "github.com/rclone/rclone/backend/dropbox"
	_ "github.com/rclone/rclone/backend/memory"
	_ "github.com/rclone/rclone/backend/onedrive"
	_ "github.com/rclone/rclone/backend/s3"
	_ "github.com/rclone/rclone/backend/smb"
	_ "github.com/rclone/rclone/backend/webdav"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/accounting"
	"github.com/rclone/rclone/fs/cache"
	"github.com/rclone/rclone/fs/config"
	"github.com/rclone/rclone/fs/config/configmap"
	"github.com/rclone/rclone/fs/fspath"
	"github.com/rclone/rclone/fs/object"
	"github.com/yeka/zip"
)

const packageLimit = 1024 * 1024
const downloadLimit = 32 * 1024 * 1024

var serial sync.Mutex
var cancellation sync.Mutex
var active context.CancelFunc
var admitted = map[string]bool{}
var clients = map[string]fs.Fs{}
var staleFilesystemCache bool
var allowed = map[string]string{
	"crypt":    "remote password password2 filename_encryption directory_name_encryption filename_encoding suffix",
	"drive":    "token client_id client_secret scope root_folder_id team_drive",
	"dropbox":  "token client_id client_secret root_namespace impersonate",
	"onedrive": "token client_id client_secret drive_id drive_type root_folder_id region",
	"s3":       "provider access_key_id secret_access_key session_token region endpoint location_constraint force_path_style",
	"webdav":   "url vendor user pass bearer_token",
	"smb":      "host user pass domain port",
	"memory":   "",
}

func init() {
	if runtime.GOOS == "android" {
		_ = os.Setenv("SSL_CERT_DIR", "/apex/com.android.conscrypt/cacerts:/system/etc/security/cacerts")
	}
	// A nonempty logical path installs our storage; never install configfile or RC.
	_ = config.SetConfigPath(filepath.Join(os.TempDir(), "logistics-memory-only"))
	config.SetData(store)
	ci := fs.GetConfig(context.Background())
	ci.LogLevel = fs.LogLevelEmergency
	// Keep rclone defaults for connection/idle timeouts and retry counts.
	// Install error accounting once before any bridge worker can run.
	accounting.Start(context.Background())
}

func cancel() {
	cancellation.Lock()
	defer cancellation.Unlock()
	if active != nil {
		active()
	}
}

func operationTimeout(action string) time.Duration {
	duration := 2 * time.Minute
	switch action {
	case "mirror_sync", "mirror_review":
		return 0 // Sync runs until completion or explicit cancellation, as on desktop.
	case "crypt_raw_write", "crypt_metadata", "crypt_manifest", "mirror_validate":
		duration = 30 * time.Minute
	}
	return duration
}

func operation(action string) (context.Context, func()) {
	ctx, stop := context.WithCancel(context.Background())
	if duration := operationTimeout(action); duration > 0 {
		stop()
		ctx, stop = context.WithTimeout(context.Background(), duration)
	}
	cancellation.Lock()
	active = stop
	cancellation.Unlock()
	return ctx, func() { stop(); cancellation.Lock(); active = nil; cancellation.Unlock() }
}

func validPath(p string) bool {
	if len(p) > 4096 || !utf8.ValidString(p) || strings.ContainsAny(p, "\\\x00\r\n") || strings.HasPrefix(p, "/") {
		return false
	}
	for _, part := range strings.Split(p, "/") {
		if part == ".." || part == "." {
			return false
		}
	}
	return true
}

func parseCredential(text []byte) (string, map[string]string, error) {
	if !utf8.Valid(text) || bytes.Contains(text, []byte{0}) {
		return "", nil, errors.New("invalid credentials")
	}
	lines := strings.Split(strings.TrimPrefix(string(text), "\ufeff"), "\n")
	name := ""
	values := map[string]string{}
	for _, raw := range lines {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") || strings.HasPrefix(line, ";") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			if name != "" {
				return "", nil, errors.New("one remote per TXT file is required")
			}
			name = line[1 : len(line)-1]
			if len(name) < 1 || len(name) > 80 {
				return "", nil, errors.New("invalid remote name")
			}
			if fspath.CheckConfigName(name) != nil {
				return "", nil, errors.New("invalid remote name")
			}
			continue
		}
		key, value, ok := strings.Cut(line, "=")
		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		if !ok || name == "" || key == "" || len(value) > 128*1024 {
			return "", nil, errors.New("invalid credential settings")
		}
		if _, exists := values[key]; exists {
			return "", nil, errors.New("duplicate credential setting")
		}
		values[key] = value
	}
	kind := values["type"]
	keys, ok := allowed[kind]
	if !ok {
		return "", nil, errors.New("remote type is not supported on mobile")
	}
	for key, value := range values {
		if key != "type" && !strings.Contains(" "+keys+" ", " "+key+" ") {
			return "", nil, errors.New("unsupported credential setting")
		}
		if strings.ContainsAny(value, "\r\n") {
			return "", nil, errors.New("invalid credential setting")
		}
		if (key == "url" || key == "endpoint") && value != "" {
			u, err := url.Parse(value)
			if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.Fragment != "" {
				return "", nil, errors.New("remote URLs must use HTTPS without embedded credentials or fragments")
			}
		}
	}
	if kind == "webdav" && values["url"] == "" {
		return "", nil, errors.New("WebDAV URL is required")
	}
	if kind == "smb" {
		if err := validateSMB(values); err != nil {
			return "", nil, err
		}
	}
	return name, values, nil
}

func shutdownClients() {
	clearRemoteComics()
	comparisonState.Lock()
	comparisonState.current = nil
	comparisonState.Unlock()
	// Cache eviction can itself disconnect network clients. Defer it until
	// the next explicit online operation, before it creates a filesystem.
	staleFilesystemCache = true
	cryptCipherMu.Lock()
	clear(cryptCiphers)
	cryptCipherMu.Unlock()
	// Detach synchronously, then retire old network clients independently. A
	// backend's disconnect must never delay a local credential import/unlock.
	retired := clients
	clients = map[string]fs.Fs{}
	if len(retired) > 0 {
		go retireClients(retired)
	}
}

func retireClients(retired map[string]fs.Fs) {
	ctx, stop := context.WithTimeout(context.Background(), 15*time.Second)
	defer stop()
	for _, client := range retired {
		if shutdown := client.Features().Shutdown; shutdown != nil {
			_ = shutdown(ctx)
		}
	}
}

func clearSession() {
	clearDocumentListKeys()
	shutdownClients()
	for _, set := range credentialSets {
		set.storage.detach()
	}
	if savedCredentials != nil {
		savedCredentials.detach()
	}
	admitted = map[string]bool{}
	store.detach()
	store = newStore()
	credentialSets = map[string]*credentialSet{}
	credentialView = store
	savedCredentials = nil
	latestCredential = ""
	config.SetData(store)
}

func importPackage(data []byte, password string, labels ...string) ([]string, error) {
	label := "Credentials.zip"
	if len(labels) > 0 {
		label = labels[0]
	}
	return importPackageMode(data, password, label, false)
}
func importPackageMode(data []byte, password, label string, sessionOnly bool) ([]string, error) {
	return importPackageWithAliases(data, password, label, sessionOnly, nil)
}
func importPackageWithAliases(data []byte, password, label string, sessionOnly bool, aliases map[string]string) ([]string, error) {
	if len(data) > packageLimit || len(password) > 4096 {
		return nil, errors.New("credential package exceeds limits")
	}
	archive, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil || len(archive.File) == 0 || len(archive.File) > 64 {
		return nil, errors.New("invalid credential ZIP")
	}
	pending := map[string]map[string]string{}
	seen := map[string]bool{}
	total := 0
	for _, member := range archive.File {
		if seen[strings.ToLower(member.Name)] {
			return nil, errors.New("duplicate credential ZIP member")
		}
		seen[strings.ToLower(member.Name)] = true
		if !validPath(member.Name) || !member.Mode().IsRegular() && !member.FileInfo().IsDir() {
			return nil, errors.New("unsafe credential ZIP member")
		}
		if member.FileInfo().IsDir() {
			continue
		}
		if strings.ToLower(path.Ext(member.Name)) != ".txt" || member.UncompressedSize64 > 256*1024 || member.CompressedSize64 > packageLimit {
			return nil, errors.New("credential ZIP must contain small TXT files")
		}
		if member.IsEncrypted() {
			member.SetPassword(password)
		}
		reader, err := member.Open()
		if err != nil {
			return nil, errors.New("invalid password or credential ZIP")
		}
		text, readErr := io.ReadAll(io.LimitReader(reader, 256*1024+1))
		closeErr := reader.Close()
		total += len(text)
		if readErr != nil || closeErr != nil || len(text) > 256*1024 || total > packageLimit {
			return nil, errors.New("invalid password or credential ZIP")
		}
		name, values, err := parseCredential(text)
		if err != nil {
			return nil, err
		}
		if _, exists := pending[name]; exists {
			return nil, errors.New("duplicate remote name")
		}
		pending[name] = values
	}
	if len(pending) == 0 {
		return nil, errors.New("no credential TXT files found")
	}
	validated := snapshotCryptCiphers(nil)
	if err := validateCryptRemotes(pending, validated); err != nil {
		return nil, err
	}
	// Publish authenticated settings to disk before replacing the session.

	if !validLabel(label) {
		return nil, errors.New("invalid credential package name")
	}
	names, err := installCredentialPackage(snapshot{Label: label, Remotes: pending, Pins: initialConnectionPins(pending), Aliases: aliases}, sessionOnly, validated)
	if err == nil {
		installDocumentListKey(label, data, password, sessionOnly)
	}
	return names, err
}

func clearStaleFilesystemCache() {
	if staleFilesystemCache {
		cache.Clear()
		staleFilesystemCache = false
	}
}

func remote(ctx context.Context, name string) (fs.Fs, error) {
	if !admitted[name] {
		return nil, errors.New("import a credential package first")
	}
	clearStaleFilesystemCache()
	kind, _ := store.GetValue(name, "type")
	if kind == "crypt" && ctx.Value(mirrorLogicalKey{}) != true {
		return nil, errors.New("crypt uses the bounded encrypted-copy interface")
	}
	if f := clients[name]; f != nil {
		return f, nil
	}
	info, err := fs.Find(kind)
	if err != nil {
		return nil, errors.New("unsupported mobile backend")
	}
	values := store.connection(name)
	options := fs.ConfigMap(info.Prefix, info.Options, "", nil)
	// Retain registered backend defaults, but admit only our validated settings.
	options.ClearGetters(configmap.PriorityNormal)
	options.AddGetter(values, configmap.PriorityNormal)
	options.ClearSetters().AddSetter(values)
	f, err := info.NewFs(ctx, name, "", options)
	if err != nil {
		return nil, errors.New("could not connect; check credentials and network")
	}
	clients[name] = f
	return f, nil
}

type entry struct {
	Path      string `json:"path"`
	Size      int64  `json:"size"`
	Directory bool   `json:"directory"`
}

func list(ctx context.Context, name, dir string) ([]entry, error) {
	if !validPath(dir) {
		return nil, errors.New("invalid remote path")
	}
	if kind, _ := store.GetValue(name, "type"); kind == "crypt" {
		return cryptList(ctx, name, dir)
	}
	f, err := remote(ctx, name)
	if err != nil {
		return nil, err
	}
	rows, err := f.List(ctx, dir)
	if err != nil {
		return nil, errors.New("remote folder could not be listed")
	}
	result := []entry{}
	for _, row := range rows {
		p := row.Remote()
		if !validPath(p) || len(p) > 4096 {
			return nil, errors.New("invalid remote entry")
		}
		_, isObject := row.(fs.Object)
		result = append(result, entry{p, row.Size(), !isObject})
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Path < result[j].Path })
	return result, nil
}

func selfCheck(ctx context.Context) (string, error) {
	// In-memory fixture only: this diagnostic never contacts a user's remote.
	roots, rootErr := x509.SystemCertPool()
	if rootErr != nil || (runtime.GOOS == "android" && len(roots.Subjects()) == 0) {
		return "", errors.New("platform certificate store is unavailable")
	}
	f, err := fs.NewFs(ctx, ":memory:logistics-native-check")
	if err != nil {
		return "", err
	}
	text := []byte("Native rclone fixture\n")
	_, err = f.Put(ctx, bytes.NewReader(text), object.NewStaticObjectInfo("fixture.txt", time.Now(), int64(len(text)), true, nil, f))
	if err != nil {
		return "", err
	}
	obj, err := f.NewObject(ctx, "fixture.txt")
	if err != nil {
		return "", err
	}
	stream, err := obj.Open(ctx)
	if err != nil {
		return "", err
	}
	value, err := io.ReadAll(stream)
	_ = stream.Close()
	if err != nil || !bytes.Equal(value, text) {
		return "", errors.New("rclone fixture failed")
	}
	return fs.Version, nil
}

//export LogisticsCloud
func LogisticsCloud(action, input *C.char) *C.char {
	return C.CString(dispatch(C.GoString(action), C.GoString(input)))
}

//export LogisticsCloudFree
func LogisticsCloudFree(value unsafe.Pointer) { C.free(value) }

func main() {}
