package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/rclone/rclone/fs/config"
	"github.com/rclone/rclone/fs/fspath"
)

// The view contains no persistence key. Each alias delegates mutations to the
// package which owns it; a session-only package never acquires a vault parent.
type credentialOrigin struct {
	storage *vaultStorage
	name    string
}
type credentialSet struct {
	id      string
	storage *vaultStorage
	aliases map[string]string
}

var credentialSets = map[string]*credentialSet{}
var credentialView *vaultStorage
var savedCredentials *vaultStorage
var latestCredential string

func packageID(label string) string {
	sum := sha256.Sum256([]byte(label))
	return hex.EncodeToString(sum[:])
}
func copySnapshot(value snapshot) snapshot {
	result := snapshot{Label: value.Label, Remotes: map[string]map[string]string{}, Pins: map[string]connectionPin{}, Aliases: map[string]string{}}
	for name, values := range value.Remotes {
		result.Remotes[name] = map[string]string{}
		for key, value := range values {
			result.Remotes[name][key] = value
		}
	}
	for name, pin := range value.Pins {
		result.Pins[name] = pin
	}
	for name, alias := range value.Aliases {
		result.Aliases[name] = alias
	}
	return result
}
func ensureCredentialSets() {
	if store == credentialView && (store.origins != nil || len(store.values.Remotes) == 0 || len(credentialSets) > 0) {
		return
	}
	credentialSets = map[string]*credentialSet{}
	savedCredentials = nil
	latestCredential = ""
	if store.path != "" {
		savedCredentials = store
	}
	if len(store.values.Remotes) > 0 {
		if len(store.values.Packages) > 0 {
			for id, value := range store.values.Packages {
				child := newStore()
				child.values = copySnapshot(value)
				child.parent = store
				child.packageID = id
				credentialSets[id] = &credentialSet{id, child, child.values.Aliases}
			}
		} else {
			child := store
			if savedCredentials != nil {
				child = newStore()
				child.values = copySnapshot(store.values)
				child.parent = store
				child.packageID = packageID(child.values.Label)
			}
			id := packageID(child.values.Label)
			credentialSets[id] = &credentialSet{id, child, child.values.Aliases}
		}
		latestCredential = store.values.Label
	}
	for _, set := range credentialSets {
		if set.aliases == nil {
			set.aliases = map[string]string{}
		}
		for _, name := range set.storage.GetSectionList() {
			if set.aliases[name] == "" {
				set.aliases[name] = name
			}
		}
		set.storage.values.Aliases = set.aliases
	}
	credentialView = store
}
func trimUTF8(value string, limit int) string {
	if len(value) <= limit {
		return value
	}
	value = value[:limit]
	for !utf8.ValidString(value) {
		value = value[:len(value)-1]
	}
	return strings.TrimSpace(value)
}
func qualifiedRemote(name, label, id string) string {
	label = fspath.MakeConfigName(strings.TrimSuffix(label, filepath.Ext(label)))
	suffix := " @ " + trimUTF8(label, 24) + " " + id[:8]
	return trimUTF8(name, 80-len(suffix)) + suffix
}
func assignAliases(set *credentialSet) error {
	used := map[string]bool{}
	for id, other := range credentialSets {
		if id != set.id {
			for _, alias := range other.aliases {
				used[alias] = true
			}
		}
	}
	names := set.storage.GetSectionList()
	if set.aliases == nil {
		set.aliases = map[string]string{}
	}
	for _, name := range names {
		alias := set.aliases[name]
		if alias == "" {
			alias = name
		}
		if used[alias] {
			alias = qualifiedRemote(name, set.storage.values.Label, set.id)
		}
		if used[alias] || len(alias) > 80 || fspath.CheckConfigName(alias) != nil {
			return errors.New("credential remote aliases conflict; choose a different package filename")
		}
		set.aliases[name] = alias
		used[alias] = true
	}
	set.storage.values.Aliases = set.aliases
	return nil
}
func publishCredentialSets() {
	view := newStore()
	view.origins = map[string]credentialOrigin{}
	view.values.Label = latestCredential
	admitted = map[string]bool{}
	for _, set := range credentialSets {
		for name, alias := range set.aliases {
			if values := set.storage.values.Remotes[name]; values != nil {
				view.values.Remotes[alias] = values
				view.origins[alias] = credentialOrigin{set.storage, name}
				admitted[alias] = true
			}
		}
	}
	store = view
	credentialView = view
	config.SetData(view)
}
func installCredentialPackage(pending snapshot, sessionOnly bool) ([]string, error) {
	ensureCredentialSets()
	id := packageID(pending.Label)
	if len(credentialSets) >= 32 && credentialSets[id] == nil {
		return nil, errors.New("up to 32 credential packages are supported")
	}
	child := newStore()
	child.values = copySnapshot(pending)
	child.packageID = id
	if previous := credentialSets[id]; previous != nil && len(child.values.Aliases) == 0 {
		child.values.Aliases = map[string]string{}
		for name, alias := range previous.aliases {
			if child.values.Remotes[name] != nil {
				child.values.Aliases[name] = alias
			}
		}
	}
	next := &credentialSet{id, child, child.values.Aliases}
	for name := range child.values.Aliases {
		if child.values.Remotes[name] == nil {
			return nil, errors.New("credential alias refers to an unavailable remote")
		}
	}
	if err := assignAliases(next); err != nil {
		return nil, err
	}
	if !sessionOnly && savedCredentials != nil {
		child.parent = savedCredentials
		if err := child.save(child.values); err != nil {
			return nil, err
		}
	}
	shutdownClients()
	if previous := credentialSets[id]; previous != nil {
		previous.storage.detach()
	}
	credentialSets[id] = next
	latestCredential = pending.Label
	publishCredentialSets()
	return store.GetSectionList(), nil
}
func installSavedCredentials(next *vaultStorage) error {
	ensureCredentialSets()
	additions := map[string]*credentialSet{}
	values := next.values.Packages
	if len(values) == 0 && len(next.values.Remotes) > 0 {
		values = map[string]snapshot{packageID(next.values.Label): copySnapshot(next.values)}
	}
	// Existing session-only versions take precedence until explicitly reloaded.
	for id, value := range values {
		if previous := credentialSets[id]; previous != nil && previous.storage.parent == nil && previous.storage.path == "" {
			continue
		}
		child := newStore()
		child.values = copySnapshot(value)
		child.parent = next
		child.packageID = id
		set := &credentialSet{id, child, child.values.Aliases}
		before := copySnapshot(child.values).Aliases
		if err := assignAliases(set); err != nil {
			return err
		}
		if !reflect.DeepEqual(before, set.aliases) {
			if err := child.save(child.values); err != nil {
				return err
			}
		}
		additions[id] = set
	}
	shutdownClients()
	oldRoot := savedCredentials
	for id, set := range credentialSets {
		if set.storage.parent != nil || set.storage.path != "" {
			set.storage.detach()
			delete(credentialSets, id)
		}
	}
	for id, set := range additions {
		credentialSets[id] = set
	}
	savedCredentials = next
	if oldRoot != nil && oldRoot != next {
		oldRoot.detach()
	}
	if latestCredential == "" {
		latestCredential = next.values.Label
	}
	publishCredentialSets()
	return nil
}
func credentialSource(name string) (*vaultStorage, string) {
	if source, ok := store.origins[name]; ok {
		return source.storage, source.name
	}
	return store, name
}
func sourceAlias(source *vaultStorage, name string) string {
	for alias, origin := range store.origins {
		if origin.storage == source && origin.name == name {
			return alias
		}
	}
	return name
}
func credentialPackageInfo() []map[string]any {
	ensureCredentialSets()
	ids := []string{}
	for id := range credentialSets {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	result := []map[string]any{}
	for _, id := range ids {
		set := credentialSets[id]
		names := []string{}
		aliases := map[string]string{}
		identities := map[string]string{}
		cryptIDs := map[string]string{}
		for name, alias := range set.aliases {
			names = append(names, alias)
			aliases[name] = alias
			if identity, err := connectionIdentity(alias); err == nil {
				identities[alias] = identity
			}
			set.storage.mu.Lock()
			if values := set.storage.values.Remotes[name]; values["type"] == "crypt" {
				data, _ := json.Marshal(values)
				sum := sha256.Sum256(data)
				cryptIDs[alias] = hex.EncodeToString(sum[:])
			}
			set.storage.mu.Unlock()
		}
		sort.Strings(names)
		result = append(result, map[string]any{"document_cache_id": documentListID(id), "id": id, "package_name": set.storage.values.Label, "saved": set.storage.parent != nil || set.storage.path != "", "remotes": names, "aliases": aliases, "identities": identities, "crypt_identities": cryptIDs})
	}
	return result
}

func validateCredentialSnapshot(value snapshot) error {
	if !validLabel(value.Label) || len(value.Remotes) == 0 || len(value.Remotes) > 64 || len(value.Pins) > 64 || len(value.Aliases) > 64 {
		return vaultError
	}
	for name, values := range value.Remotes {
		text := "[" + name + "]\n"
		for key, value := range values {
			text += key + "=" + value + "\n"
		}
		parsed, _, err := parseCredential([]byte(text))
		if err != nil || parsed != name {
			return vaultError
		}
	}
	if validateCryptRemotes(value.Remotes) != nil {
		return vaultError
	}
	for name, pin := range value.Pins {
		if value.Remotes[name] == nil || !validDigest(pin.Signature) || !validDigest(pin.Identity) {
			return vaultError
		}
	}
	used := map[string]bool{}
	for name, alias := range value.Aliases {
		if value.Remotes[name] == nil || len(alias) > 80 || fspath.CheckConfigName(alias) != nil || used[alias] {
			return vaultError
		}
		used[alias] = true
	}
	return nil
}
func validateCredentialEnvelope(value snapshot) error {
	if validateCredentialSnapshot(value) != nil || len(value.Packages) > 32 {
		return vaultError
	}
	used := map[string]bool{}
	for id, item := range value.Packages {
		if id != packageID(item.Label) || len(item.Packages) > 0 || validateCredentialSnapshot(item) != nil {
			return vaultError
		}
		for name := range item.Remotes {
			alias := item.Aliases[name]
			if alias == "" {
				alias = name
			}
			if used[alias] {
				return vaultError
			}
			used[alias] = true
		}
	}
	return nil
}
