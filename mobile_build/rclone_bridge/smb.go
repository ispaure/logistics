package main

import (
	"errors"
	"net"
	"strconv"
	"strings"

	"github.com/rclone/rclone/fs/config/obscure"
	"github.com/rclone/rclone/fs/fspath"
)

// Keep SMB configuration limited to explicit NTLM credentials. In particular,
// don't admit Kerberos cache/config paths from credential packages on mobile.
func validateSMB(values map[string]string) error {
	host := values["host"]
	if host == "" || len(host) > 253 || strings.ContainsAny(host, "/\\@ \t\r\n\x00") || (strings.Contains(host, ":") && net.ParseIP(host) == nil) {
		return errors.New("enter an SMB hostname or IP address without a URL or share path")
	}
	if values["user"] == "" || len(values["user"]) > 256 {
		return errors.New("enter an SMB username (use guest for guest access)")
	}
	for _, key := range []string{"user", "domain", "pass"} {
		if len(values[key]) > 8192 || strings.ContainsAny(values[key], "\x00\r\n") {
			return errors.New("invalid SMB credentials")
		}
	}
	if port := values["port"]; port != "" {
		n, err := strconv.Atoi(port)
		if err != nil || n < 1 || n > 65535 {
			return errors.New("SMB port must be between 1 and 65535")
		}
	}
	if password := values["pass"]; password != "" {
		if _, err := obscure.Reveal(password); err != nil {
			return errors.New("SMB credential packages require an rclone-obscured password")
		}
	}
	return nil
}

// Called under the bridge serial lock. Append without changing any existing
// remote or OAuth identity pins; publish to the vault before admitting it.
func addSMB(name, host, user, password, domain, port string, sessionOnly bool) ([]string, error) {
	if len(name) < 1 || len(name) > 80 || fspath.CheckConfigName(name) != nil {
		return nil, errors.New("enter a valid connection name")
	}
	if store.HasSection(name) {
		return nil, errors.New("a connection with that name already exists; choose another name")
	}
	if len(password) > 4096 || strings.ContainsAny(password, "\x00\r\n") {
		return nil, errors.New("invalid SMB password")
	}
	hidden, err := obscure.Obscure(password)
	if err != nil {
		return nil, errors.New("could not protect SMB password")
	}
	values := map[string]string{"type": "smb", "host": host, "user": user, "pass": hidden, "domain": domain, "port": port}
	if err := validateSMB(values); err != nil {
		return nil, err
	}
	ensureCredentialSets()
	label := "Network shares"
	if sessionOnly {
		label = "Session network shares"
	}
	pending := snapshot{Label: label, Remotes: map[string]map[string]string{}, Pins: map[string]connectionPin{}}
	if previous := credentialSets[packageID(label)]; previous != nil {
		pending = copySnapshot(previous.storage.values)
	}
	if len(pending.Remotes) >= 64 {
		return nil, errors.New("up to 64 connections per credential package are supported")
	}
	pending.Remotes[name] = values
	return installCredentialPackage(pending, sessionOnly, nil)
}
