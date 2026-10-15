package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"sync"

	"github.com/rclone/rclone/backend/crypt"
	"github.com/rclone/rclone/fs"
	"github.com/rclone/rclone/fs/operations"
)

type comparison struct {
	sync.Mutex
	run       string
	changes   map[string]string
	revisions map[string]string
	stop      context.CancelFunc
	overflow  bool
	cleanup   map[string]bool
}

var comparisonState struct {
	sync.Mutex
	current *comparison
}

// Each dry-run attempt owns a fresh comparison. Failed attempts must never
// contribute rows or revisions to a later successful review.
func (c *comparison) attempt(work func() error) func() error {
	return func() error {
		c.Lock()
		c.changes, c.revisions = map[string]string{}, map[string]string{}
		c.Unlock()
		return work()
	}
}

func (c *comparison) logger(cipher *crypt.Cipher) operations.LoggerFn {
	return func(ctx context.Context, sigil operations.Sigil, src, dst fs.DirEntry, err error) {
		if err != nil && !errors.Is(err, fs.ErrorIsDir) {
			return
		}
		item := src
		if item == nil {
			item = dst
		}
		if item == nil {
			return
		}
		_, isFile := item.(fs.Object)
		kind := map[operations.Sigil]string{operations.MissingOnSrc: "delete", operations.MissingOnDst: "add", operations.Differ: "replace", operations.Match: "match"}[sigil]
		if kind == "" {
			return
		}
		if c.cleanup[item.Remote()] {
			if sigil == operations.MissingOnDst {
				kind = "cleanup"
			} else {
				kind = "delete"
			}
		}
		name := item.Remote()
		if name == "" && !isFile {
			return // The scope root itself is not a transfer entry.
		}
		if cipher != nil {
			var plain string
			var decodeErr error
			if isFile {
				plain, decodeErr = cipher.DecryptFileName(name)
			} else {
				plain, decodeErr = cipher.DecryptDirName(name)
			}
			if decodeErr == nil {
				name = plain
			}
		}
		if !isFile {
			name += "/" // Separate a directory from a same-named conflicting file.
		}
		row := []any{name, kind}
		for _, entry := range []fs.DirEntry{src, dst} {
			if entry == nil {
				row = append(row, nil)
			} else if _, file := entry.(fs.Object); !file {
				// Directory timestamps vary between backends and can be synthesized.
				// Membership and type are what changes the reviewed empty-folder work.
				row = append(row, "directory")
			} else {
				row = append(row, []any{entry.Size(), entry.ModTime(ctx).UTC().String()})
			}
		}
		encoded, _ := json.Marshal(row)
		c.Lock()
		defer c.Unlock()
		if len(c.changes) >= 10000 {
			if _, exists := c.changes[name]; !exists {
				c.overflow = true
				c.stop()
				return
			}
		}
		c.changes[name], c.revisions[name] = kind, string(encoded)
	}
}

func (c *comparison) snapshot() map[string]any {
	c.Lock()
	defer c.Unlock()
	names := make([]string, 0, len(c.changes))
	for name := range c.changes {
		names = append(names, name)
	}
	sort.Strings(names)
	rows := make([][]string, 0, len(names))
	hash := sha256.New()
	for _, name := range names {
		rows = append(rows, []string{c.changes[name], name})
		hash.Write([]byte(c.revisions[name]))
		hash.Write([]byte{0})
	}
	return map[string]any{"changes": rows, "fingerprint": hex.EncodeToString(hash.Sum(nil))}
}

func mirrorReview(ctx context.Context, name, p, identity, localPath, run string, push bool) (any, error) {
	ctx, stop := context.WithCancel(ctx)
	defer stop()
	c := &comparison{run: run, changes: map[string]string{}, revisions: map[string]string{}, stop: stop}
	opts, _ := ctx.Value(transferOptionsKey{}).(transferOptions)
	c.cleanup = map[string]bool{}
	if !push && len(opts.CleanupPaths) != 0 {
		return nil, errors.New("cleanup is push-only")
	}
	for _, name := range opts.CleanupPaths {
		if !validPath(name) || name == "" || len(c.cleanup) >= 10000 {
			return nil, errors.New("invalid cleanup plan")
		}
		c.cleanup[name] = true
	}
	comparisonState.Lock()
	comparisonState.current = c
	comparisonState.Unlock()
	_, err := mirrorRun(ctx, name, p, identity, localPath, run, push, 0, c)
	if c.overflow {
		return nil, errors.New("review exceeds 10,000 entries; narrow the scope or proceed without a full review")
	}
	if err != nil {
		return nil, err
	}
	return c.snapshot(), nil
}

func reviewProgress(input string, clear bool) string {
	var request struct {
		Run string `json:"run"`
	}
	var result any
	var err error
	if len(input) > 1024 || json.Unmarshal([]byte(input), &request) != nil || len(request.Run) != 32 || strings.Trim(request.Run, "0123456789abcdef") != "" {
		err = errors.New("invalid comparison transaction")
	} else {
		comparisonState.Lock()
		c := comparisonState.current
		if clear && c != nil && c.run == request.Run {
			comparisonState.current = nil
		}
		comparisonState.Unlock()
		result = map[string]any{"changes": [][]string{}}
		if !clear && c != nil && c.run == request.Run {
			result = c.snapshot()
		}
	}
	reply := map[string]any{"ok": err == nil, "result": result}
	if err != nil {
		reply["error"] = err.Error()
	}
	data, _ := json.Marshal(reply)
	return string(data)
}
