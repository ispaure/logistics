// Wire decoding, operation admission and credential-state response publication.
package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
)

var credentialEpoch uint64

type bridgeRequest struct {
	Host           string            `json:"host"`
	User           string            `json:"user"`
	Domain         string            `json:"domain"`
	Port           string            `json:"port"`
	Package        string            `json:"package"`
	Password       string            `json:"password"`
	Remote         string            `json:"remote"`
	Path           string            `json:"path"`
	FD             int               `json:"fd"`
	OutputFD       int               `json:"output_fd"`
	Member         string            `json:"member"`
	Expected       string            `json:"expected"`
	Identity       string            `json:"identity"`
	Run            string            `json:"run"`
	Data           string            `json:"data"`
	Key            string            `json:"key"`
	ID             string            `json:"id"`
	Label          string            `json:"package_name"`
	Aliases        map[string]string `json:"aliases"`
	Session        bool              `json:"session_only"`
	LocalPath      string            `json:"local_path"`
	Push           bool              `json:"push"`
	BWLimit        int               `json:"bw_limit"`
	TrackRenames   bool              `json:"track_renames"`
	Excludes       []string          `json:"excludes"`
	CleanupPaths   []string          `json:"cleanup_paths"`
	Decrypted      bool              `json:"decrypted"`
	Directory      bool              `json:"directory"`
	Entries        []cryptPathEntry  `json:"entries"`
	Decode         bool              `json:"decode"`
	SourceRemote   string            `json:"source_remote"`
	SourcePath     string            `json:"source_path"`
	SourceIdentity string            `json:"source_identity"`
	Offset         int64             `json:"offset"`
	Count          int               `json:"count"`
	Width          int               `json:"width"`
	Height         int               `json:"height"`
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
	if action == "remote_cache_status" || action == "remote_cache_close" {
		return remoteComicControl(action, input)
	}
	if action == "mirror_progress" {
		return mirrorProgress(input)
	}
	if action == "mirror_review_progress" || action == "mirror_review_clear" {
		return reviewProgress(input, action == "mirror_review_clear")
	}
	var ctx context.Context
	var done func()
	if action == "import" || action == "vault_open" || action == "add_smb" {
		var acquired bool
		ctx, done, acquired = tryCredentialLoad()
		if !acquired {
			return `{"ok":false,"error_code":"credentials_busy","error":"Credentials are in use. Stop the active operation, then retry loading the credential ZIP."}`
		}
	} else {
		ctx, done = scopedOperation(action)
	}
	defer done()
	request, err := decodeRequest(action, input)
	var result any
	if err == nil {
		if request.Decrypted {
			ctx = context.WithValue(ctx, mirrorLogicalKey{}, true)
		}
		result, err = executeRequest(ctx, action, request)
	}
	return encodeReply(action, result, err)
}

// requestLimit returns encoded JSON bytes; zero explicitly permits larger review plans.
func requestLimit(action string) int {
	switch action {
	case "crypt_write_buffer":
		return base64.StdEncoding.EncodedLen(downloadLimit) + 64*1024
	case "image_thumbnail":
		return 24 * packageLimit
	case "mirror_review":
		return 0
	default:
		return 2 * packageLimit
	}
}

func decodeRequest(action, input string) (bridgeRequest, error) {
	var request bridgeRequest
	limit := requestLimit(action)
	if limit > 0 && len(input) > limit {
		return request, errors.New("request exceeds limits")
	}
	err := json.Unmarshal([]byte(input), &request)
	return request, err
}

func encodeReply(action string, result any, err error) string {
	if err == nil && action == "list" && store.failure() {
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
		switch action {
		case "import", "vault_open", "add_smb", "clear", "forget_package":
			credentialEpoch++
			info := vaultInfo()
			info["epoch"] = credentialEpoch
			reply["credential_state"] = info
		}
	}
	encoded, _ := json.Marshal(reply)
	return string(encoded)
}
