// Native request routing. Each case delegates I/O and policy to its domain owner.
package main

import (
	"context"
	"encoding/base64"
	"errors"
	"sort"
)

func executeRequest(ctx context.Context, action string, request bridgeRequest) (any, error) {
	var result any
	var err error
	switch action {
	case "add_smb":
		result, err = addSMB(request.Remote, request.Host, request.User, request.Password, request.Domain, request.Port, request.Session)
	case "import":
		var data []byte
		data, err = base64.StdEncoding.DecodeString(request.Package)
		if err == nil {
			result, err = importPackageWithAliases(data, request.Password, request.Label, request.Session, request.Aliases)
		}
	case "vault_open":
		var key []byte
		key, err = base64.StdEncoding.DecodeString(request.Key)
		if err == nil {
			var next *vaultStorage
			next, err = openVault(request.Path, request.ID, key)
			clear(key)
			if err == nil {
				err = installSavedCredentials(next)
				result = vaultInfo()
			}
		}
	case "document_lists_seal", "document_lists_open":
		var data []byte
		data, err = base64.StdEncoding.DecodeString(request.Data)
		if err == nil {
			data, err = documentLists(request.ID, data, action == "document_lists_open")
			if err == nil {
				result = base64.StdEncoding.EncodeToString(data)
			}
		}
		clear(data)
	case "protect_package", "unprotect_package":
		var key, data []byte
		key, err = base64.StdEncoding.DecodeString(request.Key)
		if err == nil {
			data, err = base64.StdEncoding.DecodeString(request.Data)
		}
		if err == nil {
			data, err = protectPackage(data, key, request.ID, action == "unprotect_package")
			if err == nil {
				result = base64.StdEncoding.EncodeToString(data)
			}
		}
		clear(key)
		clear(data)
	case "vault_info":
		result = vaultInfo()
	case "forget_package":
		var unopened *vaultStorage
		if savedCredentials == nil && request.Path != "" {
			var key []byte
			key, err = base64.StdEncoding.DecodeString(request.Key)
			if err == nil {
				unopened, err = openVault(request.Path, request.ID, key)
			}
			clear(key)
			if unopened != nil {
				defer unopened.detach()
			}
		}
		if err == nil {
			err = forgetCredentialPackage(request.Label, unopened)
		}
		result = vaultInfo()
	case "list":
		result, err = list(ctx, request.Remote, request.Path)
	case "remote_cache_open":
		result, err = cacheRemoteComic(ctx, request.Run, request.Remote, request.Path, request.Identity, request.Expected)
	case "remote_cache_archive":
		result, err = cachedRemoteArchive(ctx, request.Run, request.Remote, request.Path, request.Identity, request.Expected, request.Password, request.Member)
	case "remote_stat", "remote_range", "remote_archive":
		result, err = remoteDocumentRequest(ctx, action, request.Remote, request.Path, request.Identity,
			request.Expected, request.Password, request.Member, request.Offset, request.Count)
	case "connection_identity":
		result, err = connectionIdentity(request.Remote)
	case "mirror_info":
		result, err = mirrorInfo(ctx, request.Remote, request.Path)
	case "mirror_validate":
		result, err = mirrorValidate(ctx, request.Remote, request.Path, request.Identity, request.FD)
	case "mirror_sync":
		ctx = context.WithValue(ctx, transferOptionsKey{}, transferOptions{TrackRenames: request.TrackRenames, Excludes: request.Excludes})
		if store.failure() {
			err = errors.New("credentials could not be saved securely; sync was not started")
		} else if request.Download {
			result, err = downloadSync(ctx, request)
		} else {
			result, err = mirrorSync(ctx, request.Remote, request.Path, request.Identity, request.LocalPath, request.Run, request.Push, request.BWLimit)
		}
	case "mirror_review":
		ctx = context.WithValue(ctx, transferOptionsKey{}, transferOptions{TrackRenames: request.TrackRenames, Excludes: request.Excludes, CleanupPaths: request.CleanupPaths})
		result, err = mirrorReview(ctx, request.Remote, request.Path, request.Identity, request.LocalPath, request.Run, request.Push)
	case "crypt_remotes":
		names := []string{}
		for name := range admitted {
			if kind, _ := store.GetValue(name, "type"); kind == "crypt" {
				names = append(names, name)
			}
		}
		sort.Strings(names)
		result = names
	case "crypt_path":
		result, err = cryptPath(request.Remote, request.Path, request.Identity, request.Directory, request.Decode)
	case "crypt_paths":
		result, err = cryptPaths(ctx, request.Remote, request.Identity, request.Entries)
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
	case "crypt_write_buffer":
		result, err = cryptWriteBuffer(ctx, request.Remote, request.Path, request.Identity, request.Data, request.FD)
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
	return result, err
}
