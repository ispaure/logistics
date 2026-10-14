// Package main is a deliberately small, read-only mobile rclone C bridge.
package main

/*
#include <stdlib.h>
*/
import "C"

import (
	"bytes"
	"context"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
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
	_ "github.com/rclone/rclone/backend/webdav"
	"github.com/rclone/rclone/fs"
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
var allowed = map[string]string{
	"crypt":    "remote password password2 filename_encryption directory_name_encryption filename_encoding suffix",
	"drive":    "token client_id client_secret scope root_folder_id team_drive",
	"dropbox":  "token client_id client_secret root_namespace impersonate",
	"onedrive": "token client_id client_secret drive_id drive_type root_folder_id region",
	"s3":       "provider access_key_id secret_access_key session_token region endpoint location_constraint force_path_style",
	"webdav":   "url vendor user pass bearer_token",
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
	ci.ConnectTimeout = fs.Duration(15 * time.Second)
	ci.Timeout = fs.Duration(15 * time.Second)
	ci.LowLevelRetries = 1
	ci.Retries = 1
}

func cancel() {
	cancellation.Lock()
	defer cancellation.Unlock()
	if active != nil {
		active()
	}
}

func operation(action string) (context.Context, func()) {
	duration := 2 * time.Minute
	switch action {
	case "read", "crypt_read", "crypt_fetch", "crypt_raw_write", "crypt_metadata", "crypt_manifest", "mirror_read", "mirror_stat", "mirror_write":
		duration = 30 * time.Minute
	}
	ctx, stop := context.WithTimeout(context.Background(), duration)
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
	return name, values, nil
}

func shutdownClients() {
	clear(cryptCiphers)
	ctx, stop := context.WithTimeout(context.Background(), 15*time.Second)
	defer stop()
	for _, client := range clients {
		if shutdown := client.Features().Shutdown; shutdown != nil {
			_ = shutdown(ctx)
		}
	}

	clients = map[string]fs.Fs{}
}

func clearSession() {
	shutdownClients()
	admitted = map[string]bool{}
	store.detach()
	store = newStore()
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
	if err := validateCryptRemotes(pending); err != nil {
		return nil, err
	}
	// Publish authenticated settings to disk before replacing the session.

	if !validLabel(label) {
		return nil, errors.New("invalid credential package name")
	}
	candidate := store
	if sessionOnly {
		candidate = newStore()
	}
	shutdownClients()
	if err := candidate.replace(snapshot{Label: label, Remotes: pending}); err != nil {
		return nil, err
	}
	if sessionOnly {
		store.detach()
		store = candidate
		config.SetData(store)
	}
	admitted = map[string]bool{}
	names := []string{}
	for name := range pending {
		admitted[name] = true
		names = append(names, name)
	}
	sort.Strings(names)
	return names, nil
}

func remote(ctx context.Context, name string) (fs.Fs, error) {
	if !admitted[name] {
		return nil, errors.New("import a credential package first")
	}
	if f := clients[name]; f != nil {
		return f, nil
	}
	kind, _ := store.GetValue(name, "type")
	if kind == "crypt" {
		return nil, errors.New("crypt uses the bounded encrypted-copy interface")
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
	if len(rows) > 1000 {
		return nil, errors.New("folder exceeds 1000 entries")
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

// readInto writes only to a caller-owned private descriptor. It duplicates
// that descriptor so Go can close its own handle without closing Python's.
func readInto(ctx context.Context, name, p string, fd int) (int64, error) {
	if kind, _ := store.GetValue(name, "type"); kind == "crypt" {
		return 0, errors.New("use Download encrypted copy for crypt files")
	}
	if p == "" || !validPath(p) || fd < 3 {
		return 0, errors.New("invalid download destination")
	}
	f, err := remote(ctx, name)
	if err != nil {
		return 0, err
	}
	obj, err := f.NewObject(ctx, p)
	if err != nil {
		return 0, errors.New("remote file could not be opened")
	}
	if obj.Size() < 0 {
		return 0, errors.New("download size is unavailable")
	}
	target, err := privateOutput(fd)
	if err != nil {
		return 0, err
	}
	defer target.Close()
	stream, err := obj.Open(ctx)
	if err != nil {
		return 0, errors.New("remote file could not be opened")
	}
	count, copyErr := io.Copy(target, contextReader{ctx, stream})
	closeErr := stream.Close()
	if copyErr != nil || closeErr != nil || ctx.Err() != nil {
		return 0, errors.New("download failed or cancelled")
	}
	if count != obj.Size() {
		return 0, errors.New("download size changed or exceeds limits")
	}
	if target.Sync() != nil {
		return 0, errors.New("private download could not be flushed")
	}
	return count, nil
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

func dispatch(action, input string) (output string) {
	defer func() {
		if recover() != nil {
			output = `{"ok":false,"error":"Invalid credential package or failed native operation."}`
		}
	}()
	if action == "cancel" {
		cancel()
		return `{"ok":true}`
	}
	// Local archive/image work uses no rclone configuration and can continue
	// while a remote transfer owns the credential engine. It also must not
	// replace that transfer's cancellation handle.
	var ctx context.Context
	var done context.CancelFunc
	if action == "file_archive" || action == "file_thumbnail" || action == "image_thumbnail" {
		ctx, done = context.WithTimeout(context.Background(), 2*time.Minute)
	} else {
		serial.Lock()
		defer serial.Unlock()
		ctx, done = operation(action)
	}
	defer done()
	var request struct {
		Package        string `json:"package"`
		Password       string `json:"password"`
		Remote         string `json:"remote"`
		Path           string `json:"path"`
		FD             int    `json:"fd"`
		OutputFD       int    `json:"output_fd"`
		Member         string `json:"member"`
		Identity       string `json:"identity"`
		Expected       string `json:"expected"`
		Run            string `json:"run"`
		Data           string `json:"data"`
		Key            string `json:"key"`
		ID             string `json:"id"`
		Label          string `json:"package_name"`
		Session        bool   `json:"session_only"`
		Directory      bool   `json:"directory"`
		Decode         bool   `json:"decode"`
		SourceRemote   string `json:"source_remote"`
		SourcePath     string `json:"source_path"`
		SourceIdentity string `json:"source_identity"`
		Offset         int64  `json:"offset"`
		Count          int    `json:"count"`
		Width          int    `json:"width"`
		Height         int    `json:"height"`
	}
	var result any
	var err error
	requestLimit := 2 * packageLimit
	if action == "image_thumbnail" {
		requestLimit = 24 * packageLimit
	}
	if len(input) > requestLimit {
		err = errors.New("request exceeds limits")
	} else {
		err = json.Unmarshal([]byte(input), &request)
	}
	if err == nil {
		switch action {
		case "import":
			var data []byte
			data, err = base64.StdEncoding.DecodeString(request.Package)
			if err == nil {
				result, err = importPackageMode(data, request.Password, request.Label, request.Session)
			}
		case "vault_open":
			var key []byte
			key, err = base64.StdEncoding.DecodeString(request.Key)
			if err == nil {
				var next *vaultStorage
				next, err = openVault(request.Path, request.ID, key)
				clear(key)
				if err == nil {
					shutdownClients()
					store.detach()
					store = next
					admitted = map[string]bool{}
					config.SetData(store)
					for _, name := range store.GetSectionList() {
						admitted[name] = true
					}
					result = vaultInfo()
				}
			}
		case "vault_info":
			result = vaultInfo()
		case "list":
			result, err = list(ctx, request.Remote, request.Path)
		case "connection_identity":
			result, err = connectionIdentity(request.Remote)
		case "mirror_info":
			result, err = mirrorInfo(ctx, request.Remote, request.Path)
		case "mirror_list":
			result, err = mirrorList(ctx, request.Remote, request.Path, request.Identity)
		case "mirror_read":
			result, err = mirrorRead(ctx, request.Remote, request.Path, request.Identity, request.FD)
		case "mirror_stat":
			result, err = mirrorStat(ctx, request.Remote, request.Path, request.Identity)
		case "mirror_write":
			if store.failure() {
				err = errors.New("credentials could not be saved securely; push was not started")
			} else {
				result, err = mirrorWrite(ctx, request.Remote, request.Path, request.Identity, request.Expected, request.Run, request.FD)
			}
		case "read":
			result, err = readInto(ctx, request.Remote, request.Path, request.FD)
		case "crypt_read":
			result, err = cryptReadInto(ctx, request.Remote, request.Path, request.FD)
		case "crypt_remotes":
			names := []string{}
			for name := range admitted {
				if kind, _ := store.GetValue(name, "type"); kind == "crypt" {
					names = append(names, name)
				}
			}
			sort.Strings(names)
			result = names
		case "crypt_fetch":
			result, err = cryptFetch(ctx, request.Remote, request.Path, request.FD)
		case "crypt_path":
			result, err = cryptPath(request.Remote, request.Path, request.Identity, request.Directory, request.Decode)
		case "crypt_raw_read":
			result, err = cryptRawRead(ctx, request.Remote, request.Path, request.Identity, request.FD)
		case "crypt_stat":
			result, err = cryptStat(ctx, request.Remote, request.Path, request.Identity, request.FD)
		case "crypt_range":
			result, err = cryptRange(ctx, request.Remote, request.Path, request.Identity, request.FD, request.Offset, request.Count)
		case "file_archive":
			result, err = fileArchive(ctx, request.FD, request.Password, request.Member)
		case "crypt_archive":
			result, err = cryptArchive(ctx, request.Remote, request.Path, request.Identity, request.Password, request.Member, request.FD)
		case "crypt_manifest":
			result, err = cryptManifest(ctx, request.Remote, request.Path, request.Identity, request.Password, request.FD)
		case "crypt_thumbnail":
			result, err = cryptThumbnail(ctx, request.Remote, request.Path, request.Identity, request.Password, request.Member, request.FD, request.Width, request.Height)
		case "file_thumbnail":
			result, err = fileThumbnail(ctx, request.FD, request.Width, request.Height)
		case "image_thumbnail":
			var data []byte
			data, err = base64.StdEncoding.DecodeString(request.Data)
			if err == nil && len(data) <= 16*packageLimit {
				result, err = nativeThumbnail(ctx, data, request.Width, request.Height)
			} else {
				err = errors.New("image exceeds thumbnail buffer")
			}
		case "remote_thumbnail":
			result, err = remoteThumbnail(ctx, request.Remote, request.Path, request.Password, request.Width, request.Height)
		case "crypt_raw_write":
			result, err = cryptRawWrite(ctx, request.Remote, request.Path, request.Identity, request.FD, request.OutputFD, request.SourceRemote, request.SourcePath, request.SourceIdentity)
		case "crypt_describe":
			result, _, err = cryptDescribe(request.Remote, request.Path, request.Identity)
		case "crypt_decode":
			result, err = cryptDecode(ctx, request.Remote, request.Path, request.Identity, request.FD, request.Password)
		case "crypt_metadata":
			result, err = cryptStreamMetadata(ctx, request.Remote, request.Path, request.Identity, request.Password, request.Member, request.Data, request.FD, request.OutputFD)
		case "crypt_encode":
			result, err = cryptEncode(ctx, request.Remote, request.Path, request.Identity, request.Data, request.FD)
		case "probe":
			result, err = selfCheck(ctx)
		case "clear":
			clearSession()
			result = true
		default:
			err = errors.New("unsupported mobile operation")
		}
	}
	if err == nil && (action == "list" || action == "read" || action == "crypt_read" || action == "crypt_fetch") && store.failure() {
		err = errors.New("Credentials refreshed in memory but could not be saved securely. Retry before closing the app.")
	}
	reply := map[string]any{"ok": err == nil}
	if err != nil {
		reply["error"] = "Rclone operation failed."
		if errors.Is(err, archivePasswordError) {
			reply["error_code"] = "archive_password"
		}
		if action != "probe" {
			reply["error"] = err.Error()
		}
	} else {
		reply["result"] = result
	}
	encoded, _ := json.Marshal(reply)
	return string(encoded)
}

//export LogisticsCloud
func LogisticsCloud(action, input *C.char) *C.char {
	return C.CString(dispatch(C.GoString(action), C.GoString(input)))
}

//export LogisticsCloudFree
func LogisticsCloudFree(value unsafe.Pointer) { C.free(value) }

func main() {}
