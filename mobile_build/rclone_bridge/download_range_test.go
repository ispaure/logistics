// TEST_STAGE = TestStage.REGRESSION

// Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
// SPDX-License-Identifier: MIT

package main

import (
	"bytes"
	"context"
	"encoding/binary"
	"fmt"
	"io"
	"math/bits"
	"os"
	"testing"

	"github.com/rclone/rclone/fs"
)

type fixedDownloadRange struct {
	fs.Object
	start int64
	data  []byte
}

func (r fixedDownloadRange) Open(_ context.Context, options ...fs.OpenOption) (io.ReadCloser, error) {
	if len(options) != 1 {
		return nil, fmt.Errorf("expected one range option, got %v", options)
	}
	requested, ok := options[0].(*fs.RangeOption)
	if !ok || requested.Start != r.start || requested.End != r.start+int64(len(r.data))-1 {
		return nil, fmt.Errorf("unexpected backing range: %v", options)
	}
	return io.NopCloser(bytes.NewReader(r.data)), nil
}

func TestAuthenticatedDownloadRangeAt100GiB(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:large-range"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, _, _, _, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	const offset int64 = 100 << 30
	payload := []byte("verified final bytes")
	request, err := decodeRequest("download_range", fmt.Sprintf(`{"offset":%d,"count":%d}`, offset, len(payload)))
	if err != nil || request.Offset != offset || request.Count != len(payload) {
		t.Fatal("bridge range did not preserve the large offset", request.Offset, request.Count, err)
	}
	stream, err := cipher.EncryptData(bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	encoded, err := io.ReadAll(stream)
	if err != nil {
		t.Fatal(err)
	}
	const headerSize = 32
	header, tail := encoded[:headerSize], encoded[headerSize:]
	// The crypt nonce advances once per 64 KiB block. Backdate the header's
	// little-endian nonce so this real authenticated block belongs at 100 GiB.
	blocks := uint64(offset / 65536)
	for i := 8; i < headerSize; i += 8 {
		word, borrow := bits.Sub64(binary.LittleEndian.Uint64(header[i:]), blocks, 0)
		binary.LittleEndian.PutUint64(header[i:], word)
		blocks = borrow
	}
	reader := remoteReaderAt{object: fixedDownloadRange{start: cipher.EncryptedSize(offset), data: tail}, cipher: cipher}
	for _, encrypted := range []bool{false, true} {
		want := payload
		if encrypted {
			want = tail
		}
		got, err := authenticatedDownloadRange(context.Background(), reader, header, request.Offset, int64(request.Count), encrypted)
		if err != nil || !bytes.Equal(got, want) {
			t.Fatal("large authenticated range mismatch", encrypted, err)
		}
	}
}

func TestDownloadStreamAuthenticatesChunksAndResumes(t *testing.T) {
	clearSession()
	t.Cleanup(clearSession)
	if _, err := importPackage(cryptPackage(t, "Cloud:stream-range"), ""); err != nil {
		t.Fatal(err)
	}
	cipher, _, _, _, err := cryptConnection("Secret")
	if err != nil {
		t.Fatal(err)
	}
	payload := bytes.Repeat([]byte("checkpoint"), downloadChunk/2)
	stream, err := cipher.EncryptData(bytes.NewReader(payload))
	if err != nil {
		t.Fatal(err)
	}
	ciphertext, err := io.ReadAll(stream)
	if err != nil {
		t.Fatal(err)
	}
	header := ciphertext[:32]
	for _, offset := range []int64{0, downloadChunk} {
		for _, encoded := range []bool{false, true} {
			start := cipher.EncryptedSize(offset)
			backing := fixedDownloadRange{start: start, data: ciphertext[start:]}
			reader := remoteReaderAt{object: backing, cipher: cipher}
			pipeReader, pipeWriter, err := os.Pipe()
			if err != nil {
				t.Fatal(err)
			}
			finished := make(chan error, 1)
			remaining := int64(len(payload)) - offset
			go func() {
				size, err := streamDownload(context.Background(), reader, header, offset, remaining, encoded, int(pipeWriter.Fd()))
				pipeWriter.Close()
				if err == nil && size != remaining {
					err = fmt.Errorf("wrong logical byte count: %d", size)
				}
				finished <- err
			}()
			data, readErr := io.ReadAll(pipeReader)
			pipeReader.Close()
			want := payload[offset:]
			if encoded && offset == 0 {
				want = ciphertext
			} else if encoded {
				want = ciphertext[start:]
			}
			if err := <-finished; err != nil || readErr != nil || !bytes.Equal(data, want) {
				t.Fatal("wrong streamed data", offset, encoded, readErr, err)
			}
		}
	}

	regular, err := os.CreateTemp(t.TempDir(), "not-a-pipe")
	if err != nil {
		t.Fatal(err)
	}
	defer regular.Close()
	reader := remoteReaderAt{object: fixedDownloadRange{start: 32, data: ciphertext[32:]}, cipher: cipher}
	if _, err := streamDownload(context.Background(), reader, header, 0, int64(len(payload)), false, int(regular.Fd())); err == nil {
		t.Fatal("accepted a regular file as the download pipe")
	}
}
