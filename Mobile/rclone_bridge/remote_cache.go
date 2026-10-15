package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"sync"
)

const remoteComicLimit int64 = 128 * 1024 * 1024
const remoteComicPoolLimit int64 = 256 * 1024 * 1024

type remoteComic struct {
	remote, path, identity, revision string
	data                             []byte
	done, total                      int64
	ready                            bool
}

var remoteComics = struct {
	sync.Mutex
	entries map[string]*remoteComic
	bytes   int64
}{entries: make(map[string]*remoteComic)}

func clearRemoteComics() {
	remoteComics.Lock()
	defer remoteComics.Unlock()
	clear(remoteComics.entries)
	remoteComics.bytes = 0
}

func releaseRemoteComic(run string) {
	remoteComics.Lock()
	defer remoteComics.Unlock()
	if item := remoteComics.entries[run]; item != nil {
		remoteComics.bytes -= item.total
		delete(remoteComics.entries, run)
	}
}

// Progress and release never wait for the serial network-operation lock.
func remoteComicControl(action, input string) string {
	var request struct {
		Run string `json:"run"`
	}
	if len(input) > 1024 || json.Unmarshal([]byte(input), &request) != nil || len(request.Run) != 32 {
		return `{"ok":false,"error":"invalid comic cache request"}`
	}
	if action == "remote_cache_close" {
		releaseRemoteComic(request.Run)
	}
	remoteComics.Lock()
	result := map[string]any{"done": int64(0), "total": int64(0), "ready": false}
	if item := remoteComics.entries[request.Run]; item != nil {
		result = map[string]any{"done": item.done, "total": item.total, "ready": item.ready}
	}
	remoteComics.Unlock()
	data, _ := json.Marshal(map[string]any{"ok": true, "result": result})
	return string(data)
}

func cacheRemoteComic(ctx context.Context, run, name, p, identity, expected string) (any, error) {
	if len(run) != 32 {
		return nil, errors.New("invalid comic cache key")
	}
	reader, size, revision, err := remoteDocument(ctx, name, p, identity)
	if err != nil {
		return nil, err
	}
	if size <= 0 || size > remoteComicLimit {
		return nil, errors.New("comic exceeds the 128 MiB memory preview limit; make a local copy")
	}
	if expected == "" || expected != revision {
		return nil, errors.New("remote comic changed; reopen it")
	}
	item := &remoteComic{remote: name, path: p, identity: identity, revision: revision, total: size}
	remoteComics.Lock()
	if remoteComics.entries[run] != nil || remoteComics.bytes+size > remoteComicPoolLimit {
		remoteComics.Unlock()
		return nil, errors.New("comic memory cache is full; close another remote comic and retry")
	}
	remoteComics.entries[run] = item
	remoteComics.bytes += size
	remoteComics.Unlock()
	success := false
	defer func() {
		if !success {
			releaseRemoteComic(run)
		}
	}()
	var stream io.ReadCloser
	if reader.cipher != nil {
		stream, err = reader.cipher.DecryptDataSeek(ctx, reader.open, 0, size)
	} else {
		stream, err = reader.open(ctx, 0, size)
	}
	if err != nil {
		return nil, err
	}
	defer stream.Close()
	data := make([]byte, int(size))
	for offset := int64(0); offset < size; {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		end := min(offset+256*1024, size)
		n, readErr := io.ReadFull(stream, data[offset:end])
		offset += int64(n)
		remoteComics.Lock()
		item.done = offset
		retained := remoteComics.entries[run] == item
		remoteComics.Unlock()
		if !retained {
			return nil, errors.New("comic cache was closed")
		}
		if readErr != nil {
			return nil, errors.New("remote comic download is incomplete")
		}
	}
	_, _, after, err := remoteDocument(ctx, name, p, identity)
	if err != nil || after != revision {
		return nil, errors.New("remote comic changed while downloading; reopen it")
	}
	remoteComics.Lock()
	if remoteComics.entries[run] != item {
		remoteComics.Unlock()
		return nil, errors.New("comic cache was closed")
	}
	item.data, item.ready = data, true
	remoteComics.Unlock()
	success = true
	return map[string]any{"size": size, "revision": revision}, nil
}

func cachedRemoteArchive(ctx context.Context, run, name, p, identity, expected, password, member string) (any, error) {
	remoteComics.Lock()
	item := remoteComics.entries[run]
	if item == nil || !item.ready || item.remote != name || item.path != p || item.identity != identity || item.revision != expected {
		remoteComics.Unlock()
		return nil, errors.New("comic memory cache is unavailable; reopen it")
	}
	data := item.data
	remoteComics.Unlock()
	current, err := connectionIdentity(name)
	if err != nil || current != identity {
		return nil, errors.New("credentials changed; reopen the comic")
	}
	return archiveContents(ctx, bytes.NewReader(data), int64(len(data)), password, member, 10000, 16*1024*1024)
}
