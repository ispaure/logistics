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
	// Default config.Storage is in memory. Never install configfile or start RC.
	_ = config.SetConfigPath("")
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

func operation() (context.Context, func()) {
	ctx, stop := context.WithTimeout(context.Background(), 2*time.Minute)
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
			for _, c := range name {
				if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-' || c == ' ') {
					return "", nil, errors.New("invalid remote name")
				}
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

func clearSession() {
	ctx, stop := context.WithTimeout(context.Background(), 15*time.Second)
	defer stop()
	for _, client := range clients {
		if shutdown := client.Features().Shutdown; shutdown != nil {
			_ = shutdown(ctx)
		}
	}
	for _, name := range config.Data().GetSectionList() {
		config.Data().DeleteSection(name)
	}
	admitted = map[string]bool{}
	clients = map[string]fs.Fs{}
}

func importPackage(data []byte, password string) ([]string, error) {
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
	// Publish only after every member has authenticated and validated.
	clearSession()
	names := []string{}
	for name, values := range pending {
		for key, value := range values {
			config.Data().SetValue(name, key, value)
		}
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
	f, err := fs.NewFs(ctx, name+":")
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

func read(ctx context.Context, name, p string) ([]byte, error) {
	if p == "" || !validPath(p) {
		return nil, errors.New("invalid remote path")
	}
	f, err := remote(ctx, name)
	if err != nil {
		return nil, err
	}
	obj, err := f.NewObject(ctx, p)
	if err != nil {
		return nil, errors.New("remote file could not be opened")
	}
	if obj.Size() < 0 || obj.Size() > downloadLimit {
		return nil, errors.New("download exceeds 32 MiB")
	}
	stream, err := obj.Open(ctx)
	if err != nil {
		return nil, errors.New("remote file could not be opened")
	}
	data, err := io.ReadAll(io.LimitReader(stream, downloadLimit+1))
	closeErr := stream.Close()
	if err != nil || closeErr != nil || ctx.Err() != nil {
		return nil, errors.New("download failed or cancelled")
	}
	if len(data) > downloadLimit || int64(len(data)) != obj.Size() {
		return nil, errors.New("download size changed or exceeds limits")
	}
	return data, nil
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
	serial.Lock()
	defer serial.Unlock()
	ctx, done := operation()
	defer done()
	var request struct {
		Package  string `json:"package"`
		Password string `json:"password"`
		Remote   string `json:"remote"`
		Path     string `json:"path"`
	}
	var result any
	var err error
	if len(input) > 2*packageLimit {
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
				result, err = importPackage(data, request.Password)
			}
		case "list":
			result, err = list(ctx, request.Remote, request.Path)
		case "read":
			var data []byte
			data, err = read(ctx, request.Remote, request.Path)
			if err == nil {
				result = base64.StdEncoding.EncodeToString(data)
			}
		case "probe":
			result, err = selfCheck(ctx)
		case "clear":
			clearSession()
			result = true
		default:
			err = errors.New("unsupported mobile operation")
		}
	}
	reply := map[string]any{"ok": err == nil}
	if err != nil {
		reply["error"] = "Rclone operation failed."
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
