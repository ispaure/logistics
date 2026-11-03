package main

import (
	"context"
	"errors"
	"io"
	"sync"
)

// ZIP inflation makes small sequential reads. Keep one authenticated crypt
// block for this request so each small read does not decrypt the block again.
// This cache never outlives the descriptor/credential operation that owns it.
const archiveBlockSize = 64 * 1024

type archiveBlockReader struct {
	ctx    context.Context
	source io.ReaderAt
	size   int64
	mu     sync.Mutex
	data   []byte
	offset int64
}

func (reader *archiveBlockReader) close() {
	reader.mu.Lock()
	defer reader.mu.Unlock()
	clear(reader.data)
	reader.data = nil
}

func (reader *archiveBlockReader) ReadAt(buffer []byte, offset int64) (int, error) {
	reader.mu.Lock()
	defer reader.mu.Unlock()
	if err := reader.ctx.Err(); err != nil {
		return 0, err
	}
	if offset < 0 {
		return 0, errors.New("invalid range")
	}
	done := 0
	for len(buffer) > 0 {
		if err := reader.ctx.Err(); err != nil {
			return done, err
		}
		if offset >= reader.size {
			return done, io.EOF
		}
		start := offset / archiveBlockSize * archiveBlockSize
		if len(reader.data) == 0 || reader.offset != start {
			count := min(int64(archiveBlockSize), reader.size-start)
			clear(reader.data)
			reader.data = reader.data[:0]
			if cap(reader.data) < int(count) {
				reader.data = make([]byte, 0, count)
			}
			block := reader.data[:count]
			if n, err := reader.source.ReadAt(block, start); n != len(block) || err != nil {
				clear(block)
				if err == nil {
					err = io.ErrUnexpectedEOF
				}
				return done, err
			}
			reader.data, reader.offset = block, start
		}
		n := copy(buffer, reader.data[offset-start:])
		buffer, offset, done = buffer[n:], offset+int64(n), done+n
	}
	return done, nil
}
